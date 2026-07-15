from __future__ import annotations

import math
import random
import time
from datetime import datetime

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Subset

from clients.attacks import FreeRiderAttacker, flatten_delta
from config import ExperimentConfig
from data.loaders import get_datasets, make_eval_loader
from data.partition import partition_dataset
from logging_utils import RunLogger
from models.architectures import get_model
from server.aggregation import clone_state, fedavg_delta, make_trap_state
from server.detection import evaluate_update
from server.trap_selection import TrapSelector


def run_experiment(config: ExperimentConfig) -> str:
    config.validate()
    run_name = config.resolved_run_name()
    start_time = datetime.now()
    wall_start = time.perf_counter()

    set_global_seed(config.seed)
    device = resolve_device(config.device)
    generator = torch.Generator(device=device)
    generator.manual_seed(config.seed)
    rng = random.Random(config.seed)

    train_set, test_set = get_datasets(config)
    partitions = partition_dataset(train_set, config)
    client_loaders = [
        make_client_loader(train_set, indices, config, seed=config.seed + client_id)
        for client_id, indices in enumerate(partitions)
    ]
    eval_loader = make_eval_loader(config, test_set)

    model = get_model(config.dataset).to(device)
    global_state = clone_state(model.state_dict())
    loss_fn = nn.CrossEntropyLoss()

    free_rider_count = math.ceil(config.free_rider_pct * config.num_clients)
    free_riders = set(rng.sample(range(config.num_clients), free_rider_count))
    attacker = FreeRiderAttacker(config, device)
    selector = TrapSelector(config, rng)
    logger = RunLogger(config, run_name)

    active_clients = list(range(config.num_clients))
    penalties = {client_id: 0 for client_id in range(config.num_clients)}
    times_flagged = {client_id: 0 for client_id in range(config.num_clients)}
    times_trapped = {client_id: 0 for client_id in range(config.num_clients)}

    for round_idx in range(1, config.num_rounds + 1):
        round_start = time.perf_counter()
        active_this_round = active_clients[:]
        base_state = clone_state(global_state)
        trap_state = make_trap_state(
            base_state, config.trap_noise_scale, config.trap_noise_floor, generator
        )
        selection = selector.select(round_idx, active_clients, penalties, times_flagged)
        logger.log_trap_matrix_row(
            round_idx, selection.phase, selection.trapped_clients, config.num_clients
        )

        returned_states: dict[int, dict[str, torch.Tensor]] = {}
        deltas: dict[int, torch.Tensor] = {}
        local_stats: dict[int, dict[str, float]] = {}

        for client_id in active_this_round:
            was_trapped = client_id in selection.trapped_clients
            received_state = trap_state if was_trapped else base_state
            if was_trapped:
                times_trapped[client_id] += 1

            if client_id in free_riders:
                attacker.observe_received(client_id, received_state, was_trapped)
                returned_state = attacker.fabricate(
                    client_id, received_state, round_idx, generator
                )
                metrics = evaluate_state_on_loader(
                    model, returned_state, client_loaders[client_id], loss_fn, device, config
                )
            else:
                returned_state, metrics = train_local_model(
                    model,
                    received_state,
                    client_loaders[client_id],
                    loss_fn,
                    device,
                    config,
                )

            returned_states[client_id] = returned_state
            deltas[client_id] = flatten_delta(returned_state, received_state)
            local_stats[client_id] = metrics

        reference = build_reference(selection.phase, selection.trapped_clients, selection.anchors, deltas)
        new_flags = 0
        removed_after_round: list[int] = []

        for client_id in active_this_round:
            was_trapped = client_id in selection.trapped_clients
            was_checked = client_id in selection.checked_clients
            detection = None
            if selection.phase != "warmup" and was_checked:
                detection = evaluate_update(deltas[client_id], reference, was_trapped, config)
                penalties[client_id] += detection.penalty
                if detection.flagged:
                    times_flagged[client_id] += 1
                    new_flags += 1
                if penalties[client_id] > config.removal_threshold:
                    removed_after_round.append(client_id)
                    logger.removal_rows.append(
                        {
                            "round": round_idx,
                            "client_id": client_id,
                            "is_free_rider": int(client_id in free_riders),
                            "final_penalty": penalties[client_id],
                        }
                    )

            penalty_added = detection.penalty if detection else 0
            logger.client_rows.append(
                {
                    "round": round_idx,
                    "client_id": client_id,
                    "is_free_rider": int(client_id in free_riders),
                    "was_trapped": int(was_trapped),
                    "local_accuracy": local_stats[client_id]["accuracy"],
                    "local_loss": local_stats[client_id]["loss"],
                    "cosine_similarity": detection.cosine_similarity if detection else "",
                    "delta_norm": detection.delta_norm if detection else float(deltas[client_id].norm().item()),
                    "flagged": int(detection.flagged) if detection else 0,
                    "penalty_added_this_round": penalty_added,
                }
            )
            logger.penalty_rows.append(
                {
                    "round": round_idx,
                    "client_id": client_id,
                    "cumulative_penalty": penalties[client_id],
                    "times_flagged_so_far": times_flagged[client_id],
                    "times_trapped_so_far": times_trapped[client_id],
                }
            )

        inactive_this_round = [
            client_id
            for client_id in range(config.num_clients)
            if client_id not in set(active_this_round)
        ]
        for client_id in inactive_this_round:
            logger.client_rows.append(
                {
                    "round": round_idx,
                    "client_id": client_id,
                    "is_free_rider": int(client_id in free_riders),
                    "was_trapped": 0,
                    "local_accuracy": "",
                    "local_loss": "",
                    "cosine_similarity": "",
                    "delta_norm": "",
                    "flagged": 0,
                    "penalty_added_this_round": 0,
                }
            )
            logger.penalty_rows.append(
                {
                    "round": round_idx,
                    "client_id": client_id,
                    "cumulative_penalty": penalties[client_id],
                    "times_flagged_so_far": times_flagged[client_id],
                    "times_trapped_so_far": times_trapped[client_id],
                }
            )

        aggregated_clients = [
            client_id for client_id in active_this_round if client_id not in selection.trapped_clients
        ]
        global_state = fedavg_delta(base_state, [returned_states[client_id] for client_id in aggregated_clients])
        model.load_state_dict(global_state)

        active_clients = [
            client_id for client_id in active_this_round if client_id not in set(removed_after_round)
        ]
        selector.observe_round(selection.phase, new_flags, active_clients)

        global_metrics = evaluate_model(model, eval_loader, loss_fn, device)
        logger.global_rows.append(
            {
                "round": round_idx,
                "global_accuracy": global_metrics["accuracy"],
                "global_loss": global_metrics["loss"],
                "num_active_clients": len(active_clients),
                "num_trapped": len(selection.trapped_clients),
                "num_aggregated": len(aggregated_clients),
                "round_time_seconds": time.perf_counter() - round_start,
            }
        )

        if not active_clients:
            break

    wall_end = time.perf_counter()
    end_time = datetime.now()
    detection_summary = build_detection_summary(config, free_riders, active_clients)
    logger.summary_rows.append(detection_summary)
    run_config = config.to_dict()
    run_config.update(
        {
            "run_name": run_name,
            "seed": config.seed,
            "device": str(device),
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "total_wall_clock_seconds": wall_end - wall_start,
            "removal_threshold": config.removal_threshold,
            "num_free_riders": len(free_riders),
            **detection_summary,
        }
    )
    logger.write_all(run_config)
    return str(logger.run_dir)


