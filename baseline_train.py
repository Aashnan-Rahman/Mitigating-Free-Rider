from __future__ import annotations

import math
import random
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, Subset

from clients.attacks import FreeRiderAttacker, flatten_delta
from comparison.frad import FradDetector, FradInputs
from comparison.frida import FridaLossDetector
from config import ExperimentConfig
from data.loaders import get_datasets, make_eval_loader
from data.partition import partition_dataset
from logging_utils import RunLogger
from models.architectures import get_model
from server.aggregation import clone_state, fedavg_delta
from train import (
    delete_successful_checkpoints,
    evaluate_model,
    hardware_info,
    make_client_loader,
    resource_snapshot,
    resolve_device,
    safe_ratio,
    save_rolling_checkpoint,
    set_global_seed,
    train_local_model,
)


class _TargetSubset(Dataset):
    """Subset that preserves a targets attribute for Dirichlet partitioning."""

    def __init__(self, dataset: Dataset, indices: Sequence[int]) -> None:
        self.dataset = dataset
        self.indices = [int(item) for item in indices]
        source_targets = getattr(dataset, "targets", getattr(dataset, "labels", None))
        if source_targets is None:
            raise ValueError("Baseline dataset must expose targets or labels")
        self.targets = np.asarray(source_targets)[self.indices]

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, index: int):
        return self.dataset[self.indices[index]]


