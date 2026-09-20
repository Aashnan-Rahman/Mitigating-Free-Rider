from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset

from atomic_io import atomic_write_json
from clients.attacks import flatten_delta
from comparison.frad import FradDetector, FradInputs
from comparison.frida import FridaLossDetector
from config import ExperimentConfig
from data.loaders import get_datasets
from models.architectures import get_model
from server.aggregation import clone_state, floating_keys
from server.detection import evaluate_updates
from train import build_layer_profile, resolve_device, set_global_seed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare server-side SWT-CP, FRIDA-loss and paper-guided FRAD "
            "detector time without modifying completed FL runs."
        )
    )
    parser.add_argument("--dataset", choices=("mnist", "cifar10"), default="cifar10")
    parser.add_argument("--clients", type=int, default=100)
    parser.add_argument("--free-rider-pct", type=float, default=0.4)
    parser.add_argument("--canary-size", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--frad-epochs", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--torch-threads",
        type=int,
        help="Limit PyTorch CPU threads for a reproducible low-impact benchmark.",
    )
    parser.add_argument(
        "--note",
        default="",
        help="Record an environmental caveat such as a concurrent background run.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        args.clients = 6
        args.canary_size = 8
        args.repeats = 1
        args.frad_epochs = 2
    validate_args(args)

    if args.torch_threads is not None:
        torch.set_num_threads(args.torch_threads)

    set_global_seed(args.seed)
    device = resolve_device(args.device)
    config = ExperimentConfig(
        dataset=args.dataset,
        num_clients=args.clients,
        free_rider_pct=args.free_rider_pct,
        seed=args.seed,
        device=str(device),
        pin_memory=device.type == "cuda",
    )
    train_set, _ = get_datasets(config)
    if args.canary_size > len(train_set):
        raise ValueError("canary-size exceeds the training dataset")
    canary_loader = DataLoader(
        Subset(train_set, list(range(args.canary_size))),
        batch_size=min(32, args.canary_size),
        shuffle=False,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )

    model = get_model(args.dataset).to(device)
    base_state = clone_state(model.state_dict())
    honest_state = train_canary_prototype(model, base_state, canary_loader, device)
    client_states, free_riders = make_client_states(
        base_state,
        honest_state,
        args.clients,
        args.free_rider_pct,
        args.seed,
        device,
    )
    deltas = {
        client_id: flatten_delta(state, base_state)
        for client_id, state in client_states.items()
    }
    profiles = {
        client_id: build_layer_profile(state, base_state, config.zero_update_epsilon)
        for client_id, state in client_states.items()
    }
    honest_ids = [item for item in client_states if item not in free_riders]
    reference_ids = honest_ids[: min(10, len(honest_ids))]
    reference = (
        torch.stack([deltas[item] for item in reference_ids]).mean(dim=0)
        if reference_ids
        else torch.zeros_like(next(iter(deltas.values())))
    )

    frida = FridaLossDetector(z_threshold=2.0)
    model_bytes = sum(
        tensor.numel() * tensor.element_size() for tensor in base_state.values()
    )
    delta_norms = torch.tensor(
        [float(deltas[item].norm().item()) for item in range(args.clients)]
    )
    is_honest = torch.tensor(
        [0.0 if item in free_riders else 1.0 for item in range(args.clients)]
    )
    # These inputs model FRAD's named contribution factors.  Ground truth is
    # used only to construct a controlled synthetic workload, never by detect().
    frad_inputs = FradInputs(
        computation=0.05 + 0.95 * is_honest,
        communication=torch.full((args.clients,), float(model_bytes)),
        data_quality=0.10 + 0.90 * is_honest,
        history=delta_norms,
    )

    calls: dict[str, Callable[[], Any]] = {
        "swtcp_detection_primitive": lambda: evaluate_updates(
            deltas, profiles, reference, set(client_states), config
        ),
        "frida_loss_server": lambda: frida.detect(
            model, client_states, canary_loader, device
        ),
        "frad_paper_guided": lambda: FradDetector(
            epochs=args.frad_epochs,
            anomaly_quantile=1.0 - args.free_rider_pct,
        ).detect(frad_inputs, device),
    }
    results: dict[str, dict[str, Any]] = {}
    for name, call in calls.items():
        durations: list[float] = []
        flagged_counts: list[int] = []
        for repeat in range(args.repeats):
            set_global_seed(args.seed + repeat)
            synchronize(device)
            started = time.perf_counter()
            output = call()
            synchronize(device)
            durations.append(time.perf_counter() - started)
            if isinstance(output, dict):
                flagged_counts.append(sum(bool(item.flagged) for item in output.values()))
            else:
                flagged_counts.append(sum(output.flags.values()))
        results[name] = summarize(durations, flagged_counts)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or Path("results") / f"detector_overhead_{timestamp}.json"
    report = {
        "created_at": datetime.now().isoformat(),
        "scope": "server-side detector microbenchmark",
        "distribution": "not applicable: controlled synthetic client states",
        "dataset_model": args.dataset,
        "device": str(device),
        "torch_threads": torch.get_num_threads(),
        "environment_note": args.note,
        "clients": args.clients,
        "free_rider_pct": args.free_rider_pct,
        "canary_size": args.canary_size,
        "repeats": args.repeats,
        "frad_epochs": args.frad_epochs,
        "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
        "model_state_bytes": model_bytes,
        "limitations": [
            "FRIDA timing covers server-side loss inference only; required honest-client canary training is excluded.",
            "FRAD is a paper-guided reproduction because no author implementation was located.",
            "This microbenchmark measures computational overhead, not IID/non-IID detection effectiveness.",
            "SWT-CP timing covers its update-scoring primitive, not selection or longitudinal bookkeeping.",
        ],
        "results": results,
    }
    atomic_write_json(output_path, report)
    print(json.dumps(report, indent=2))
    print(f"Benchmark written to: {output_path}")


def validate_args(args: argparse.Namespace) -> None:
    if args.clients < 2:
        raise ValueError("clients must be at least 2")
    if not 0.0 < args.free_rider_pct < 1.0:
        raise ValueError("free-rider-pct must be in (0, 1)")
    if args.canary_size <= 0 or args.repeats <= 0 or args.frad_epochs <= 0:
        raise ValueError("canary-size, repeats and frad-epochs must be positive")
    if args.torch_threads is not None and args.torch_threads <= 0:
        raise ValueError("torch-threads must be positive")


def train_canary_prototype(
    model: nn.Module,
    base_state: dict[str, torch.Tensor],
    loader: DataLoader,
    device: torch.device,
) -> dict[str, torch.Tensor]:
    model.load_state_dict(base_state)
    model.train()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)
    loss_fn = nn.CrossEntropyLoss()
    for inputs, targets in loader:
        inputs = inputs.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        loss = loss_fn(model(inputs), targets)
        loss.backward()
        optimizer.step()
    return clone_state(model.state_dict())