def set_global_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def resolve_device(device_setting: str) -> torch.device:
    if device_setting == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device_setting == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("device='cuda' was requested, but CUDA is not available.")
    return torch.device(device_setting)


def make_client_loader(dataset, indices: list[int], config: ExperimentConfig, seed: int) -> DataLoader:
    generator = torch.Generator()
    generator.manual_seed(seed)
    return DataLoader(
        Subset(dataset, indices),
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
        pin_memory=config.pin_memory,
        generator=generator,
    )


def make_optimizer(model: nn.Module, config: ExperimentConfig):
    if config.optimizer == "sgd":
        return torch.optim.SGD(
            model.parameters(), lr=config.learning_rate, momentum=config.momentum
        )
    if config.optimizer == "adam":
        return torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    raise ValueError(f"Unsupported optimizer: {config.optimizer}")


def train_local_model(
    model_template: nn.Module,
    initial_state: dict[str, torch.Tensor],
    loader: DataLoader,
    loss_fn: nn.Module,
    device: torch.device,
    config: ExperimentConfig,
) -> tuple[dict[str, torch.Tensor], dict[str, float]]:
    model_template.load_state_dict(initial_state)
    model_template.train()
    optimizer = make_optimizer(model_template, config)
    total_loss = 0.0
    total_correct = 0
    total_seen = 0

    for _ in range(config.local_epochs):
        for inputs, targets in loader:
            inputs = inputs.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            logits = model_template(inputs)
            loss = loss_fn(logits, targets)
            loss.backward()
            optimizer.step()

            batch_size = targets.size(0)
            total_loss += float(loss.item()) * batch_size
            total_correct += int((logits.argmax(dim=1) == targets).sum().item())
            total_seen += batch_size

    if total_seen == 0:
        return clone_state(initial_state), {"accuracy": float("nan"), "loss": float("nan")}
    return clone_state(model_template.state_dict()), {
        "accuracy": total_correct / total_seen,
        "loss": total_loss / total_seen,
    }


