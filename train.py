from __future__ import annotations

import math
import os
import platform
import random
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import Callable

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
    apply_surveillance_penalties,
    combine_coverage_checks,
    evaluate_suspicion_group,
    evaluate_updates,
    evaluate_zero_updates_only,
    merge_detection_results,
    should_rehabilitate,
)
from server.trap_selection import TrapSelector


def run_experiment(
    config: ExperimentConfig,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> str:
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
    first_flag_round: dict[int, int] = {}
    first_removal_round: dict[int, int] = {}
    coverage_trap_state: dict[str, torch.Tensor] | None = None
    coverage_deltas: dict[int, list[torch.Tensor]] = {}
    coverage_observation_rounds: dict[int, list[int]] = {}
    surveillance_trap_state: dict[str, torch.Tensor] | None = None
    surveillance_deltas: dict[int, torch.Tensor] = {}
    surveillance_observation_rounds: dict[int, int] = {}
    suspected_clients: set[int] = set()
    dodge_probe_counts = {client_id: 0 for client_id in range(config.num_clients)}
    dodge_flag_counts = {client_id: 0 for client_id in range(config.num_clients)}
    lifetime_trap_flags = {client_id: 0 for client_id in range(config.num_clients)}
    start_round = 1

    if config.resume_checkpoint:
        checkpoint_path = Path(config.resume_checkpoint)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Resume checkpoint not found: {checkpoint_path}")
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        checkpoint_config = checkpoint.get("config", {})
        if checkpoint_config.get("methodology_version") != config.methodology_version:
            raise ValueError(
                "Checkpoint methodology version does not match this implementation; "
                "start a fresh run instead of mixing detector protocols."
            )
        if checkpoint_config.get("attack_type") != config.attack_type:
            raise ValueError("Resume checkpoint attack_type does not match the requested config.")
        if checkpoint_config.get("dataset") != config.dataset:
            raise ValueError("Resume checkpoint dataset does not match the requested config.")
        if checkpoint_config.get("distribution") != config.distribution:
            raise ValueError(
                "Resume checkpoint distribution does not match the requested config."
            )
        completed_round = int(checkpoint["round"])
        if completed_round >= config.num_rounds:
            raise ValueError("Resume checkpoint already reached the configured num_rounds.")
        model.load_state_dict(checkpoint["model_state"])
        global_state = clone_state(checkpoint["global_state"])
        active_clients = [int(client_id) for client_id in checkpoint["active_clients"]]
        penalties = {int(client_id): int(value) for client_id, value in checkpoint["penalties"].items()}
        times_flagged = {
            int(client_id): int(value) for client_id, value in checkpoint["times_flagged"].items()
        }
        times_trapped = {
            int(client_id): int(value) for client_id, value in checkpoint["times_trapped"].items()
        }
        free_riders = {int(client_id) for client_id in checkpoint["free_riders_ground_truth"]}
        logger.load_existing(completed_round, checkpoint.get("global_metrics"))
        start_round = completed_round + 1
        if "selector_state" in checkpoint:
            selector.load_state_dict(checkpoint["selector_state"])
            coverage_trap_state = checkpoint.get("coverage_trap_state")
            coverage_deltas = {
                int(client_id): [delta.detach().clone() for delta in values]
                for client_id, values in checkpoint.get("coverage_deltas", {}).items()
            }
            coverage_observation_rounds = {
                int(client_id): [int(value) for value in values]
                for client_id, values in checkpoint.get(
                    "coverage_observation_rounds", {}
                ).items()
            }
            surveillance_trap_state = checkpoint.get("surveillance_trap_state")
            surveillance_deltas = {
                int(client_id): delta.detach().clone()
                for client_id, delta in checkpoint.get("surveillance_deltas", {}).items()
            }
            surveillance_observation_rounds = {
                int(client_id): int(value)
                for client_id, value in checkpoint.get(
                    "surveillance_observation_rounds", {}
                ).items()
            }
            suspected_clients = {
                int(client_id) for client_id in checkpoint.get("suspected_clients", [])
            }
            dodge_probe_counts.update(
                {int(key): int(value) for key, value in checkpoint.get("dodge_probe_counts", {}).items()}
            )
            dodge_flag_counts.update(
                {int(key): int(value) for key, value in checkpoint.get("dodge_flag_counts", {}).items()}
            )
            lifetime_trap_flags.update(
                {int(key): int(value) for key, value in checkpoint.get("lifetime_trap_flags", {}).items()}
            )
            first_flag_round.update(
                {int(key): int(value) for key, value in checkpoint.get("first_flag_round", {}).items()}
            )
            first_removal_round.update(
                {
                    int(key): int(value)
                    for key, value in checkpoint.get("first_removal_round", {}).items()
                }
            )
        else:
            raise ValueError(
                "This methodology version requires persisted selector and probe state."
            )
        if "rng_state" in checkpoint:
            rng.setstate(checkpoint["rng_state"])
        if "generator_state" in checkpoint:
            generator.set_state(checkpoint["generator_state"])
        if "attacker_state" in checkpoint:
            attacker.load_state_dict(checkpoint["attacker_state"])

    for round_idx in range(start_round, config.num_rounds + 1):
        round_start = time.perf_counter()
        process_start = time.process_time()
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
        active_this_round = active_clients[:]
        base_state = clone_state(global_state)
        selection = selector.select(
            round_idx, active_clients, penalties, times_flagged, suspected_clients
        )
        client_trap_states: dict[int, dict[str, torch.Tensor]] = {}
        if selection.phase == "coverage":
            if coverage_trap_state is None:
                coverage_trap_state = make_trap_state(
                    base_state,
                    config.trap_noise_scale,
                    config.trap_noise_floor,
                    generator,
                )
            trap_state = coverage_trap_state
        else:
            trap_state = base_state
            if selection.surveillance_clients:
                if surveillance_trap_state is None:
                    surveillance_trap_state = make_trap_state(
                        base_state,
                        config.trap_noise_scale,
                        config.trap_noise_floor,
                        generator,
                    )
                for client_id in selection.surveillance_clients:
                    client_trap_states[client_id] = surveillance_trap_state
            for suspects, anchors in selection.suspicion_groups:
                group_trap_state = make_trap_state(
                    base_state,
                    config.trap_noise_scale,
                    config.trap_noise_floor,
                    generator,
                )
                for client_id in suspects | anchors:
                    client_trap_states[client_id] = group_trap_state
        logger.log_trap_matrix_row(
            round_idx, selection.phase, selection.trapped_clients, config.num_clients
        )
        if selection.phase == "coverage":
            for client_id in selection.trapped_clients:
                logger.trap_assignment_rows.append(
                    {
                        "round": round_idx,
                        "client_id": client_id,
                        "phase": selection.phase,
                        "role": "initial_coverage",
                        "group_id": "coverage",
                    }
                )
        else:
            for group_id, (suspects, anchors) in enumerate(selection.suspicion_groups):
                for client_id in suspects:
                    logger.trap_assignment_rows.append(
                        {
                            "round": round_idx,
                            "client_id": client_id,
                            "phase": selection.phase,
                            "role": "suspect",
                            "group_id": group_id,
                        }
                    )
                for client_id in anchors:
                    logger.trap_assignment_rows.append(
                        {
                            "round": round_idx,
                            "client_id": client_id,
                            "phase": selection.phase,
                            "role": "anchor",
                            "group_id": group_id,
                        }
                    )
            for client_id in selection.surveillance_clients:
                logger.trap_assignment_rows.append(
                    {
                        "round": round_idx,
                        "client_id": client_id,
                        "phase": selection.phase,
                        "role": "surveillance",
                        "group_id": "Y",
                    }
                )

        returned_states: dict[int, dict[str, torch.Tensor]] = {}
        deltas: dict[int, torch.Tensor] = {}
        local_stats: dict[int, dict[str, float]] = {}

        for client_id in active_this_round:
            client_start = time.perf_counter()
            was_trapped = client_id in selection.trapped_clients
            received_state = (
                trap_state
                if selection.phase == "coverage" and was_trapped
                else client_trap_states.get(client_id, base_state)
            )
            if was_trapped:
                times_trapped[client_id] += 1

            if client_id in free_riders:
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
            metrics["num_local_samples"] = len(client_loaders[client_id].dataset)
            metrics["local_steps"] = (
                config.local_epochs * len(client_loaders[client_id])
                if client_id not in free_riders
                else 0
            )
            metrics["local_compute_seconds"] = time.perf_counter() - client_start
            local_stats[client_id] = metrics

        reference = build_reference(selection.phase, selection.trapped_clients, selection.anchors, deltas)
        new_flags = 0
        removed_after_round: list[int] = []

        detection_results = {}
        detection_rounds_used: dict[int, int] = {}
        coverage_checks_used: dict[int, int] = {}
        coverage_flags_used: dict[int, int] = {}
        decision_flag_counts: dict[int, int] = {}
        trap_flag_counts: dict[int, int] = {}
        suspicion_probed: set[int] = set()
        if selection.phase == "coverage":
            for client_id in selection.trapped_clients:
                coverage_deltas.setdefault(client_id, []).append(deltas[client_id])
                coverage_observation_rounds.setdefault(client_id, []).append(round_idx)
            if selection.coverage_complete:
                probe_deltas: dict[int, torch.Tensor] = {}
                client_probe_ids: dict[int, list[int]] = {}
                probe_id = 0
                for client_id, client_deltas in coverage_deltas.items():
                    if client_id not in set(active_this_round):
                        continue
                    for delta in client_deltas:
                        probe_deltas[probe_id] = delta
                        client_probe_ids.setdefault(client_id, []).append(probe_id)
                        probe_id += 1
                coverage_reference = build_reference(
                    "coverage", set(probe_deltas), set(), probe_deltas
                )
                probe_results = evaluate_updates(
                    probe_deltas,
                    coverage_reference,
                    set(probe_deltas),
                    config,
                )
                coverage_checks_used = {
                    client_id: len(probe_ids)
                    for client_id, probe_ids in client_probe_ids.items()
                }
                coverage_flags_used = {
                    client_id: sum(probe_results[item].flagged for item in probe_ids)
                    for client_id, probe_ids in client_probe_ids.items()
                }
                decision_flag_counts.update(coverage_flags_used)
                trap_flag_counts.update(coverage_flags_used)
                if config.coverage_checks_per_client == 1:
                    detection_results = {
                        client_id: probe_results[probe_ids[0]]
                        for client_id, probe_ids in client_probe_ids.items()
                    }
                else:
                    detection_results = {
                        client_id: combine_coverage_checks(
                            [probe_results[item] for item in probe_ids]
                        )
                        for client_id, probe_ids in client_probe_ids.items()
                    }
                detection_rounds_used = {
                    client_id: max(coverage_observation_rounds[client_id])
                    for client_id in client_probe_ids
                }
            ordinary_clients = set(active_this_round) - selection.trapped_clients
            ordinary_zero_results = evaluate_zero_updates_only(
                {client_id: deltas[client_id] for client_id in ordinary_clients},
                config,
            )
            for client_id, result in ordinary_zero_results.items():
                detection_results[client_id] = merge_detection_results(
                    detection_results.get(client_id), result
                )
                decision_flag_counts[client_id] = decision_flag_counts.get(client_id, 0) + 1
                detection_rounds_used[client_id] = round_idx
        elif selection.phase == "warmup":
            # Trap selection is inactive, but server-observed checks still run.
            detection_results = evaluate_updates(
                deltas,
                reference,
                selection.trapped_clients,
                config,
            )
            detection_rounds_used = {
                client_id: round_idx for client_id in active_this_round
            }
        else:
            # Every suspicious group has its own fresh trap and is evaluated
            # only against the low-suspicion anchors that received that trap.
            for suspects, anchors in selection.suspicion_groups:
                suspicion_probed.update(suspects)
                group_results = evaluate_suspicion_group(
                    deltas, suspects, anchors, config
                )
                detection_results.update(group_results)
                for client_id in group_results:
                    if group_results[client_id].flagged:
                        decision_flag_counts[client_id] = 1
                        trap_flag_counts[client_id] = 1
                    detection_rounds_used[client_id] = round_idx

            # Exact send-back remains detectable even for ordinary clients that
            # did not receive a trap in this round.
            ordinary_clients = set(active_this_round) - selection.trapped_clients
            ordinary_zero_results = evaluate_zero_updates_only(
                {client_id: deltas[client_id] for client_id in ordinary_clients},
                config,
            )
            detection_results.update(ordinary_zero_results)
            for client_id in ordinary_zero_results:
                decision_flag_counts[client_id] = 1
                detection_rounds_used[client_id] = round_idx

            for client_id in selection.surveillance_clients:
                surveillance_deltas[client_id] = deltas[client_id]
                surveillance_observation_rounds[client_id] = round_idx
            if selection.surveillance_complete:
                eligible_surveillance = (
                    set(surveillance_deltas)
                    & set(active_this_round)
                    - suspected_clients
                    - suspicion_probed
                    - selection.anchors
                )
                eligible_deltas = {
                    client_id: surveillance_deltas[client_id]
                    for client_id in eligible_surveillance
                }
                eligible_rounds = {
                    client_id: surveillance_observation_rounds[client_id]
                    for client_id in eligible_surveillance
                }
                surveillance_reference = build_reference(
                    "coverage",
                    eligible_surveillance,
                    set(),
                    eligible_deltas,
                )
                surveillance_results = evaluate_updates(
                    eligible_deltas,
                    surveillance_reference,
                    eligible_surveillance,
                    config,
                )
                surveillance_results = apply_surveillance_penalties(
                    surveillance_results, config
                )
                for client_id, result in surveillance_results.items():
                    detection_results[client_id] = merge_detection_results(
                        detection_results.get(client_id), result
                    )
                    if result.flagged:
                        decision_flag_counts[client_id] = (
                            decision_flag_counts.get(client_id, 0) + 1
                        )
                        trap_flag_counts[client_id] = trap_flag_counts.get(client_id, 0) + 1
                detection_rounds_used.update(eligible_rounds)
                coverage_checks_used.update(
                    {client_id: 1 for client_id in surveillance_results}
                )
                coverage_flags_used.update(
                    {
                        client_id: int(result.flagged)
                        for client_id, result in surveillance_results.items()
                    }
                )

        for client_id in suspicion_probed:
            dodge_probe_counts[client_id] += 1
            if detection_results[client_id].flagged:
                dodge_flag_counts[client_id] += 1

        for client_id in active_this_round:
            was_trapped = client_id in selection.trapped_clients
            detection = detection_results.get(client_id)
            if detection is not None:
                if detection.flagged:
                    penalties[client_id] += detection.penalty
                    flag_count = decision_flag_counts.get(client_id, 1)
                    times_flagged[client_id] += flag_count
                    lifetime_trap_flags[client_id] += trap_flag_counts.get(
                        client_id,
                        int(was_trapped),
                    )
                    if client_id not in suspected_clients:
                        suspected_clients.add(client_id)
                        dodge_probe_counts[client_id] = 0
                        dodge_flag_counts[client_id] = 0
                    first_flag_round.setdefault(client_id, round_idx)
                    new_flags += flag_count
                    logger.detection_event_rows.append(
                        {
                            "decision_round": round_idx,
                            "observation_round": detection_rounds_used.get(client_id, round_idx),
                            "client_id": client_id,
                            "is_free_rider": int(client_id in free_riders),
                            "was_trapped": int(
                                client_id in selection.trapped_clients
                                or selection.phase == "coverage"
                                or coverage_checks_used.get(client_id, 0)
                            ),
                            "reason": detection.reason,
                            "delta_norm": detection.delta_norm,
                            "norm_z_score": detection.norm_z_score,
                            "loss": "",
                            "loss_z_score": detection.loss_z_score,
                            "coverage_checks": coverage_checks_used.get(client_id, ""),
                            "coverage_flags": coverage_flags_used.get(client_id, ""),
                            "penalty": detection.penalty,
                        }
                    )
                if penalties[client_id] >= config.removal_threshold:
                    removed_after_round.append(client_id)
                    suspected_clients.discard(client_id)
                    first_removal_round.setdefault(client_id, round_idx)
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
                    "num_local_samples": local_stats[client_id]["num_local_samples"],
                    "local_steps": local_stats[client_id]["local_steps"],
                    "local_compute_seconds": local_stats[client_id]["local_compute_seconds"],
                    "cosine_similarity": detection.cosine_similarity if detection else "",
                    "delta_norm": detection.delta_norm if detection else float(deltas[client_id].norm().item()),
                    "norm_z_score": detection.norm_z_score if detection else "",
                    "norm_median": detection.norm_median if detection else "",
                    "norm_mad": detection.norm_mad if detection else "",
                    "loss_z_score": detection.loss_z_score if detection else "",
                    "loss_median": detection.loss_median if detection else "",
                    "loss_mad": detection.loss_mad if detection else "",
                    "detection_observation_round": detection_rounds_used.get(client_id, ""),
                    "detection_loss": "",
                    "detection_reason": detection.reason if detection and detection.reason else "",
                    "coverage_checks": coverage_checks_used.get(client_id, ""),
                    "coverage_flags": coverage_flags_used.get(client_id, ""),
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
                    "num_local_samples": "",
                    "local_steps": "",
                    "local_compute_seconds": "",
                    "cosine_similarity": "",
                    "delta_norm": "",
                    "norm_z_score": "",
                    "norm_median": "",
                    "norm_mad": "",
                    "loss_z_score": "",
                    "loss_median": "",
                    "loss_mad": "",
                    "detection_observation_round": "",
                    "detection_loss": "",
                    "detection_reason": "",
                    "coverage_checks": "",
                    "coverage_flags": "",
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

        if selection.phase == "coverage" and selection.coverage_complete:
            coverage_trap_state = None
            coverage_deltas.clear()
            coverage_observation_rounds.clear()
        if selection.surveillance_complete:
            surveillance_trap_state = None
            surveillance_deltas.clear()
            surveillance_observation_rounds.clear()

        rehabilitated_after_round: list[int] = []
        removed_set = set(removed_after_round)
        for client_id in suspicion_probed - removed_set:
            probes = dodge_probe_counts[client_id]
            flag_rate = dodge_flag_counts[client_id] / probes if probes else 0.0
            if should_rehabilitate(probes, dodge_flag_counts[client_id], config):
                suspected_clients.discard(client_id)
                rehabilitated_after_round.append(client_id)
                logger.rehabilitation_rows.append(
                    {
                        "round": round_idx,
                        "client_id": client_id,
                        "is_free_rider": int(client_id in free_riders),
                        "penalty": penalties[client_id],
                        "probes": probes,
                        "flags": dodge_flag_counts[client_id],
                        "dodge_index": flag_rate,
                    }
                )
                dodge_probe_counts[client_id] = 0
                dodge_flag_counts[client_id] = 0

        for client_id in range(config.num_clients):
            probes = dodge_probe_counts[client_id]
            logger.dodge_rows.append(
                {
                    "round": round_idx,
                    "client_id": client_id,
                    "is_suspected": int(client_id in suspected_clients),
                    "episode_probes": probes,
                    "episode_flags": dodge_flag_counts[client_id],
                    "dodge_index": dodge_flag_counts[client_id] / probes if probes else "",
                    "lifetime_trap_flags": lifetime_trap_flags[client_id],
                }
            )

        evaluated_ids = set(detection_results)
        predicted = {
            client_id for client_id, result in detection_results.items() if result.flagged
        }
        actual = evaluated_ids & free_riders
        true_positives = len(predicted & actual)
        false_positives = len(predicted - actual)
        false_negatives = len(actual - predicted)
        true_negatives = len(evaluated_ids - predicted - actual)
        logger.detection_round_rows.append(
            {
                "round": round_idx,
                "evaluated_clients": len(evaluated_ids),
                "true_positives": true_positives,
                "false_positives": false_positives,
                "true_negatives": true_negatives,
                "false_negatives": false_negatives,
                "detection_accuracy": safe_ratio(true_positives + true_negatives, len(evaluated_ids)),
                "precision": safe_ratio(true_positives, true_positives + false_positives),
                "recall": safe_ratio(true_positives, true_positives + false_negatives),
                "f1": f1_score(true_positives, false_positives, false_negatives),
                "false_positive_rate": safe_ratio(false_positives, false_positives + true_negatives),
                "false_negative_rate": safe_ratio(false_negatives, false_negatives + true_positives),
                "specificity": safe_ratio(true_negatives, true_negatives + false_positives),
                "new_removals": len(removed_after_round),
                "new_rehabilitations": len(rehabilitated_after_round),
                "num_suspected": len(suspected_clients),
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

        global_metrics = evaluate_model(model, eval_loader, loss_fn, device)
        resource_metrics = resource_snapshot(device)
        logger.global_rows.append(
            {
                "round": round_idx,
                "global_accuracy": global_metrics["accuracy"],
                "global_loss": global_metrics["loss"],
                "num_active_clients": len(active_clients),
                "num_suspected_clients": len(suspected_clients),
                "num_trapped": len(selection.trapped_clients),
                "num_aggregated": len(aggregated_clients),
                "round_compute_seconds": time.perf_counter() - round_start,
                "round_time_seconds": 0.0,
                "process_cpu_seconds": 0.0,
                **resource_metrics,
            }
        )

        if config.save_checkpoints:
            checkpoint = {
                "round": round_idx,
                "model_state": clone_state(model.state_dict()),
                "global_state": clone_state(global_state),
                "active_clients": active_clients[:],
                "penalties": penalties.copy(),
                "times_flagged": times_flagged.copy(),
                "times_trapped": times_trapped.copy(),
                "selector_state": selector.state_dict(),
                "coverage_trap_state": coverage_trap_state,
                "coverage_deltas": coverage_deltas,
                "coverage_observation_rounds": coverage_observation_rounds,
                "surveillance_trap_state": surveillance_trap_state,
                "surveillance_deltas": surveillance_deltas,
                "surveillance_observation_rounds": surveillance_observation_rounds,
                "suspected_clients": sorted(suspected_clients),
                "dodge_probe_counts": dodge_probe_counts.copy(),
                "dodge_flag_counts": dodge_flag_counts.copy(),
                "lifetime_trap_flags": lifetime_trap_flags.copy(),
                "first_flag_round": first_flag_round.copy(),
                "first_removal_round": first_removal_round.copy(),
                "free_riders_ground_truth": sorted(free_riders),
                "global_metrics": logger.global_rows[-1],
                "config": config.to_dict(),
                "rng_state": rng.getstate(),
                "generator_state": generator.get_state(),
                "attacker_state": attacker.state_dict(),
            }
            save_rolling_checkpoint(
                checkpoint,
                logger.run_dir,
                round_idx,
                config.checkpoint_keep_last,
            )
        logger.global_rows[-1]["round_time_seconds"] = time.perf_counter() - round_start
        logger.global_rows[-1]["process_cpu_seconds"] = time.process_time() - process_start
        logger.write_progress(round_idx, config.to_dict())
        if progress_callback is not None:
            progress_callback(
                {
                    "round": round_idx,
                    "total_rounds": config.num_rounds,
                    "phase": selection.phase,
                    "active_clients": len(active_clients),
                    "round_time_seconds": logger.global_rows[-1]["round_time_seconds"],
                    "global_accuracy": global_metrics["accuracy"],
                    "global_loss": global_metrics["loss"],
                    "device": str(device),
                    "new_flags": new_flags,
                    "new_removals": len(removed_after_round),
                    "new_rehabilitations": len(rehabilitated_after_round),
                    "suspected_clients": len(suspected_clients),
                    **resource_metrics,
                }
            )

        if not active_clients:
            break

    wall_end = time.perf_counter()
    end_time = datetime.now()
    detection_summary = build_detection_summary(config, free_riders, active_clients)
    logger.summary_rows.append(detection_summary)
    logger.client_summary_rows.extend(
        {
            "client_id": client_id,
            "is_free_rider": int(client_id in free_riders),
            "first_flag_round": first_flag_round.get(client_id, ""),
            "times_flagged": times_flagged[client_id],
            "times_trapped": times_trapped[client_id],
            "first_removal_round": first_removal_round.get(client_id, ""),
            "final_penalty": penalties[client_id],
            "suspected_at_end": int(client_id in suspected_clients),
            "lifetime_trap_flags": lifetime_trap_flags[client_id],
            "active_at_end": int(client_id in active_clients),
        }
        for client_id in range(config.num_clients)
    )
    run_config = config.to_dict()
    completed_rounds = len(logger.global_rows)
    final_global = logger.global_rows[-1] if logger.global_rows else {}
    run_config.update(
        {
            "run_name": run_name,
            "seed": config.seed,
            "device": str(device),
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "total_wall_clock_seconds": wall_end - wall_start,
            "completed_rounds": completed_rounds,
            "final_global_accuracy": final_global.get("global_accuracy"),
            "best_global_accuracy": max(
                (row["global_accuracy"] for row in logger.global_rows), default=None
            ),
            "final_global_loss": final_global.get("global_loss"),
            "final_suspected_clients": len(suspected_clients),
            "total_rehabilitations": len(logger.rehabilitation_rows),
            "average_round_time_seconds": (
                sum(row["round_time_seconds"] for row in logger.global_rows) / completed_rounds
                if completed_rounds
                else None
            ),
            "peak_process_rss_mb": max(
                (
                    float(row["process_rss_mb"])
                    for row in logger.global_rows
                    if row.get("process_rss_mb") != ""
                ),
                default=None,
            ),
            "peak_cuda_allocated_mb": max(
                (
                    float(row["cuda_peak_allocated_mb"])
                    for row in logger.global_rows
                    if row.get("cuda_peak_allocated_mb") != ""
                ),
                default=None,
            ),
            "removal_threshold": config.removal_threshold,
            "num_free_riders": len(free_riders),
            "hardware": hardware_info(device),
            **detection_summary,
        }
    )
    logger.write_all(run_config)
    return str(logger.run_dir)


def save_rolling_checkpoint(
    checkpoint: dict[str, object],
    run_dir: Path,
    round_idx: int,
    keep_last: int,
) -> None:
    """Atomically save this round and retain only the newest snapshots."""
    if keep_last <= 0:
        raise ValueError("keep_last must be positive.")
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / f"checkpoint_round_{round_idx:04d}.pt"
    temporary_path = run_dir / f".{checkpoint_path.name}.tmp"
    torch.save(checkpoint, temporary_path)
    temporary_path.replace(checkpoint_path)

    numbered: list[tuple[int, Path]] = []
    for path in run_dir.glob("checkpoint_round_*.pt"):
        suffix = path.stem.removeprefix("checkpoint_round_")
        if suffix.isdigit():
            numbered.append((int(suffix), path))
    numbered.sort(key=lambda item: item[0])
    for _, obsolete_path in numbered[:-keep_last]:
        obsolete_path.unlink()

    # Publish a portable resume filename after the numbered checkpoint exists.
    latest_path = run_dir / "latest_checkpoint.pt"
    latest_temporary = run_dir / ".latest_checkpoint.pt.tmp"
    latest_temporary.unlink(missing_ok=True)
    shutil.copy2(checkpoint_path, latest_temporary)
    latest_temporary.replace(latest_path)


def safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def f1_score(true_positives: int, false_positives: int, false_negatives: int) -> float:
    precision = safe_ratio(true_positives, true_positives + false_positives)
    recall = safe_ratio(true_positives, true_positives + false_negatives)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def resource_snapshot(device: torch.device) -> dict[str, float | str]:
    metrics: dict[str, float | str] = {"process_rss_mb": ""}
    try:
        import psutil

        process = psutil.Process(os.getpid())
        metrics["process_rss_mb"] = process.memory_info().rss / (1024**2)
        metrics["system_memory_percent"] = psutil.virtual_memory().percent
        metrics["cpu_percent"] = process.cpu_percent(interval=None)
    except ImportError:
        metrics.update({"system_memory_percent": "", "cpu_percent": ""})
    if device.type == "cuda":
        metrics.update(
            {
                "cuda_allocated_mb": torch.cuda.memory_allocated(device) / (1024**2),
                "cuda_reserved_mb": torch.cuda.memory_reserved(device) / (1024**2),
                "cuda_peak_allocated_mb": torch.cuda.max_memory_allocated(device) / (1024**2),
            }
        )
    else:
        metrics.update(
            {"cuda_allocated_mb": "", "cuda_reserved_mb": "", "cuda_peak_allocated_mb": ""}
        )
    return metrics


def hardware_info(device: torch.device) -> dict[str, object]:
    info: dict[str, object] = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "torch_version": torch.__version__,
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
    }
    if device.type == "cuda":
        properties = torch.cuda.get_device_properties(device)
        info.update(
            {
                "cuda_device_name": properties.name,
                "cuda_total_memory_mb": properties.total_memory / (1024**2),
                "cuda_version": torch.version.cuda,
            }
        )
    try:
        import psutil

        info["total_system_memory_mb"] = psutil.virtual_memory().total / (1024**2)
    except ImportError:
        info["total_system_memory_mb"] = None
    return info


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
    if phase == "coverage":
        vectors = [deltas[client_id] for client_id in trapped_clients]
        return torch.stack(vectors).median(dim=0).values if vectors else _empty_reference(deltas)
    if phase == "suspicion":
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
    true_negatives = honest_count - removed_honest
    detection_accuracy = (removed_free_riders + true_negatives) / config.num_clients
    return {
        "removed_free_riders": removed_free_riders,
        "removed_honest_clients": removed_honest,
        "missed_free_riders": missed_free_riders,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "detection_accuracy": detection_accuracy,
        "false_positive_removal_rate": false_positive_rate,
    }