def make_client_states(
    base_state: dict[str, torch.Tensor],
    honest_state: dict[str, torch.Tensor],
    clients: int,
    free_rider_pct: float,
    seed: int,
    device: torch.device,
) -> tuple[dict[int, dict[str, torch.Tensor]], set[int]]:
    count = math.ceil(clients * free_rider_pct)
    free_riders = set(range(count))
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)
    states: dict[int, dict[str, torch.Tensor]] = {}
    for client_id in range(clients):
        if client_id in free_riders:
            states[client_id] = clone_state(base_state)
            continue
        state = clone_state(honest_state)
        for key in floating_keys(state):
            noise = torch.randn(
                state[key].shape,
                generator=generator,
                device=state[key].device,
                dtype=state[key].dtype,
            )
            state[key] = state[key] + noise * 1e-6
        states[client_id] = state
    return states, free_riders


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def summarize(durations: list[float], flagged_counts: list[int]) -> dict[str, Any]:
    return {
        "samples_seconds": durations,
        "mean_seconds": statistics.fmean(durations),
        "median_seconds": statistics.median(durations),
        "min_seconds": min(durations),
        "max_seconds": max(durations),
        "population_std_seconds": statistics.pstdev(durations),
        "flagged_clients_each_repeat": flagged_counts,
    }


if __name__ == "__main__":
    main()