@torch.no_grad()
def evaluate_state_on_loader(
    model: nn.Module,
    state: dict[str, torch.Tensor],
    loader: DataLoader,
    loss_fn: nn.Module,
    device: torch.device,
    config: ExperimentConfig,
) -> dict[str, float]:
    model.load_state_dict(state)
    model.eval()
    total_loss = 0.0
    total_correct = 0
    total_seen = 0
    for batch_idx, (inputs, targets) in enumerate(loader):
        if batch_idx >= config.local_eval_batches:
            break
        inputs = inputs.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        logits = model(inputs)
        loss = loss_fn(logits, targets)
        batch_size = targets.size(0)
        total_loss += float(loss.item()) * batch_size
        total_correct += int((logits.argmax(dim=1) == targets).sum().item())
        total_seen += batch_size
    if total_seen == 0:
        return {"accuracy": float("nan"), "loss": float("nan")}
    return {"accuracy": total_correct / total_seen, "loss": total_loss / total_seen}


@torch.no_grad()
def evaluate_model(
    model: nn.Module, loader: DataLoader, loss_fn: nn.Module, device: torch.device
) -> dict[str, float]:
    model.eval()
    total_loss = 0.0
    total_correct = 0
    total_seen = 0
    for inputs, targets in loader:
        inputs = inputs.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        logits = model(inputs)
        loss = loss_fn(logits, targets)
        batch_size = targets.size(0)
        total_loss += float(loss.item()) * batch_size
        total_correct += int((logits.argmax(dim=1) == targets).sum().item())
        total_seen += batch_size
    return {"accuracy": total_correct / total_seen, "loss": total_loss / total_seen}


def build_reference(
    phase: str,
    trapped_clients: set[int],
    anchors: set[int],
    deltas: dict[int, torch.Tensor],
) -> torch.Tensor:
    if phase in {"coverage", "suspicion_clean"}:
        vectors = [deltas[client_id] for client_id in trapped_clients]
        return torch.stack(vectors).mean(dim=0) if vectors else _empty_reference(deltas)
    if phase == "suspicion_flagged":
        anchor_vectors = [deltas[client_id] for client_id in anchors if client_id in deltas]
        if anchor_vectors:
            return torch.stack(anchor_vectors).mean(dim=0)
        trapped_vectors = [deltas[client_id] for client_id in trapped_clients]
        return torch.stack(trapped_vectors).mean(dim=0) if trapped_vectors else _empty_reference(deltas)
    return _empty_reference(deltas)


def _empty_reference(deltas: dict[int, torch.Tensor]) -> torch.Tensor:
    if deltas:
        first = next(iter(deltas.values()))
        return torch.zeros_like(first)
    return torch.empty(0)


def build_detection_summary(
    config: ExperimentConfig, free_riders: set[int], active_clients: list[int]
) -> dict[str, float | int]:
    active = set(active_clients)
    removed = set(range(config.num_clients)) - active
    removed_free_riders = len(removed & free_riders)
    removed_honest = len(removed - free_riders)
    missed_free_riders = len(free_riders - removed)
    honest_count = config.num_clients - len(free_riders)
    precision_denominator = removed_free_riders + removed_honest
    recall_denominator = removed_free_riders + missed_free_riders
    precision = removed_free_riders / precision_denominator if precision_denominator else 0.0
    recall = removed_free_riders / recall_denominator if recall_denominator else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    false_positive_rate = removed_honest / honest_count if honest_count else 0.0
    return {
        "removed_free_riders": removed_free_riders,
        "removed_honest_clients": removed_honest,
        "missed_free_riders": missed_free_riders,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_removal_rate": false_positive_rate,
    }