def run_baseline_experiment(
    config: ExperimentConfig,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> str:
    """Run FRIDA-loss or the paper-guided FRAD reproduction with recovery."""
    config.validate()
    if config.methodology_version not in {"frida_loss", "frad_reproduction"}:
        raise ValueError(f"Unsupported baseline methodology: {config.methodology_version}")

    run_name = config.resolved_run_name()
    start_time = datetime.now()
    wall_start = time.perf_counter()
    set_global_seed(config.seed)
    device = resolve_device(config.device)
    generator = torch.Generator(device=device)
    generator.manual_seed(config.seed)
    rng = random.Random(config.seed)

    train_set, test_set = get_datasets(config)
    canary_total = config.baseline_canary_size * config.num_rounds
    if config.methodology_version == "frida_loss" and canary_total >= len(train_set):
        raise ValueError(
            "FRIDA requires baseline_canary_size * num_rounds to leave local training data"
        )
    permutation = np.random.default_rng(config.seed + 70_001).permutation(len(train_set))
    if config.methodology_version == "frida_loss":
        canary_indices = permutation[:canary_total].astype(int).tolist()
        local_indices = permutation[canary_total:].astype(int).tolist()
    else:
        canary_indices = []
        local_indices = permutation.astype(int).tolist()
    local_dataset = _TargetSubset(train_set, local_indices)
    partitions = partition_dataset(local_dataset, config)
    client_loaders = [
        make_client_loader(local_dataset, indices, config, config.seed + client_id)
        for client_id, indices in enumerate(partitions)
    ]
    eval_loader = make_eval_loader(config, test_set)

    model = get_model(config.dataset).to(device)
    global_state = clone_state(model.state_dict())
    loss_fn = nn.CrossEntropyLoss()
    free_rider_count = math.ceil(config.free_rider_pct * config.num_clients)
    free_riders = set(rng.sample(range(config.num_clients), free_rider_count))
    attacker = FreeRiderAttacker(config, device)
    logger = RunLogger(config, run_name)
    times_flagged = {client_id: 0 for client_id in range(config.num_clients)}
    times_evaluated = {client_id: 0 for client_id in range(config.num_clients)}
    first_flag_round: dict[int, int] = {}
    norm_history = {client_id: 0.0 for client_id in range(config.num_clients)}
    cumulative = {key: 0 for key in ("tp", "fp", "tn", "fn")}
    start_round = 1

    if config.resume_checkpoint:
        checkpoint_path = Path(config.resume_checkpoint)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Resume checkpoint not found: {checkpoint_path}")
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        saved_config = checkpoint.get("config", {})
        for field in ("methodology_version", "dataset", "distribution", "attack_type"):
            if saved_config.get(field) != getattr(config, field):
                raise ValueError(f"Checkpoint {field} does not match the requested baseline")
        completed_round = int(checkpoint["round"])
        if completed_round >= config.num_rounds:
            raise ValueError("Resume checkpoint already reached num_rounds")
        global_state = clone_state(checkpoint["global_state"])
        model.load_state_dict(global_state)
        free_riders = {int(item) for item in checkpoint["free_riders_ground_truth"]}
        times_flagged.update(
            {int(key): int(value) for key, value in checkpoint["times_flagged"].items()}
        )
        times_evaluated.update(
            {int(key): int(value) for key, value in checkpoint["times_evaluated"].items()}
        )
        first_flag_round.update(
            {int(key): int(value) for key, value in checkpoint.get("first_flag_round", {}).items()}
        )
        norm_history.update(
            {int(key): float(value) for key, value in checkpoint.get("norm_history", {}).items()}
        )
        cumulative.update(
            {str(key): int(value) for key, value in checkpoint.get("cumulative", {}).items()}
        )
        attacker.load_state_dict(checkpoint.get("attacker_state", {}))
        if "rng_state" in checkpoint:
            rng.setstate(checkpoint["rng_state"])
        if "generator_state" in checkpoint:
            generator.set_state(checkpoint["generator_state"])
        if "torch_rng_state" in checkpoint:
            torch.set_rng_state(checkpoint["torch_rng_state"].cpu())
        logger.load_existing(completed_round, checkpoint.get("global_metrics"))
        start_round = completed_round + 1

    frida = FridaLossDetector(config.frida_z_threshold)
    model_state_bytes = sum(
        tensor.numel() * tensor.element_size() for tensor in global_state.values()
    )

    for round_idx in range(start_round, config.num_rounds + 1):
        round_start = time.perf_counter()
        process_start = time.process_time()
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
        base_state = clone_state(global_state)
        canary_loader = None
        if config.methodology_version == "frida_loss":
            offset = (round_idx - 1) * config.baseline_canary_size
            round_canaries = canary_indices[offset : offset + config.baseline_canary_size]
            canary_loader = DataLoader(
                Subset(train_set, round_canaries),
                batch_size=min(config.batch_size, config.baseline_canary_size),
                shuffle=False,
                num_workers=config.num_workers,
                pin_memory=config.pin_memory,
            )

        returned_states: dict[int, dict[str, torch.Tensor]] = {}
        deltas: dict[int, torch.Tensor] = {}
        local_stats: dict[int, dict[str, float]] = {}
        for client_id in range(config.num_clients):
            client_start = time.perf_counter()
            if client_id in free_riders:
                returned_state = attacker.fabricate(client_id, base_state, round_idx, generator)
                metrics = {"accuracy": float("nan"), "loss": float("nan")}
                local_steps = 0
            else:
                returned_state, metrics = train_local_model(
                    model, base_state, client_loaders[client_id], loss_fn, device, config
                )
                local_steps = config.local_epochs * len(client_loaders[client_id])
                if canary_loader is not None:
                    returned_state = train_extra_epochs(
                        model,
                        returned_state,
                        canary_loader,
                        loss_fn,
                        device,
                        config,
                        config.frida_canary_epochs,
                    )
                    local_steps += config.frida_canary_epochs * len(canary_loader)
            returned_states[client_id] = returned_state
            delta = flatten_delta(returned_state, base_state)
            deltas[client_id] = delta
            norm = float(delta.norm().item())
            norm_history[client_id] = 0.8 * norm_history[client_id] + 0.2 * norm
            metrics.update(
                {
                    "num_local_samples": len(client_loaders[client_id].dataset),
                    "local_steps": local_steps,
                    "local_compute_seconds": time.perf_counter() - client_start,
                    "delta_norm": norm,
                }
            )
            local_stats[client_id] = metrics

        synchronize(device)
        detection_started = time.perf_counter()
        if config.methodology_version == "frida_loss":
            if canary_loader is None:
                raise RuntimeError("FRIDA canary loader was not created")
            output = frida.detect(model, returned_states, canary_loader, device)
        else:
            torch.manual_seed(config.seed + round_idx)
            frad_inputs = FradInputs(
                computation=torch.tensor(
                    [local_stats[item]["local_compute_seconds"] for item in range(config.num_clients)]
                ),
                communication=torch.full((config.num_clients,), float(model_state_bytes)),
                data_quality=torch.tensor(
                    [
                        0.0
                        if not math.isfinite(local_stats[item]["accuracy"])
                        else local_stats[item]["accuracy"]
                        for item in range(config.num_clients)
                    ]
                ),
                history=torch.tensor(
                    [norm_history[item] for item in range(config.num_clients)]
                ),
            )
            output = FradDetector(
                epochs=config.frad_epochs,
                latent_dim=config.frad_latent_dim,
                components=config.frad_components,
                anomaly_quantile=1.0 - config.free_rider_pct,
            ).detect(frad_inputs, device)
        synchronize(device)
        detector_seconds = time.perf_counter() - detection_started

        predicted = {client_id for client_id, flagged in output.flags.items() if flagged}
        actual = free_riders
        tp = len(predicted & actual)
        fp = len(predicted - actual)
        fn = len(actual - predicted)
        tn = config.num_clients - tp - fp - fn
        cumulative["tp"] += tp
        cumulative["fp"] += fp
        cumulative["tn"] += tn
        cumulative["fn"] += fn
        for client_id in range(config.num_clients):
            times_evaluated[client_id] += 1
            if output.flags[client_id]:
                times_flagged[client_id] += 1
                first_flag_round.setdefault(client_id, round_idx)
            logger.client_rows.append(
                {
                    "round": round_idx,
                    "client_id": client_id,
                    "is_free_rider": int(client_id in free_riders),
                    "is_active": 1,
                    "local_accuracy": local_stats[client_id]["accuracy"],
                    "local_loss": local_stats[client_id]["loss"],
                    "num_local_samples": local_stats[client_id]["num_local_samples"],
                    "local_steps": local_stats[client_id]["local_steps"],
                    "local_compute_seconds": local_stats[client_id]["local_compute_seconds"],
                    "delta_norm": local_stats[client_id]["delta_norm"],
                    "detection_observation_round": round_idx,
                    "detection_score": output.scores[client_id],
                    "flagged": int(output.flags[client_id]),
                    "detection_reason": config.methodology_version,
                }
            )
        logger.detection_round_rows.append(
            {
                "round": round_idx,
                "evaluated_clients": config.num_clients,
                "true_positives": tp,
                "false_positives": fp,
                "true_negatives": tn,
                "false_negatives": fn,
                "detection_accuracy": safe_ratio(tp + tn, config.num_clients),
                "precision": safe_ratio(tp, tp + fp),
                "recall": safe_ratio(tp, tp + fn),
                "f1": f1_value(tp, fp, fn),
                "false_positive_rate": safe_ratio(fp, fp + tn),
                "false_negative_rate": safe_ratio(fn, fn + tp),
                "specificity": safe_ratio(tn, tn + fp),
                "detector_time_seconds": detector_seconds,
                "new_removals": 0,
                "new_rehabilitations": 0,
                "num_suspected": len(predicted),
                "num_candidates": 0,
            }
        )

        global_state = fedavg_delta(base_state, returned_states.values())
        model.load_state_dict(global_state)
        global_metrics = evaluate_model(model, eval_loader, loss_fn, device)
        resources = resource_snapshot(device)
        logger.global_rows.append(
            {
                "round": round_idx,
                "global_accuracy": global_metrics["accuracy"],
                "global_loss": global_metrics["loss"],
                "num_active_clients": config.num_clients,
                "num_suspected_clients": len(predicted),
                "num_candidate_clients": 0,
                "num_aggregated": config.num_clients,
                "detector_time_seconds": detector_seconds,
                "round_compute_seconds": time.perf_counter() - round_start,
                "round_time_seconds": 0.0,
                "process_cpu_seconds": 0.0,
                **resources,
            }
        )

        if config.save_checkpoints:
            checkpoint = {
                "round": round_idx,
                "model_state": clone_state(global_state),
                "global_state": clone_state(global_state),
                "active_clients": list(range(config.num_clients)),
                "penalties": {item: 0 for item in range(config.num_clients)},
                "times_flagged": times_flagged.copy(),
                "times_evaluated": times_evaluated.copy(),
                "first_flag_round": first_flag_round.copy(),
                "norm_history": norm_history.copy(),
                "cumulative": cumulative.copy(),
                "free_riders_ground_truth": sorted(free_riders),
                "global_metrics": logger.global_rows[-1],
                "config": config.to_dict(),
                "rng_state": rng.getstate(),
                "generator_state": generator.get_state(),
                "torch_rng_state": torch.get_rng_state(),
                "attacker_state": attacker.state_dict(),
            }
            save_rolling_checkpoint(
                checkpoint, logger.run_dir, round_idx, config.checkpoint_keep_last
            )
        logger.global_rows[-1]["round_time_seconds"] = time.perf_counter() - round_start
        logger.global_rows[-1]["process_cpu_seconds"] = time.process_time() - process_start
        logger.write_progress(round_idx, config.to_dict())
        if progress_callback is not None:
            progress_callback(
                {
                    "round": round_idx,
                    "total_rounds": config.num_rounds,
                    "phase": config.methodology_version,
                    "active_clients": config.num_clients,
                    "round_time_seconds": logger.global_rows[-1]["round_time_seconds"],
                    "detector_time_seconds": detector_seconds,
                    "global_accuracy": global_metrics["accuracy"],
                    "global_loss": global_metrics["loss"],
                    "device": str(device),
                    "new_flags": len(predicted),
                    "flagged_clients": len(predicted),
                    "new_removals": 0,
                    "new_rehabilitations": 0,
                    "suspected_clients": len(predicted),
                    "candidate_clients": 0,
                    **resources,
                }
            )

    summary = build_summary(config, free_riders, times_flagged, times_evaluated, cumulative)
    logger.summary_rows.append(summary)
    logger.client_summary_rows.extend(
        {
            "client_id": client_id,
            "is_free_rider": int(client_id in free_riders),
            "first_flag_round": first_flag_round.get(client_id, ""),
            "times_flagged": times_flagged[client_id],
            "times_evaluated": times_evaluated[client_id],
            "flag_rate": safe_ratio(times_flagged[client_id], times_evaluated[client_id]),
            "majority_classified_free_rider": int(
                times_flagged[client_id] * 2 >= times_evaluated[client_id]
            ),
        }
        for client_id in range(config.num_clients)
    )
    wall_end = time.perf_counter()
    final_global = logger.global_rows[-1] if logger.global_rows else {}
    run_config = config.to_dict()
    run_config.update(
        {
            "run_name": run_name,
            "device": str(device),
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": datetime.now().isoformat(),
            "total_wall_clock_seconds": wall_end - wall_start,
            "completed_rounds": len(logger.global_rows),
            "final_global_accuracy": final_global.get("global_accuracy"),
            "best_global_accuracy": max(
                (row["global_accuracy"] for row in logger.global_rows), default=None
            ),
            "final_global_loss": final_global.get("global_loss"),
            "average_round_time_seconds": average_field(logger.global_rows, "round_time_seconds"),
            "average_detector_time_seconds": average_field(
                logger.global_rows, "detector_time_seconds"
            ),
            "peak_process_rss_mb": max(
                (float(row["process_rss_mb"]) for row in logger.global_rows if row.get("process_rss_mb") != ""),
                default=None,
            ),
            "num_free_riders": len(free_riders),
            "classification_policy": "majority of per-round flags; clients are not removed",
            "hardware": hardware_info(device),
            **summary,
        }
    )
    logger.write_all(run_config)
    deleted = delete_successful_checkpoints(logger.run_dir)
    run_config["checkpoint_cleanup_on_success"] = True
    run_config["checkpoints_deleted_on_success"] = deleted
    logger.write_completion(run_config, len(logger.global_rows))
    return str(logger.run_dir)


def train_extra_epochs(
    model: nn.Module,
    initial_state: dict[str, torch.Tensor],
    loader: DataLoader,
    loss_fn: nn.Module,
    device: torch.device,
    config: ExperimentConfig,
    epochs: int,
) -> dict[str, torch.Tensor]:
    model.load_state_dict(initial_state)
    model.train()
    optimizer = torch.optim.SGD(
        model.parameters(), lr=config.learning_rate, momentum=config.momentum
    )
    for _ in range(epochs):
        for inputs, targets in loader:
            inputs = inputs.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(inputs), targets)
            loss.backward()
            optimizer.step()
    return clone_state(model.state_dict())


