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
from server.detection import (
    DetectionResult,
    cosine_similarity,
    evaluate_update,
    evaluate_update_with_norm_threshold,
)
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
    batch_records: dict[str, list[dict]] = {"coverage": [], "suspicion_clean": []}
    batch_trap_states: dict[str, dict[str, torch.Tensor]] = {}
    batch_ids = {"coverage": 0, "suspicion_clean": 0}

    for round_idx in range(1, config.num_rounds + 1):
        round_start = time.perf_counter()
        active_this_round = active_clients[:]
        base_state = clone_state(global_state)
        selection = selector.select(round_idx, active_clients, penalties, times_flagged)
        trap_state = select_trap_state(
            selection.phase,
            base_state,
            config,
            generator,
            batch_trap_states,
            batch_ids,
        )
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

        active_norm_z_scores = build_norm_z_scores(deltas, config.zero_update_epsilon)
        reference = build_reference(selection.phase, selection.trapped_clients, selection.anchors, deltas)
        new_flags = 0
        removed_after_round: list[int] = []
        batch_phase = batch_mad_phase(selection.phase, config)
        suspicion_threshold = None
        if config.use_batch_mad_threshold and selection.phase == "suspicion_flagged":
            suspicion_threshold = build_mad_threshold(
                [float(deltas[client_id].norm().item()) for client_id in selection.anchors if client_id in deltas],
                config,
            )
            logger.threshold_rows.append(
                {
                    "round": round_idx,
                    "phase": selection.phase,
                    "batch_id": "",
                    "threshold_basis": "anchors",
                    "basis_client_count": suspicion_threshold["count"],
                    "checked_client_count": len(selection.checked_clients),
                    "median_norm": suspicion_threshold["median"],
                    "mad_norm": suspicion_threshold["mad"],
                    "k": config.mad_threshold_k,
                    "norm_threshold": suspicion_threshold["threshold"],
                    "trap_model_scope": "per_round",
                }
            )

        for client_id in active_this_round:
            was_trapped = client_id in selection.trapped_clients
            was_checked = client_id in selection.checked_clients
            norm = float(deltas[client_id].norm().item())
            detection = None
            if selection.phase != "warmup" and was_checked:
                if batch_phase:
                    similarity = cosine_similarity(deltas[client_id], reference)
                    client_row = build_client_row(
                        round_idx,
                        client_id,
                        free_riders,
                        was_trapped,
                        local_stats[client_id],
                        similarity,
                        "",
                        norm,
                        active_norm_z_scores.get(client_id, ""),
                        False,
                        "pending_batch_mad_threshold",
                        0,
                    )
                    logger.client_rows.append(client_row)
                    batch_records[batch_phase].append(
                        {
                            "round": round_idx,
                            "phase": selection.phase,
                            "batch_id": batch_ids[batch_phase],
                            "client_id": client_id,
                            "is_free_rider": client_id in free_riders,
                            "was_trapped": was_trapped,
                            "delta": deltas[client_id],
                            "reference": reference,
                            "cosine_similarity": similarity,
                            "delta_norm": norm,
                            "client_row": client_row,
                        }
                    )
                    continue
                if suspicion_threshold:
                    mad_score = build_mad_score(
                        norm,
                        suspicion_threshold["median"],
                        suspicion_threshold["mad"],
                        config.zero_update_epsilon,
                    )
                    detection = evaluate_update_with_norm_threshold(
                        deltas[client_id],
                        reference,
                        was_trapped,
                        config,
                        mad_score,
                        suspicion_threshold["threshold"],
                    )
                else:
                    detection = evaluate_update(
                        deltas[client_id],
                        reference,
                        was_trapped,
                        config,
                        active_norm_z_scores.get(client_id),
                    )
                new_flags += apply_detection_penalty(
                    detection,
                    client_id,
                    round_idx,
                    free_riders,
                    config,
                    penalties,
                    times_flagged,
                    removed_after_round,
                    logger,
                )

            penalty_added = detection.penalty if detection else 0
            threshold_row_info = None
            if detection and suspicion_threshold:
                threshold_row_info = {
                    **suspicion_threshold,
                    "basis": "anchors",
                    "batch_id": "",
                }
            logger.client_rows.append(
                build_client_row(
                    round_idx,
                    client_id,
                    free_riders,
                    was_trapped,
                    local_stats[client_id],
                    detection.cosine_similarity if detection else "",
                    detection.norm_z_score if detection else "",
                    detection.delta_norm if detection else norm,
                    active_norm_z_scores.get(client_id, ""),
                    detection.flagged if detection else False,
                    detection.reason if detection and detection.reason else "",
                    penalty_added,
                    threshold_row_info,
                )
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
                    "norm_z_score": "",
                    "delta_norm": "",
                    "active_norm_z_score": "",
                    "flagged": 0,
                    "detection_reason": "",
                    "penalty_added_this_round": 0,
                }
            )

        if batch_phase and should_flush_batch(batch_phase, selector, round_idx, config):
            batch_flags, batch_removals = flush_batch_mad_records(
                batch_phase,
                round_idx,
                batch_records[batch_phase],
                config,
                penalties,
                times_flagged,
                free_riders,
                removed_after_round,
                logger,
            )
            new_flags += batch_flags
            removed_after_round.extend(batch_removals)
            batch_records[batch_phase] = []
            batch_trap_states.pop(batch_phase, None)

        for client_id in range(config.num_clients):
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
            client_id
            for client_id in active_this_round
            if client_id not in selection.trapped_clients
            and not should_skip_fedavg(client_id, penalties, config)
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
                "num_skipped_by_penalty": sum(
                    1
                    for client_id in active_this_round
                    if client_id not in selection.trapped_clients
                    and should_skip_fedavg(client_id, penalties, config)
                ),
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