def build_summary(
    config: ExperimentConfig,
    free_riders: set[int],
    times_flagged: dict[int, int],
    times_evaluated: dict[int, int],
    cumulative: dict[str, int],
) -> dict[str, float | int | str]:
    predicted = {
        item
        for item in range(config.num_clients)
        if times_evaluated[item] and times_flagged[item] * 2 >= times_evaluated[item]
    }
    tp_clients = len(predicted & free_riders)
    fp_clients = len(predicted - free_riders)
    fn_clients = len(free_riders - predicted)
    tn_clients = config.num_clients - tp_clients - fp_clients - fn_clients
    return {
        "summary_semantics": "majority per-round classification; no client removal",
        "removed_free_riders": tp_clients,
        "removed_honest_clients": fp_clients,
        "missed_free_riders": fn_clients,
        "precision": safe_ratio(tp_clients, tp_clients + fp_clients),
        "recall": safe_ratio(tp_clients, tp_clients + fn_clients),
        "f1": f1_value(tp_clients, fp_clients, fn_clients),
        "detection_accuracy": safe_ratio(tp_clients + tn_clients, config.num_clients),
        "false_positive_removal_rate": safe_ratio(
            fp_clients, config.num_clients - len(free_riders)
        ),
        "per_round_precision": safe_ratio(cumulative["tp"], cumulative["tp"] + cumulative["fp"]),
        "per_round_recall": safe_ratio(cumulative["tp"], cumulative["tp"] + cumulative["fn"]),
        "per_round_f1": f1_value(cumulative["tp"], cumulative["fp"], cumulative["fn"]),
    }


def f1_value(tp: int, fp: int, fn: int) -> float:
    precision = safe_ratio(tp, tp + fp)
    recall = safe_ratio(tp, tp + fn)
    return safe_ratio(2.0 * precision * recall, precision + recall)


def average_field(rows: list[dict], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
    return sum(values) / len(values) if values else None


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)