def batch_mad_phase(phase: str, config: ExperimentConfig) -> str | None:
    if config.use_batch_mad_threshold and phase in {"coverage", "suspicion_clean"}:
        return phase
    return None


def select_trap_state(
    phase: str,
    base_state: dict[str, torch.Tensor],
    config: ExperimentConfig,
    generator: torch.Generator,
    batch_trap_states: dict[str, dict[str, torch.Tensor]],
    batch_ids: dict[str, int],
) -> dict[str, torch.Tensor]:
    batch_phase = batch_mad_phase(phase, config)
    if not batch_phase or not config.same_trap_for_batch_sweeps:
        return make_trap_state(
            base_state, config.trap_noise_scale, config.trap_noise_floor, generator
        )
    if batch_phase not in batch_trap_states:
        batch_ids[batch_phase] += 1
        batch_trap_states[batch_phase] = make_trap_state(
            base_state, config.trap_noise_scale, config.trap_noise_floor, generator
        )
    return batch_trap_states[batch_phase]


def build_client_row(
    round_idx: int,
    client_id: int,
    free_riders: set[int],
    was_trapped: bool,
    local_stats: dict[str, float],
    cosine_similarity_value,
    norm_z_score_value,
    delta_norm_value,
    active_norm_z_score_value,
    flagged: bool,
    detection_reason: str,
    penalty_added: int,
    threshold_info: dict[str, float | int] | None = None,
) -> dict:
    row = {
        "round": round_idx,
        "client_id": client_id,
        "is_free_rider": int(client_id in free_riders),
        "was_trapped": int(was_trapped),
        "local_accuracy": local_stats["accuracy"],
        "local_loss": local_stats["loss"],
        "cosine_similarity": cosine_similarity_value,
        "norm_z_score": norm_z_score_value,
        "delta_norm": delta_norm_value,
        "active_norm_z_score": active_norm_z_score_value,
        "flagged": int(flagged),
        "detection_reason": detection_reason,
        "penalty_added_this_round": penalty_added,
    }
    if threshold_info:
        row.update(
            {
                "norm_threshold": threshold_info["threshold"],
                "threshold_median_norm": threshold_info["median"],
                "threshold_mad_norm": threshold_info["mad"],
                "threshold_k": threshold_info["k"],
                "threshold_basis": threshold_info["basis"],
                "batch_id": threshold_info.get("batch_id", ""),
            }
        )
    return row


def build_mad_threshold(norms: list[float], config: ExperimentConfig) -> dict[str, float | int]:
    if not norms:
        return {
            "count": 0,
            "median": 0.0,
            "mad": 0.0,
            "k": config.mad_threshold_k,
            "threshold": float("inf"),
        }
    tensor = torch.tensor(norms, dtype=torch.float32)
    median = float(torch.quantile(tensor, 0.5).item())
    mad = float(torch.quantile((tensor - median).abs(), 0.5).item())
    scale = max(mad, config.zero_update_epsilon)
    return {
        "count": len(norms),
        "median": median,
        "mad": mad,
        "k": config.mad_threshold_k,
        "threshold": median + config.mad_threshold_k * scale,
    }


def build_mad_score(norm: float, median: float, mad: float, epsilon: float) -> float:
    return abs(norm - median) / max(mad, epsilon)


def should_skip_fedavg(
    client_id: int, penalties: dict[int, int], config: ExperimentConfig
) -> bool:
    if config.fedavg_skip_penalty_threshold is None:
        return False
    return penalties.get(client_id, 0) > config.fedavg_skip_penalty_threshold


def should_flush_batch(
    phase: str, selector: TrapSelector, round_idx: int, config: ExperimentConfig
) -> bool:
    if round_idx >= config.num_rounds:
        return True
    if phase == "coverage":
        return not selector.coverage_queue
    if phase == "suspicion_clean":
        return not selector.clean_queue
    return False


def apply_detection_penalty(
    detection: DetectionResult,
    client_id: int,
    round_idx: int,
    free_riders: set[int],
    config: ExperimentConfig,
    penalties: dict[int, int],
    times_flagged: dict[int, int],
    removed_after_round: list[int],
    logger: RunLogger,
) -> int:
    penalties[client_id] += detection.penalty
    if not detection.flagged:
        return 0
    times_flagged[client_id] += 1
    if (
        penalties[client_id] >= config.removal_threshold
        and client_id not in removed_after_round
    ):
        removed_after_round.append(client_id)
        logger.removal_rows.append(
            {
                "round": round_idx,
                "client_id": client_id,
                "is_free_rider": int(client_id in free_riders),
                "final_penalty": penalties[client_id],
            }
        )
    return 1


def flush_batch_mad_records(
    phase: str,
    round_idx: int,
    records: list[dict],
    config: ExperimentConfig,
    penalties: dict[int, int],
    times_flagged: dict[int, int],
    free_riders: set[int],
    already_removed: list[int],
    logger: RunLogger,
) -> tuple[int, list[int]]:
    if not records:
        return 0, []

    threshold_info = build_mad_threshold(
        [float(record["delta_norm"]) for record in records], config
    )
    threshold_basis = (
        "coverage_batch_all_checked"
        if phase == "coverage"
        else "clean_batch_all_checked"
    )
    batch_id = records[0]["batch_id"]
    logger.threshold_rows.append(
        {
            "round": round_idx,
            "phase": phase,
            "batch_id": batch_id,
            "threshold_basis": threshold_basis,
            "basis_client_count": threshold_info["count"],
            "checked_client_count": len(records),
            "median_norm": threshold_info["median"],
            "mad_norm": threshold_info["mad"],
            "k": config.mad_threshold_k,
            "norm_threshold": threshold_info["threshold"],
            "trap_model_scope": "same_for_batch",
        }
    )

    flags = 0
    removed: list[int] = []
    for record in records:
        score = build_mad_score(
            float(record["delta_norm"]),
            float(threshold_info["median"]),
            float(threshold_info["mad"]),
            config.zero_update_epsilon,
        )
        detection = evaluate_update_with_norm_threshold(
            record["delta"],
            record["reference"],
            record["was_trapped"],
            config,
            score,
            float(threshold_info["threshold"]),
        )
        if detection.flagged and phase in {"coverage", "suspicion_clean"}:
            detection.penalty = config.penalty_normal_flag
        row = record["client_row"]
        row.update(
            {
                "cosine_similarity": detection.cosine_similarity,
                "norm_z_score": detection.norm_z_score,
                "delta_norm": detection.delta_norm,
                "flagged": int(detection.flagged),
                "detection_reason": detection.reason if detection.reason else "",
                "penalty_added_this_round": detection.penalty,
                "norm_threshold": threshold_info["threshold"],
                "threshold_median_norm": threshold_info["median"],
                "threshold_mad_norm": threshold_info["mad"],
                "threshold_k": config.mad_threshold_k,
                "threshold_basis": threshold_basis,
                "batch_id": batch_id,
            }
        )
        before = len(removed)
        flags += apply_detection_penalty(
            detection,
            record["client_id"],
            round_idx,
            free_riders,
            config,
            penalties,
            times_flagged,
            removed,
            logger,
        )
        if len(removed) > before and removed[-1] in already_removed:
            removed.pop()
    return flags, removed


def build_norm_z_scores(
    deltas: dict[int, torch.Tensor], epsilon: float
) -> dict[int, float]:
    if not deltas:
        return {}
    client_ids = list(deltas)
    norms = torch.tensor(
        [float(deltas[client_id].norm().item()) for client_id in client_ids],
        dtype=torch.float32,
    )
    median = norms.median()
    mad = (norms - median).abs().median()
    scale = (mad * 1.4826).clamp_min(epsilon)
    z_scores = ((norms - median).abs() / scale).tolist()
    return {
        client_id: float(z_score)
        for client_id, z_score in zip(client_ids, z_scores, strict=True)
    }


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
