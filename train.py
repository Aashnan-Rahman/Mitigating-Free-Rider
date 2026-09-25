from __future__ import annotations

import math
import os
import platform
import random
import shutil
import time
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import Callable

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Subset

from atomic_io import flush_file_to_disk, replace_with_retry
from clients.attacks import FreeRiderAttacker, flatten_delta
from config import ExperimentConfig
from data.loaders import get_datasets, make_eval_loader
from data.partition import partition_dataset
from logging_utils import RunLogger
from models.architectures import get_model
from server.aggregation import clone_state, fedavg_delta, floating_keys, make_trap_state
from server.detection import (
    DetectionResult,
    apply_surveillance_penalties,
    combine_coverage_checks,
    evaluate_suspicion_group,
    evaluate_updates,
    evaluate_zero_updates_only,
    merge_detection_results,
    should_rehabilitate,
)
from server.trap_selection import TrapSelector
from server.cycle_trap_selection import CycleTrapSelector
from server.cycle_protocol import transition_cycle_state
from server.model_fingerprint import model_fingerprint
from server.v11_detection import evaluate_v11_cycle
from server.v12_detection import (
    compact_sketch,
    evaluate_v12_cycle,
    history_reconstruction_scores,
    model_state_sketch,
)
from server.cycle_scoring import (
    cycle_classification,
    score_change,
    score_requires_removal,
    sendbacks_require_removal,
)


def evaluate_completed_cycle(
    *,
    coverage_deltas: dict[int, list[torch.Tensor]],
    coverage_profiles: dict[int, list[torch.Tensor]],
    coverage_trap_ids: dict[int, list[int]],
    coverage_observation_rounds: dict[int, list[int]],
    active_clients: set[int],
    checks: int,
    config: ExperimentConfig,
    trusted_reference_clients: set[int] | None,
) -> dict[str, object]:
    """Evaluate a complete v10 cycle, optionally against a cleaned R pool."""
    per_client_results: dict[int, list[DetectionResult]] = {}
    provisional_outliers: set[int] = set()
    reference_valid = True
    trap_payloads: dict[
        int,
        tuple[
            dict[int, torch.Tensor],
            dict[int, torch.Tensor],
            set[int],
            dict[int, DetectionResult],
        ],
    ] = {}

    for trap_id in range(checks):
        trap_deltas: dict[int, torch.Tensor] = {}
        trap_profiles: dict[int, torch.Tensor] = {}
        for client_id, client_deltas in coverage_deltas.items():
            if client_id not in active_clients:
                continue
            for index, delta in enumerate(client_deltas):
                if coverage_trap_ids[client_id][index] != trap_id:
                    continue
                trap_deltas[client_id] = delta
                trap_profiles[client_id] = coverage_profiles[client_id][index]

        if trusted_reference_clients is None:
            reference_ids = set(trap_deltas)
            reference = build_reference(
                "coverage", reference_ids, set(), trap_deltas
            )
            trap_results = evaluate_updates(
                trap_deltas,
                trap_profiles,
                reference,
                set(trap_deltas),
                config,
                reference_ids=reference_ids,
            )
        else:
            reference_ids = set(trap_deltas) & trusted_reference_clients
            if len(reference_ids) < config.cycle_min_reference_clients:
                reference_valid = False
                break
            provisional_reference = build_reference(
                "coverage", reference_ids, set(), trap_deltas
            )
            provisional = evaluate_updates(
                trap_deltas,
                trap_profiles,
                provisional_reference,
                set(trap_deltas),
                config,
                reference_ids=reference_ids,
            )
            trap_outliers = {
                client_id
                for client_id in reference_ids
                if provisional[client_id].flagged
            }
            provisional_outliers.update(trap_outliers)
            trap_payloads[trap_id] = (
                trap_deltas,
                trap_profiles,
                reference_ids,
                provisional,
            )
            continue

        for client_id, result in trap_results.items():
            per_client_results.setdefault(client_id, []).append(result)

    if reference_valid and trusted_reference_clients is not None:
        # Clean references once at the cycle level. An R client provisionally
        # anomalous under either frozen trap cannot define the other trap's
        # recomputed baseline.
        for trap_id in range(checks):
            trap_deltas, trap_profiles, reference_ids, provisional = trap_payloads[trap_id]
            cleaned_reference_ids = reference_ids - provisional_outliers
            if len(cleaned_reference_ids) < config.cycle_min_reference_clients:
                reference_valid = False
                break
            final_reference = build_reference(
                "coverage", cleaned_reference_ids, set(), trap_deltas
            )
            trap_results = evaluate_updates(
                trap_deltas,
                trap_profiles,
                final_reference,
                set(trap_deltas),
                config,
                reference_ids=cleaned_reference_ids,
            )
            # Preserve the actual provisional failure that disqualified an R
            # reference, even if the recomputed baseline would clear it.
            for client_id in provisional_outliers:
                if client_id in provisional and provisional[client_id].flagged:
                    trap_results[client_id] = provisional[client_id]
            for client_id, result in trap_results.items():
                per_client_results.setdefault(client_id, []).append(result)

    checks_used = {
        client_id: len(coverage_deltas.get(client_id, []))
        for client_id in active_clients
        if client_id in coverage_deltas
    }
    if not reference_valid:
        # Preserve exact-zero evidence but defer statistical state changes until
        # a sufficiently large trusted reference population is available.
        per_client_results.clear()
        for client_id in checks_used:
            zero_results = evaluate_zero_updates_only(
                {
                    index: delta
                    for index, delta in enumerate(coverage_deltas[client_id])
                },
                config,
            )
            if zero_results:
                per_client_results[client_id] = list(zero_results.values())

    combined_results = {
        client_id: combine_coverage_checks(results)
        for client_id, results in per_client_results.items()
        if results
    }
    flag_counts = {
        client_id: sum(result.flagged for result in results)
        for client_id, results in per_client_results.items()
    }
    joint_counts = {
        client_id: sum(result.joint_flag_count for result in results)
        for client_id, results in per_client_results.items()
    }
    zero_counts = {
        client_id: sum(result.reason == "zero_update" for result in results)
        for client_id, results in per_client_results.items()
    }
    decision_rounds = {
        client_id: max(coverage_observation_rounds[client_id])
        for client_id in checks_used
    }
    return {
        "results": combined_results,
        "checks": checks_used,
        "flags": flag_counts,
        "joint_flags": joint_counts,
        "zero_counts": zero_counts,
        "decision_rounds": decision_rounds,
        "reference_outliers": provisional_outliers,
        "reference_valid": reference_valid,
    }


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
    is_v12 = config.methodology_version == "swtcp_v12"
    is_v11 = config.methodology_version in {"swtcp_v11", "swtcp_v12"}
    is_v10 = config.methodology_version in {"swtcp_v10", "swtcp_v11", "swtcp_v12"}
    is_v9 = config.methodology_version in {"swtcp_v9", "swtcp_v10", "swtcp_v11", "swtcp_v12"}
    selector = CycleTrapSelector(config, rng) if is_v9 else TrapSelector(config, rng)
    logger = RunLogger(config, run_name)

    active_clients = list(range(config.num_clients))
    penalties = {client_id: 0.0 for client_id in range(config.num_clients)}
    zero_penalties = {client_id: 0 for client_id in range(config.num_clients)}
    magnitude_penalties = {client_id: 0 for client_id in range(config.num_clients)}
    times_flagged = {client_id: 0 for client_id in range(config.num_clients)}
    times_trapped = {client_id: 0 for client_id in range(config.num_clients)}
    first_flag_round: dict[int, int] = {}
    first_removal_round: dict[int, int] = {}
    coverage_trap_states: dict[int, dict[str, torch.Tensor]] = {}
    coverage_deltas: dict[int, list[torch.Tensor]] = {}
    coverage_norms: dict[int, list[float]] = {}
    coverage_profiles: dict[int, list[torch.Tensor]] = {}
    coverage_history_scores: dict[int, list[dict[str, float]]] = {}
    coverage_trap_ids: dict[int, list[int]] = {}
    coverage_observation_rounds: dict[int, list[int]] = {}
    surveillance_trap_state: dict[str, torch.Tensor] | None = None
    surveillance_deltas: dict[int, torch.Tensor] = {}
    surveillance_profiles: dict[int, torch.Tensor] = {}
    surveillance_observation_rounds: dict[int, int] = {}
    suspected_clients: set[int] = set()
    candidate_clients: set[int] = set()
    candidate_flag_counts = {client_id: 0 for client_id in range(config.num_clients)}
    candidate_probe_counts = {client_id: 0 for client_id in range(config.num_clients)}
    dodge_probe_counts = {client_id: 0 for client_id in range(config.num_clients)}
    dodge_flag_counts = {client_id: 0 for client_id in range(config.num_clients)}
    lifetime_trap_flags = {client_id: 0 for client_id in range(config.num_clients)}
    zero_update_counts = {client_id: 0 for client_id in range(config.num_clients)}
    cycle_clean_counts = {client_id: 0 for client_id in range(config.num_clients)}
    cycle_strong_counts = {client_id: 0 for client_id in range(config.num_clients)}
    cycle_trusted_strong_counts = {
        client_id: 0 for client_id in range(config.num_clients)
    }
    reference_eligible_clients: set[int] = set()
    reference_probation_counts: dict[int, int] = {}
    v11_calibration_history: list[list[float]] = []
    v11_norm_scale_history: list[float] = []
    v11_profile_scale_history: list[float] = []
    v11_last_cutoff: float | None = None
    sent_model_sketches = {
        client_id: deque(maxlen=config.v12_history_window + 1)
        for client_id in range(config.num_clients)
    }
    sent_model_fingerprints = {
        client_id: deque(maxlen=config.sendback_history_size)
        for client_id in range(config.num_clients)
    }
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
        penalties = {int(client_id): float(value) for client_id, value in checkpoint["penalties"].items()}
        zero_penalties.update(
            {int(key): int(value) for key, value in checkpoint.get("zero_penalties", {}).items()}
        )
        magnitude_penalties.update(
            {
                int(key): int(value)
                for key, value in checkpoint.get("magnitude_penalties", {}).items()
            }
        )
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
            coverage_trap_states = {
                int(trap_id): clone_state(state)
                for trap_id, state in checkpoint.get("coverage_trap_states", {}).items()
            }
            coverage_deltas = {
                int(client_id): [delta.detach().clone() for delta in values]
                for client_id, values in checkpoint.get("coverage_deltas", {}).items()
            }
            coverage_profiles = {
                int(client_id): [profile.detach().clone() for profile in values]
                for client_id, values in checkpoint.get("coverage_profiles", {}).items()
            }
            coverage_trap_ids = {
                int(client_id): [int(trap_id) for trap_id in values]
                for client_id, values in checkpoint.get("coverage_trap_ids", {}).items()
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
            surveillance_profiles = {
                int(client_id): profile.detach().clone()
                for client_id, profile in checkpoint.get(
                    "surveillance_profiles", {}
                ).items()
            }
            candidate_clients = {
                int(client_id) for client_id in checkpoint.get("candidate_clients", [])
            }
            candidate_flag_counts.update(
                {
                    int(key): int(value)
                    for key, value in checkpoint.get(
                        "candidate_flag_counts", {}
                    ).items()
                }
            )
            candidate_probe_counts.update(
                {
                    int(key): int(value)
                    for key, value in checkpoint.get(
                        "candidate_probe_counts", {}
                    ).items()
                }
            )
            dodge_probe_counts.update(
                {int(key): int(value) for key, value in checkpoint.get("dodge_probe_counts", {}).items()}
            )
            dodge_flag_counts.update(
                {int(key): int(value) for key, value in checkpoint.get("dodge_flag_counts", {}).items()}
            )
            lifetime_trap_flags.update(
                {int(key): int(value) for key, value in checkpoint.get("lifetime_trap_flags", {}).items()}
            )
            zero_update_counts.update(
                {int(key): int(value) for key, value in checkpoint.get("zero_update_counts", {}).items()}
            )
            cycle_clean_counts.update(
                {
                    int(key): int(value)
                    for key, value in checkpoint.get("cycle_clean_counts", {}).items()
                }
            )
            cycle_strong_counts.update(
                {
                    int(key): int(value)
                    for key, value in checkpoint.get("cycle_strong_counts", {}).items()
                }
            )
            cycle_trusted_strong_counts.update(
                {
                    int(key): int(value)
                    for key, value in checkpoint.get(
                        "cycle_trusted_strong_counts", {}
                    ).items()
                }
            )
            reference_eligible_clients = {
                int(client_id)
                for client_id in checkpoint.get("reference_eligible_clients", [])
            }
            coverage_history_scores = {
                int(client_id): [
                    {str(name): float(value) for name, value in scores.items()}
                    for scores in observations
                ]
                for client_id, observations in checkpoint.get(
                    "coverage_history_scores", {}
                ).items()
            }
            coverage_norms = {
                int(client_id): [float(value) for value in values]
                for client_id, values in checkpoint.get("coverage_norms", {}).items()
            }
            reference_probation_counts = {
                int(key): int(value)
                for key, value in checkpoint.get(
                    "reference_probation_counts", {}
                ).items()
            }
            v11_calibration_history = [
                [float(value) for value in cycle]
                for cycle in checkpoint.get("v11_calibration_history", [])
            ]
            v11_norm_scale_history = [
                float(value)
                for value in checkpoint.get("v11_norm_scale_history", [])
            ]
            v11_profile_scale_history = [
                float(value)
                for value in checkpoint.get("v11_profile_scale_history", [])
            ]
            stored_cutoff = checkpoint.get("v11_last_cutoff")
            v11_last_cutoff = (
                float(stored_cutoff) if stored_cutoff is not None else None
            )
            for client_id, fingerprints in checkpoint.get(
                "sent_model_fingerprints", {}
            ).items():
                sent_model_fingerprints[int(client_id)].extend(fingerprints)
            for client_id, sketches in checkpoint.get(
                "sent_model_sketches", {}
            ).items():
                sent_model_sketches[int(client_id)].extend(
                    sketch.detach().float().cpu() for sketch in sketches
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
        candidate_clients_at_round_start = candidate_clients.copy()
        suspected_clients_at_round_start = suspected_clients.copy()
        base_state = clone_state(global_state)
        selection = selector.select(
            round_idx,
            active_clients,
            penalties,
            times_flagged,
            suspected_clients,
            candidate_clients,
        )
        client_trap_states: dict[int, dict[str, torch.Tensor]] = {}
        is_cycle_probe = is_v9 and selection.phase in {"double_probe", "single_probe"}
        if selection.phase == "coverage" or is_cycle_probe:
            if not coverage_trap_states:
                trap_count = selector.checks_per_client if is_cycle_probe else config.coverage_checks_per_client
                coverage_trap_states = {
                    trap_id: make_trap_state(
                        base_state,
                        config.trap_noise_scale,
                        config.trap_noise_floor,
                        generator,
                    )
                    for trap_id in range(trap_count)
                }
            if selection.coverage_trap_id is None:
                raise RuntimeError("Coverage selection is missing its trap-model ID.")
            trap_state = coverage_trap_states[selection.coverage_trap_id]
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
            for suspects, candidates, anchors in selection.suspicion_groups:
                group_trap_state = make_trap_state(
                    base_state,
                    config.trap_noise_scale,
                    config.trap_noise_floor,
                    generator,
                )
                for client_id in suspects | candidates | anchors:
                    client_trap_states[client_id] = group_trap_state
        logger.log_trap_matrix_row(
            round_idx, selection.phase, selection.trapped_clients, config.num_clients
        )
        if selection.phase == "coverage" or is_cycle_probe:
            for client_id in selection.trapped_clients:
                logger.trap_assignment_rows.append(
                    {
                        "round": round_idx,
                        "client_id": client_id,
                        "phase": selection.phase,
                        "role": "cycle_probe" if is_cycle_probe else "initial_coverage",
                        "group_id": f"coverage_trap_{selection.coverage_trap_id}",
                    }
                )
        else:
            for group_id, (suspects, candidates, anchors) in enumerate(selection.suspicion_groups):
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
                for client_id in candidates:
                    logger.trap_assignment_rows.append(
                        {
                            "round": round_idx,
                            "client_id": client_id,
                            "phase": selection.phase,
                            "role": "candidate",
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
        profiles: dict[int, torch.Tensor] = {}
        local_stats: dict[int, dict[str, float]] = {}
        exact_replay_clients: set[int] = set()
        sent_fingerprint_cache: dict[int, str] = {}
        sent_sketch_cache: dict[int, torch.Tensor] = {}
        response_history_scores: dict[int, dict[str, float]] = {}

        for client_id in active_this_round:
            client_start = time.perf_counter()
            was_trapped = client_id in selection.trapped_clients
            received_state = (
                trap_state
                if (selection.phase == "coverage" or is_cycle_probe) and was_trapped
                else client_trap_states.get(client_id, base_state)
            )
            if was_trapped:
                times_trapped[client_id] += 1

            state_identity = id(received_state)
            sent_fingerprint = sent_fingerprint_cache.get(state_identity)
            if sent_fingerprint is None:
                sent_fingerprint = model_fingerprint(received_state)
                sent_fingerprint_cache[state_identity] = sent_fingerprint
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
            if is_v12:
                sent_sketch = sent_sketch_cache.get(state_identity)
                if sent_sketch is None:
                    sent_sketch = model_state_sketch(
                        received_state,
                        config.v12_sketch_width,
                        config.seed,
                    )
                    sent_sketch_cache[state_identity] = sent_sketch
                sent_model_sketches[client_id].append(sent_sketch.detach().clone())
                update_sketch = compact_sketch(
                    deltas[client_id],
                    config.v12_sketch_width,
                    config.seed,
                )
                response_history_scores[client_id] = history_reconstruction_scores(
                    update_sketch,
                    list(sent_model_sketches[client_id]),
                    config.v12_history_window,
                    config.cycle_scale_epsilon,
                )
            if (
                float(deltas[client_id].norm().item()) >= config.zero_update_epsilon
                and model_fingerprint(returned_state)
                in sent_model_fingerprints[client_id]
            ):
                exact_replay_clients.add(client_id)
            sent_model_fingerprints[client_id].append(sent_fingerprint)
            profiles[client_id] = build_layer_profile(
                returned_state, received_state, config.zero_update_epsilon
            )
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
        rehabilitated_after_round: list[int] = []
        v9_score_changes: dict[int, float] = {}

        detection_results = {}
        detection_rounds_used: dict[int, int] = {}
        coverage_checks_used: dict[int, int] = {}
        coverage_flags_used: dict[int, int] = {}
        coverage_joint_flags_used: dict[int, int] = {}
        coverage_zero_responses_used: dict[int, int] = {}
        decision_flag_counts: dict[int, int] = {}
        decision_joint_counts: dict[int, int] = {}
        trap_flag_counts: dict[int, int] = {}
        zero_responses_added: dict[int, int] = {}
        cycle_reference_outliers: set[int] = set()
        cycle_reference_valid = True
        cycle_coherent_strong: dict[int, bool] = {}
        cycle_scores: dict[int, float] = {}
        cycle_frozen_reference_ids: set[int] = set()
        cycle_norm_scales: list[float] = []
        cycle_profile_scales: list[float] = []
        suspicion_probed: set[int] = set()
        candidate_probed: set[int] = set()
        if selection.phase == "coverage" or is_cycle_probe:
            if selection.coverage_trap_id is None:
                raise RuntimeError("Coverage evidence is missing its trap-model ID.")
            for client_id in selection.trapped_clients:
                if is_v11:
                    coverage_norms.setdefault(client_id, []).append(
                        float(deltas[client_id].norm().item())
                    )
                    coverage_profiles.setdefault(client_id, []).append(
                        profiles[client_id].detach().float().cpu()
                    )
                    if is_v12:
                        coverage_history_scores.setdefault(client_id, []).append(
                            dict(response_history_scores.get(client_id, {}))
                        )
                else:
                    coverage_deltas.setdefault(client_id, []).append(deltas[client_id])
                    coverage_profiles.setdefault(client_id, []).append(profiles[client_id])
                coverage_trap_ids.setdefault(client_id, []).append(
                    selection.coverage_trap_id
                )
                coverage_observation_rounds.setdefault(client_id, []).append(round_idx)
            if selection.coverage_complete:
                checks_in_cycle = selector.checks_per_client if is_cycle_probe else config.coverage_checks_per_client
                if is_v10:
                    initial_cycle = selector.cycle_index == 0
                    if is_v11:
                        evaluator = evaluate_v12_cycle if is_v12 else evaluate_v11_cycle
                        evaluator_kwargs = {
                            "coverage_norms": coverage_norms,
                            "coverage_profiles": coverage_profiles,
                            "coverage_trap_ids": coverage_trap_ids,
                            "coverage_observation_rounds": coverage_observation_rounds,
                            "active_clients": set(active_this_round),
                            "checks": checks_in_cycle,
                            "config": config,
                            "trusted_reference_clients": (
                                None if initial_cycle else reference_eligible_clients.copy()
                            ),
                            "calibration_history": v11_calibration_history,
                            "norm_scale_history": v11_norm_scale_history,
                            "profile_scale_history": v11_profile_scale_history,
                        }
                        if is_v12:
                            evaluator_kwargs["coverage_history_scores"] = coverage_history_scores
                        evidence = evaluator(**evaluator_kwargs)
                    else:
                        evidence = evaluate_completed_cycle(
                            coverage_deltas=coverage_deltas,
                            coverage_profiles=coverage_profiles,
                            coverage_trap_ids=coverage_trap_ids,
                            coverage_observation_rounds=coverage_observation_rounds,
                            active_clients=set(active_this_round),
                            checks=checks_in_cycle,
                            config=config,
                            trusted_reference_clients=(
                                None if initial_cycle else reference_eligible_clients
                            ),
                        )
                    detection_results = evidence["results"]
                    coverage_checks_used = evidence["checks"]
                    coverage_flags_used = evidence["flags"]
                    coverage_joint_flags_used = evidence["joint_flags"]
                    coverage_zero_responses_used = evidence["zero_counts"]
                    detection_rounds_used = evidence["decision_rounds"]
                    cycle_reference_outliers = evidence["reference_outliers"]
                    cycle_reference_valid = bool(evidence["reference_valid"])
                    if is_v11:
                        cycle_coherent_strong = evidence["coherent_strong"]
                        cycle_scores = evidence["cycle_scores"]
                        cycle_frozen_reference_ids = evidence["frozen_reference_ids"]
                        cycle_norm_scales = evidence["norm_scales"]
                        cycle_profile_scales = evidence["profile_scales"]
                        v11_last_cutoff = float(evidence["cutoff"])
                else:
                    client_probe_ids: dict[int, list[int]] = {}
                    probe_results = {}
                    probe_id = 0
                    for trap_id in range(checks_in_cycle):
                        trap_deltas: dict[int, torch.Tensor] = {}
                        trap_profiles: dict[int, torch.Tensor] = {}
                        for client_id, client_deltas in coverage_deltas.items():
                            if client_id not in set(active_this_round):
                                continue
                            for index, delta in enumerate(client_deltas):
                                if coverage_trap_ids[client_id][index] != trap_id:
                                    continue
                                trap_deltas[probe_id] = delta
                                trap_profiles[probe_id] = coverage_profiles[client_id][index]
                                client_probe_ids.setdefault(client_id, []).append(probe_id)
                                probe_id += 1
                        coverage_reference = build_reference(
                            "coverage", set(trap_deltas), set(), trap_deltas
                        )
                        probe_results.update(
                            evaluate_updates(
                                trap_deltas,
                                trap_profiles,
                                coverage_reference,
                                set(trap_deltas),
                                config,
                            )
                        )
                    coverage_checks_used = {
                        client_id: len(probe_ids)
                        for client_id, probe_ids in client_probe_ids.items()
                    }
                    coverage_flags_used = {
                        client_id: sum(probe_results[item].flagged for item in probe_ids)
                        for client_id, probe_ids in client_probe_ids.items()
                    }
                    coverage_joint_flags_used = {
                        client_id: sum(
                            probe_results[item].joint_flag_count for item in probe_ids
                        )
                        for client_id, probe_ids in client_probe_ids.items()
                    }
                    coverage_zero_responses_used = {
                        client_id: sum(
                            probe_results[item].reason == "zero_update"
                            for item in probe_ids
                        )
                        for client_id, probe_ids in client_probe_ids.items()
                    }
                    if is_v9:
                        coverage_flags_used = {
                            client_id: int(
                                coverage_joint_flags_used.get(client_id, 0) > 0
                                or coverage_zero_responses_used.get(client_id, 0) > 0
                            )
                            for client_id in client_probe_ids
                        }
                    if checks_in_cycle == 1:
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
                decision_flag_counts.update(coverage_flags_used)
                decision_joint_counts.update(coverage_joint_flags_used)
                trap_flag_counts.update(coverage_flags_used)
                zero_responses_added.update(coverage_zero_responses_used)
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
                zero_responses_added[client_id] = zero_responses_added.get(client_id, 0) + 1
                detection_rounds_used[client_id] = round_idx
        elif selection.phase in {"warmup", "dormant"}:
            # Before secret probes begin, only exact send-backs are strong enough
            # to create evidence; nonzero population outliers are ignored.
            detection_results = evaluate_zero_updates_only(deltas, config)
            detection_rounds_used = {
                client_id: round_idx for client_id in active_this_round
            }
            zero_responses_added.update(
                {
                    client_id: 1
                    for client_id, result in detection_results.items()
                    if result.reason == "zero_update"
                }
            )
        else:
            # Every suspicious group has its own fresh trap and is evaluated
            # only against the low-suspicion anchors that received that trap.
            for suspects, candidates, anchors in selection.suspicion_groups:
                suspicion_probed.update(suspects)
                candidate_probed.update(candidates)
                group_results = evaluate_suspicion_group(
                    deltas,
                    profiles,
                    suspects | candidates,
                    anchors,
                    config,
                )
                detection_results.update(group_results)
                for client_id in group_results:
                    if group_results[client_id].flagged:
                        decision_flag_counts[client_id] = 1
                        decision_joint_counts[client_id] = group_results[
                            client_id
                        ].joint_flag_count
                        trap_flag_counts[client_id] = 1
                        if group_results[client_id].reason == "zero_update":
                            zero_responses_added[client_id] = 1
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
                decision_joint_counts[client_id] = 0
                zero_responses_added[client_id] = 1
                detection_rounds_used[client_id] = round_idx

            for client_id in selection.surveillance_clients:
                surveillance_deltas[client_id] = deltas[client_id]
                surveillance_profiles[client_id] = profiles[client_id]
                surveillance_observation_rounds[client_id] = round_idx
            if selection.surveillance_complete:
                eligible_surveillance = (
                    set(surveillance_deltas)
                    & set(active_this_round)
                    - suspected_clients
                    - candidate_clients
                    - suspicion_probed
                    - candidate_probed
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
                    {
                        client_id: surveillance_profiles[client_id]
                        for client_id in eligible_surveillance
                    },
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
                        decision_joint_counts[client_id] = (
                            decision_joint_counts.get(client_id, 0)
                            + result.joint_flag_count
                        )
                        trap_flag_counts[client_id] = trap_flag_counts.get(client_id, 0) + 1
                        if result.reason == "zero_update":
                            zero_responses_added[client_id] = (
                                zero_responses_added.get(client_id, 0) + 1
                            )
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
                coverage_joint_flags_used.update(
                    {
                        client_id: result.joint_flag_count
                        for client_id, result in surveillance_results.items()
                    }
                )

        # A nonzero response that exactly matches any of this client's recent
        # server-sent models is stale replay evidence. Zero deltas retain their
        # existing path, so a response can earn at most one send-back count.
        for client_id in exact_replay_clients:
            replay_result = DetectionResult(
                True,
                config.penalty_zero_update,
                None,
                float(deltas[client_id].norm().item()),
                None,
                None,
                None,
                None,
                None,
                None,
                "exact_model_replay",
            )
            detection_results[client_id] = merge_detection_results(
                detection_results.get(client_id), replay_result
            )
            decision_flag_counts[client_id] = (
                decision_flag_counts.get(client_id, 0) + 1
            )
            zero_responses_added[client_id] = (
                zero_responses_added.get(client_id, 0) + 1
            )
            detection_rounds_used[client_id] = round_idx

        if is_v9:
            # Send-backs are counted on every round and are never offset by a
            # positive cycle score. Classification is performed only after a
            # complete sweep, when every active client has comparable evidence.
            for client_id, result in detection_results.items():
                if zero_responses_added.get(client_id, 0) > 0:
                    added = zero_responses_added[client_id]
                    zero_update_counts[client_id] += added
                    zero_penalties[client_id] = zero_update_counts[client_id]
                    times_flagged[client_id] += added
                    first_flag_round.setdefault(client_id, round_idx)
                    new_flags += added
                    logger.detection_event_rows.append(
                        {
                            "decision_round": round_idx,
                            "observation_round": detection_rounds_used.get(client_id, round_idx),
                            "client_id": client_id,
                            "is_free_rider": int(client_id in free_riders),
                            "was_trapped": int(client_id in selection.trapped_clients),
                            "reason": (
                                "exact_model_replay"
                                if client_id in exact_replay_clients
                                else "zero_update"
                            ),
                            "delta_norm": result.delta_norm,
                            "norm_z_score": result.norm_z_score,
                            "magnitude_flag": 0,
                            "profile_score": result.profile_score,
                            "profile_z_score": result.profile_z_score,
                            "profile_median": result.profile_median,
                            "profile_mad": result.profile_mad,
                            "profile_flag": 0,
                            "joint_flag_count": 0,
                            "loss": "",
                            "loss_z_score": "",
                            "coverage_checks": coverage_checks_used.get(client_id, ""),
                            "coverage_flags": coverage_flags_used.get(client_id, ""),
                            "coverage_joint_flags": coverage_joint_flags_used.get(client_id, ""),
                            "penalty": 0,
                        }
                    )

            if is_v10 and is_cycle_probe and selection.coverage_complete:
                initial_cycle = selector.cycle_index == 0
                if cycle_reference_valid:
                    previous_suspects = suspected_clients.copy()
                    previous_candidates = candidate_clients.copy()
                    next_suspects: set[int] = set()
                    next_candidates: set[int] = set()
                    v12_new_strong_anomaly = False
                    for client_id, checks in coverage_checks_used.items():
                        previous_role = (
                            "S"
                            if client_id in previous_suspects
                            else "C"
                            if client_id in previous_candidates
                            else "R"
                        )
                        if coverage_zero_responses_used.get(client_id, 0):
                            if previous_role == "S":
                                next_suspects.add(client_id)
                            elif previous_role == "C":
                                next_candidates.add(client_id)
                            reference_eligible_clients.discard(client_id)
                            reference_probation_counts.pop(client_id, None)
                            continue

                        failed_probes = coverage_flags_used.get(client_id, 0)
                        if client_id in cycle_reference_outliers:
                            failed_probes = max(1, failed_probes)
                        transition = transition_cycle_state(
                            role=previous_role,
                            failed_probes=min(failed_probes, checks),
                            checks=checks,
                            score=penalties[client_id],
                            clean_cycles=cycle_clean_counts[client_id],
                            strong_cycles=cycle_strong_counts[client_id],
                            trusted_strong_cycles=cycle_trusted_strong_counts[client_id],
                            initial_cycle=initial_cycle,
                            trusted_cycle=not initial_cycle,
                            config=config,
                            coherent_strong=(
                                cycle_coherent_strong.get(client_id, False)
                                if is_v11
                                else None
                            ),
                        )
                        if (
                            is_v12
                            and failed_probes
                            and cycle_coherent_strong.get(client_id, False)
                        ):
                            v12_new_strong_anomaly = True
                        old_score = penalties[client_id]
                        penalties[client_id] = transition.score
                        v9_score_changes[client_id] = transition.score - old_score
                        cycle_clean_counts[client_id] = transition.clean_cycles
                        cycle_strong_counts[client_id] = transition.strong_cycles
                        cycle_trusted_strong_counts[client_id] = (
                            transition.trusted_strong_cycles
                        )

                        if transition.role == "S":
                            next_suspects.add(client_id)
                        elif transition.role == "C":
                            next_candidates.add(client_id)

                        if transition.role != "R":
                            reference_eligible_clients.discard(client_id)
                            reference_probation_counts.pop(client_id, None)
                        elif transition.rehabilitated:
                            reference_eligible_clients.discard(client_id)
                            reference_probation_counts[client_id] = 0
                            rehabilitated_after_round.append(client_id)
                            logger.rehabilitation_rows.append(
                                {
                                    "round": round_idx,
                                    "client_id": client_id,
                                    "is_free_rider": int(client_id in free_riders),
                                    "cleared_magnitude_penalty": 0,
                                    "remaining_penalty": penalties[client_id],
                                    "probes": checks,
                                    "flags": 0,
                                    "dodge_index": 0.0,
                                }
                            )
                        elif initial_cycle:
                            reference_eligible_clients.add(client_id)
                        elif client_id in reference_probation_counts:
                            if failed_probes == 0:
                                reference_probation_counts[client_id] += 1
                            if (
                                reference_probation_counts[client_id]
                                >= config.cycle_reference_probation_cycles
                            ):
                                reference_probation_counts.pop(client_id, None)
                                reference_eligible_clients.add(client_id)

                        if failed_probes:
                            times_flagged[client_id] += failed_probes
                            lifetime_trap_flags[client_id] += failed_probes
                            first_flag_round.setdefault(client_id, round_idx)
                            new_flags += failed_probes
                            detection = detection_results.get(client_id)
                            if detection is not None:
                                logger.detection_event_rows.append(
                                    {
                                        "decision_round": round_idx,
                                        "observation_round": detection_rounds_used.get(client_id, round_idx),
                                        "client_id": client_id,
                                        "is_free_rider": int(client_id in free_riders),
                                        "was_trapped": 1,
                                        "reason": f"cycle_failure_{transition.role}",
                                        "delta_norm": detection.delta_norm,
                                        "norm_z_score": detection.norm_z_score,
                                        "magnitude_flag": int(detection.magnitude_flag),
                                        "profile_score": detection.profile_score,
                                        "profile_z_score": detection.profile_z_score,
                                        "profile_median": detection.profile_median,
                                        "profile_mad": detection.profile_mad,
                                        "profile_flag": int(detection.profile_flag),
                                        "joint_flag_count": coverage_joint_flags_used.get(client_id, 0),
                                        "loss": "",
                                        "loss_z_score": "",
                                        "coverage_checks": checks,
                                        "coverage_flags": failed_probes,
                                        "coverage_joint_flags": coverage_joint_flags_used.get(client_id, 0),
                                        "penalty": v9_score_changes[client_id],
                                    }
                                )
                            logger.candidate_event_rows.append(
                                {
                                    "round": round_idx,
                                    "client_id": client_id,
                                    "is_free_rider": int(client_id in free_riders),
                                    "event": (
                                        "entered_suspicious_state"
                                        if transition.role == "S"
                                        else "entered_candidate_state"
                                    ),
                                    "reason": (
                                        f"{failed_probes}_failed_probes_in_{checks}_checks"
                                        + (
                                            "_coherent"
                                            if is_v11
                                            and cycle_coherent_strong.get(client_id, False)
                                            else "_weak"
                                            if is_v11
                                            else ""
                                        )
                                    ),
                                    "cumulative_penalty": penalties[client_id],
                                }
                            )

                        if transition.remove:
                            removed_after_round.append(client_id)
                            next_suspects.discard(client_id)
                            next_candidates.discard(client_id)
                            reference_eligible_clients.discard(client_id)
                            reference_probation_counts.pop(client_id, None)
                            first_removal_round.setdefault(client_id, round_idx)
                            logger.removal_rows.append(
                                {
                                    "round": round_idx,
                                    "client_id": client_id,
                                    "is_free_rider": int(client_id in free_riders),
                                    "final_penalty": penalties[client_id],
                                    "removal_basis": "two_strong_cycles_with_trusted_confirmation",
                                    "zero_update_count": zero_update_counts[client_id],
                                    "suspicion_probes": times_trapped[client_id],
                                }
                            )

                    if is_v11:
                        calibration_ids = (
                            reference_eligible_clients.copy()
                            if initial_cycle
                            else cycle_frozen_reference_ids
                        )
                        calibration_scores = [
                            cycle_scores[client_id]
                            for client_id in calibration_ids
                            if client_id in cycle_scores
                            and client_id not in removed_after_round
                        ]
                        if calibration_scores:
                            v11_calibration_history.append(calibration_scores)
                            del v11_calibration_history[
                                : -config.cycle_calibration_window_cycles
                            ]
                        v11_norm_scale_history.extend(cycle_norm_scales)
                        v11_profile_scale_history.extend(cycle_profile_scales)
                        scale_history_limit = (
                            config.cycle_calibration_window_cycles * max(1, checks)
                        )
                        del v11_norm_scale_history[:-scale_history_limit]
                        del v11_profile_scale_history[:-scale_history_limit]

                    suspected_clients = next_suspects
                    candidate_clients = next_candidates - next_suspects
                    anomaly_found = (
                        v12_new_strong_anomaly
                        if is_v12
                        else bool(suspected_clients or candidate_clients)
                    )
                    selector.finish_cycle(anomaly_found)
                else:
                    # Never relax probing or change statistical states when the
                    # trusted R reference is too small for a defensible decision.
                    selector.finish_cycle(anomaly_found=True)

            if not is_v10 and is_cycle_probe and selection.coverage_complete:
                previous_suspects = suspected_clients.copy()
                previous_candidates = candidate_clients.copy()
                next_suspects: set[int] = set()
                next_candidates: set[int] = set()
                for client_id, checks in coverage_checks_used.items():
                    # Exact send-backs use only their five-strike path. Giving
                    # them an additional C/S cost would silently make four
                    # send-backs sufficient for removal.
                    if coverage_zero_responses_used.get(client_id, 0):
                        if client_id in previous_suspects:
                            next_suspects.add(client_id)
                        elif client_id in previous_candidates:
                            next_candidates.add(client_id)
                        continue

                    classification = cycle_classification(
                        coverage_joint_flags_used.get(client_id, 0), checks
                    )
                    change = score_change(
                        classification,
                        config.cycle_clear_reward,
                        config.cycle_candidate_cost,
                        config.cycle_suspicious_cost,
                    )
                    v9_score_changes[client_id] = change
                    penalties[client_id] += change
                    if classification == "S":
                        next_suspects.add(client_id)
                    elif classification == "C":
                        next_candidates.add(client_id)
                    elif client_id in previous_suspects or client_id in previous_candidates:
                        rehabilitated_after_round.append(client_id)
                        logger.rehabilitation_rows.append(
                            {
                                "round": round_idx,
                                "client_id": client_id,
                                "is_free_rider": int(client_id in free_riders),
                                "cleared_magnitude_penalty": 0,
                                "remaining_penalty": penalties[client_id],
                                "probes": checks,
                                "flags": 0,
                                "dodge_index": 0.0,
                            }
                        )
                    joint_failures = coverage_joint_flags_used.get(client_id, 0)
                    if joint_failures:
                        times_flagged[client_id] += joint_failures
                        lifetime_trap_flags[client_id] += joint_failures
                        first_flag_round.setdefault(client_id, round_idx)
                        new_flags += joint_failures
                        detection = detection_results[client_id]
                        logger.detection_event_rows.append(
                            {
                                "decision_round": round_idx,
                                "observation_round": detection_rounds_used.get(client_id, round_idx),
                                "client_id": client_id,
                                "is_free_rider": int(client_id in free_riders),
                                "was_trapped": 1,
                                "reason": f"joint_cycle_failure_{classification}",
                                "delta_norm": detection.delta_norm,
                                "norm_z_score": detection.norm_z_score,
                                "magnitude_flag": int(detection.magnitude_flag),
                                "profile_score": detection.profile_score,
                                "profile_z_score": detection.profile_z_score,
                                "profile_median": detection.profile_median,
                                "profile_mad": detection.profile_mad,
                                "profile_flag": int(detection.profile_flag),
                                "joint_flag_count": joint_failures,
                                "loss": "",
                                "loss_z_score": "",
                                "coverage_checks": checks,
                                "coverage_flags": coverage_flags_used.get(client_id, 0),
                                "coverage_joint_flags": joint_failures,
                                "penalty": v9_score_changes[client_id],
                            }
                        )
                    if classification in {"C", "S"}:
                        logger.candidate_event_rows.append(
                            {
                                "round": round_idx,
                                "client_id": client_id,
                                "is_free_rider": int(client_id in free_riders),
                                "event": (
                                    "entered_suspicious_state"
                                    if classification == "S"
                                    else "entered_candidate_state"
                                ),
                                "reason": f"{joint_failures}_joint_failures_in_{checks}_probes",
                                "cumulative_penalty": penalties[client_id],
                            }
                        )

                suspected_clients = next_suspects
                candidate_clients = next_candidates - next_suspects
                anomaly_found = bool(suspected_clients or candidate_clients)
                selector.finish_cycle(anomaly_found)

            for client_id in active_this_round:
                score_removal = (
                    not is_v10
                    and score_requires_removal(
                        penalties[client_id], config.cycle_removal_score
                    )
                )
                sendback_removal = sendbacks_require_removal(
                    zero_update_counts[client_id],
                    round_idx,
                    config.warmup_rounds,
                    config.sendback_removal_count,
                )
                if not (score_removal or sendback_removal):
                    continue
                if client_id in removed_after_round:
                    continue
                removed_after_round.append(client_id)
                suspected_clients.discard(client_id)
                candidate_clients.discard(client_id)
                reference_eligible_clients.discard(client_id)
                reference_probation_counts.pop(client_id, None)
                first_removal_round.setdefault(client_id, round_idx)
                logger.removal_rows.append(
                    {
                        "round": round_idx,
                        "client_id": client_id,
                        "is_free_rider": int(client_id in free_riders),
                        "final_penalty": penalties[client_id],
                        "removal_basis": (
                            "five_exact_sendbacks"
                            if sendback_removal
                            else "cycle_score_at_or_below_minus_four"
                        ),
                        "zero_update_count": zero_update_counts[client_id],
                        "suspicion_probes": times_trapped[client_id],
                    }
                )
        for client_id in suspicion_probed:
            dodge_probe_counts[client_id] += 1
            result = detection_results[client_id]
            if result.reason == "zero_update" or result.joint_flag_count:
                dodge_flag_counts[client_id] += 1
        for client_id in candidate_probed:
            candidate_probe_counts[client_id] += 1

        for client_id in active_this_round:
            was_trapped = client_id in selection.trapped_clients
            detection = detection_results.get(client_id)
            if not is_v9 and detection is not None:
                if detection.flagged:
                    zero_count_added = zero_responses_added.get(client_id, 0)
                    zero_points_added = zero_count_added * config.penalty_zero_update
                    zero_update_counts[client_id] += zero_count_added
                    zero_penalties[client_id] += zero_points_added
                    magnitude_penalties[client_id] += max(
                        0, detection.penalty - zero_points_added
                    )
                    penalties[client_id] = (
                        zero_penalties[client_id] + magnitude_penalties[client_id]
                    )
                    flag_count = decision_flag_counts.get(client_id, 1)
                    joint_count = decision_joint_counts.get(
                        client_id, detection.joint_flag_count
                    )
                    times_flagged[client_id] += flag_count
                    lifetime_trap_flags[client_id] += trap_flag_counts.get(
                        client_id,
                        int(was_trapped),
                    )

                    was_candidate = (
                        client_id in candidate_clients_at_round_start
                        or client_id in candidate_clients
                    )
                    is_zero_response = zero_responses_added.get(client_id, 0) > 0
                    candidate_evidence = (
                        candidate_flag_counts[client_id] if was_candidate else 0
                    ) + joint_count
                    confirmed = (
                        is_zero_response
                        or candidate_evidence >= config.candidate_confirmation_flags
                    )
                    if confirmed and client_id not in suspected_clients:
                        suspected_clients.add(client_id)
                        candidate_clients.discard(client_id)
                        candidate_flag_counts[client_id] = 0
                        candidate_probe_counts[client_id] = 0
                        dodge_probe_counts[client_id] = 0
                        dodge_flag_counts[client_id] = 0
                    elif not confirmed and client_id not in suspected_clients:
                        candidate_clients.add(client_id)
                        candidate_flag_counts[client_id] = candidate_evidence
                        logger.candidate_event_rows.append(
                            {
                                "round": round_idx,
                                "client_id": client_id,
                                "is_free_rider": int(client_id in free_riders),
                                "event": (
                                    "additional_candidate_flag"
                                    if was_candidate
                                    else "entered_candidate_state"
                                ),
                                "reason": detection.reason,
                                "cumulative_penalty": penalties[client_id],
                            }
                        )
                    if confirmed and was_candidate:
                        logger.candidate_event_rows.append(
                            {
                                "round": round_idx,
                                "client_id": client_id,
                                "is_free_rider": int(client_id in free_riders),
                                "event": "confirmed_suspicious",
                                "reason": detection.reason,
                                "cumulative_penalty": penalties[client_id],
                            }
                        )
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
                            "magnitude_flag": int(detection.magnitude_flag),
                            "profile_score": detection.profile_score,
                            "profile_z_score": detection.profile_z_score,
                            "profile_median": detection.profile_median,
                            "profile_mad": detection.profile_mad,
                            "profile_flag": int(detection.profile_flag),
                            "joint_flag_count": detection.joint_flag_count,
                            "loss": "",
                            "loss_z_score": detection.loss_z_score,
                            "coverage_checks": coverage_checks_used.get(client_id, ""),
                            "coverage_flags": coverage_flags_used.get(client_id, ""),
                            "coverage_joint_flags": coverage_joint_flags_used.get(
                                client_id, ""
                            ),
                            "penalty": detection.penalty,
                        }
                    )

                elif client_id in candidate_probed:
                    candidate_clients.discard(client_id)
                    candidate_flag_counts[client_id] = 0
                    candidate_probe_counts[client_id] = 0
                    magnitude_penalties[client_id] = 0
                    penalties[client_id] = zero_penalties[client_id]
                    logger.candidate_event_rows.append(
                        {
                            "round": round_idx,
                            "client_id": client_id,
                            "is_free_rider": int(client_id in free_riders),
                            "event": "cleared_after_confirmation",
                            "reason": "confirmation_pass",
                            "cumulative_penalty": penalties[client_id],
                        }
                    )

                zero_removal_ready = (
                    round_idx >= config.warmup_rounds
                    and zero_update_counts[client_id] * config.penalty_zero_update
                    >= config.removal_threshold
                )
                magnitude_removal_ready = (
                    penalties[client_id] >= config.removal_threshold
                    and dodge_probe_counts[client_id] >= config.dodge_min_probes
                    and not should_rehabilitate(
                        dodge_probe_counts[client_id],
                        dodge_flag_counts[client_id],
                        config,
                    )
                )
                if zero_removal_ready or magnitude_removal_ready:
                    removed_after_round.append(client_id)
                    suspected_clients.discard(client_id)
                    candidate_clients.discard(client_id)
                    candidate_flag_counts[client_id] = 0
                    first_removal_round.setdefault(client_id, round_idx)
                    logger.removal_rows.append(
                        {
                            "round": round_idx,
                            "client_id": client_id,
                            "is_free_rider": int(client_id in free_riders),
                            "final_penalty": penalties[client_id],
                            "removal_basis": (
                                "exact_sendbacks"
                                if zero_removal_ready
                                else "joint_gradient_evidence_after_minimum_probes"
                            ),
                            "zero_update_count": zero_update_counts[client_id],
                            "suspicion_probes": dodge_probe_counts[client_id],
                        }
                    )
                    candidate_probe_counts[client_id] = 0
                    dodge_probe_counts[client_id] = 0
                    dodge_flag_counts[client_id] = 0

            penalty_added = (
                v9_score_changes.get(client_id, 0.0)
                if is_v9
                else detection.penalty if detection else 0
            )
            logger.client_rows.append(
                {
                    "round": round_idx,
                    "client_id": client_id,
                    "is_free_rider": int(client_id in free_riders),
                    "was_trapped": int(was_trapped),
                    "was_active_anchor": int(client_id in selection.anchors),
                    "was_y_audited": int(client_id in selection.surveillance_clients),
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
                    "magnitude_flag": int(detection.magnitude_flag) if detection else 0,
                    "profile_score": detection.profile_score if detection else "",
                    "profile_z_score": detection.profile_z_score if detection else "",
                    "profile_median": detection.profile_median if detection else "",
                    "profile_mad": detection.profile_mad if detection else "",
                    "profile_flag": int(detection.profile_flag) if detection else 0,
                    "joint_flag_count": detection.joint_flag_count if detection else 0,
                    "loss_z_score": detection.loss_z_score if detection else "",
                    "loss_median": detection.loss_median if detection else "",
                    "loss_mad": detection.loss_mad if detection else "",
                    "detection_observation_round": detection_rounds_used.get(client_id, ""),
                    "detection_loss": "",
                    "detection_reason": detection.reason if detection and detection.reason else "",
                    "coverage_checks": coverage_checks_used.get(client_id, ""),
                    "coverage_flags": coverage_flags_used.get(client_id, ""),
                    "coverage_joint_flags": coverage_joint_flags_used.get(client_id, ""),
                    "flagged": (
                        int(
                            zero_responses_added.get(client_id, 0) > 0
                            or detection.flagged
                        )
                        if is_v10 and detection
                        else
                        int(
                            zero_responses_added.get(client_id, 0) > 0
                            or detection.joint_flag_count > 0
                        )
                        if is_v9 and detection
                        else int(detection.flagged) if detection else 0
                    ),
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
                    "is_candidate": int(client_id in candidate_clients),
                    "candidate_episode_flags": candidate_flag_counts[client_id],
                    "candidate_episode_probes": candidate_probe_counts[client_id],
                    "is_suspected": int(client_id in suspected_clients),
                    "zero_update_count": zero_update_counts[client_id],
                    "zero_penalty": zero_penalties[client_id],
                    "magnitude_episode_penalty": magnitude_penalties[client_id],
                    "reference_eligible": int(client_id in reference_eligible_clients),
                    "reference_probation_cycles": reference_probation_counts.get(client_id, ""),
                    "cycle_clean_cycles": cycle_clean_counts[client_id],
                    "cycle_strong_cycles": cycle_strong_counts[client_id],
                    "cycle_trusted_strong_cycles": cycle_trusted_strong_counts[client_id],
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
                    "was_active_anchor": 0,
                    "was_y_audited": 0,
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
                    "magnitude_flag": 0,
                    "profile_score": "",
                    "profile_z_score": "",
                    "profile_median": "",
                    "profile_mad": "",
                    "profile_flag": 0,
                    "joint_flag_count": 0,
                    "loss_z_score": "",
                    "loss_median": "",
                    "loss_mad": "",
                    "detection_observation_round": "",
                    "detection_loss": "",
                    "detection_reason": "",
                    "coverage_checks": "",
                    "coverage_flags": "",
                    "coverage_joint_flags": "",
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
                    "is_candidate": int(client_id in candidate_clients),
                    "candidate_episode_flags": candidate_flag_counts[client_id],
                    "candidate_episode_probes": candidate_probe_counts[client_id],
                    "is_suspected": int(client_id in suspected_clients),
                    "zero_update_count": zero_update_counts[client_id],
                    "zero_penalty": zero_penalties[client_id],
                    "magnitude_episode_penalty": magnitude_penalties[client_id],
                    "reference_eligible": int(client_id in reference_eligible_clients),
                    "reference_probation_cycles": reference_probation_counts.get(client_id, ""),
                    "cycle_clean_cycles": cycle_clean_counts[client_id],
                    "cycle_strong_cycles": cycle_strong_counts[client_id],
                    "cycle_trusted_strong_cycles": cycle_trusted_strong_counts[client_id],
                }
            )

        if (selection.phase == "coverage" or is_cycle_probe) and selection.coverage_complete:
            coverage_trap_states.clear()
            coverage_deltas.clear()
            coverage_norms.clear()
            coverage_profiles.clear()
            coverage_history_scores.clear()
            coverage_trap_ids.clear()
            coverage_observation_rounds.clear()
        if selection.surveillance_complete:
            surveillance_trap_state = None
            surveillance_deltas.clear()
            surveillance_profiles.clear()
            surveillance_observation_rounds.clear()

        if not is_v9:
            rehabilitated_after_round = []
        removed_set = set(removed_after_round)
        rehabilitation_suspects = suspicion_probed - removed_set if not is_v9 else set()
        for client_id in rehabilitation_suspects:
            probes = dodge_probe_counts[client_id]
            flag_rate = dodge_flag_counts[client_id] / probes if probes else 0.0
            if should_rehabilitate(probes, dodge_flag_counts[client_id], config):
                suspected_clients.discard(client_id)
                candidate_clients.discard(client_id)
                candidate_flag_counts[client_id] = 0
                cleared_magnitude = magnitude_penalties[client_id]
                magnitude_penalties[client_id] = 0
                penalties[client_id] = zero_penalties[client_id]
                rehabilitated_after_round.append(client_id)
                logger.rehabilitation_rows.append(
                    {
                        "round": round_idx,
                        "client_id": client_id,
                        "is_free_rider": int(client_id in free_riders),
                        "cleared_magnitude_penalty": cleared_magnitude,
                        "remaining_penalty": penalties[client_id],
                        "probes": probes,
                        "flags": dodge_flag_counts[client_id],
                        "dodge_index": flag_rate,
                    }
                )
                dodge_probe_counts[client_id] = 0
                dodge_flag_counts[client_id] = 0

        for client_id in candidate_probed - removed_set:
            if client_id not in candidate_clients:
                continue
            probes = candidate_probe_counts[client_id]
            flags = candidate_flag_counts[client_id]
            if should_rehabilitate(probes, flags, config):
                cleared_magnitude = magnitude_penalties[client_id]
                candidate_clients.discard(client_id)
                candidate_flag_counts[client_id] = 0
                candidate_probe_counts[client_id] = 0
                magnitude_penalties[client_id] = 0
                penalties[client_id] = zero_penalties[client_id]
                rehabilitated_after_round.append(client_id)
                logger.rehabilitation_rows.append(
                    {
                        "round": round_idx,
                        "client_id": client_id,
                        "is_free_rider": int(client_id in free_riders),
                        "cleared_magnitude_penalty": cleared_magnitude,
                        "remaining_penalty": penalties[client_id],
                        "probes": probes,
                        "flags": flags,
                        "dodge_index": flags / probes if probes else 0.0,
                    }
                )
                logger.candidate_event_rows.append(
                    {
                        "round": round_idx,
                        "client_id": client_id,
                        "is_free_rider": int(client_id in free_riders),
                        "event": "rehabilitated_candidate",
                        "reason": "no_repeated_joint_failure",
                        "cumulative_penalty": penalties[client_id],
                    }
                )

        rehabilitated_set = set(rehabilitated_after_round)
        if rehabilitated_set:
            for row in logger.penalty_rows[-config.num_clients:]:
                client_id = int(row["client_id"])
                if client_id not in rehabilitated_set:
                    continue
                row["cumulative_penalty"] = penalties[client_id]
                row["magnitude_episode_penalty"] = magnitude_penalties[client_id]
                row["is_candidate"] = int(client_id in candidate_clients)
                row["candidate_episode_flags"] = candidate_flag_counts[client_id]
                row["candidate_episode_probes"] = candidate_probe_counts[client_id]
                row["is_suspected"] = int(client_id in suspected_clients)

        for client_id in range(config.num_clients):
            probes = dodge_probe_counts[client_id]
            logger.dodge_rows.append(
                {
                    "round": round_idx,
                    "client_id": client_id,
                    "is_suspected": int(client_id in suspected_clients),
                    "is_candidate": int(client_id in candidate_clients),
                    "candidate_episode_probes": candidate_probe_counts[client_id],
                    "candidate_episode_flags": candidate_flag_counts[client_id],
                    "episode_probes": probes,
                    "episode_flags": dodge_flag_counts[client_id],
                    "dodge_index": dodge_flag_counts[client_id] / probes if probes else "",
                    "lifetime_trap_flags": lifetime_trap_flags[client_id],
                }
            )

        evaluated_ids = set(detection_results)
        predicted = {
            client_id
            for client_id, result in detection_results.items()
            if (
                (
                    zero_responses_added.get(client_id, 0) > 0
                    or result.flagged
                )
                if is_v10
                else zero_responses_added.get(client_id, 0) > 0
                or result.joint_flag_count > 0
                if is_v9
                else result.flagged
            )
        }
        joint_predicted = {
            client_id
            for client_id, result in detection_results.items()
            if zero_responses_added.get(client_id, 0) > 0 or result.joint_flag_count
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
                "joint_true_positives": len(joint_predicted & actual),
                "joint_false_positives": len(joint_predicted - actual),
                "new_removals": len(removed_after_round),
                "new_rehabilitations": len(rehabilitated_after_round),
                "num_suspected": len(suspected_clients),
                "num_candidates": len(candidate_clients),
            }
        )

        if is_v10:
            quarantined_clients = (
                selection.trapped_clients
                | suspected_clients_at_round_start
                | suspected_clients
                | candidate_clients_at_round_start
                | candidate_clients
                | set(removed_after_round)
            )
        elif is_v9:
            quarantined_clients = (
                selection.trapped_clients
                | suspected_clients_at_round_start
                | suspected_clients
                | set(removed_after_round)
            )
        else:
            quarantined_clients = (
                selection.trapped_clients
                | candidate_clients_at_round_start
                | candidate_clients
            )
        aggregated_clients = [
            client_id
            for client_id in active_this_round
            if client_id not in quarantined_clients
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
                "num_candidate_clients": len(candidate_clients),
                "num_reference_eligible": len(reference_eligible_clients),
                "num_reference_probation": len(reference_probation_counts),
                "v11_cycle_cutoff": v11_last_cutoff if is_v11 else "",
                "num_trapped": len(selection.trapped_clients),
                "num_anchor_roster": len(selection.anchor_roster),
                "num_active_anchors": len(selection.anchors),
                "anchor_rotation_cycle": selection.anchor_rotation_cycle,
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
                "zero_penalties": zero_penalties.copy(),
                "magnitude_penalties": magnitude_penalties.copy(),
                "times_flagged": times_flagged.copy(),
                "times_trapped": times_trapped.copy(),
                "selector_state": selector.state_dict(),
                "coverage_trap_states": coverage_trap_states,
                "coverage_deltas": coverage_deltas,
                "coverage_norms": coverage_norms,
                "coverage_profiles": coverage_profiles,
                "coverage_history_scores": coverage_history_scores,
                "coverage_trap_ids": coverage_trap_ids,
                "coverage_observation_rounds": coverage_observation_rounds,
                "surveillance_trap_state": surveillance_trap_state,
                "surveillance_deltas": surveillance_deltas,
                "surveillance_profiles": surveillance_profiles,
                "surveillance_observation_rounds": surveillance_observation_rounds,
                "suspected_clients": sorted(suspected_clients),
                "candidate_clients": sorted(candidate_clients),
                "candidate_flag_counts": candidate_flag_counts.copy(),
                "candidate_probe_counts": candidate_probe_counts.copy(),
                "dodge_probe_counts": dodge_probe_counts.copy(),
                "dodge_flag_counts": dodge_flag_counts.copy(),
                "lifetime_trap_flags": lifetime_trap_flags.copy(),
                "zero_update_counts": zero_update_counts.copy(),
                "cycle_clean_counts": cycle_clean_counts.copy(),
                "cycle_strong_counts": cycle_strong_counts.copy(),
                "cycle_trusted_strong_counts": cycle_trusted_strong_counts.copy(),
                "reference_eligible_clients": sorted(reference_eligible_clients),
                "reference_probation_counts": reference_probation_counts.copy(),
                "v11_calibration_history": v11_calibration_history,
                "v11_norm_scale_history": v11_norm_scale_history,
                "v11_profile_scale_history": v11_profile_scale_history,
                "v11_last_cutoff": v11_last_cutoff,
                "sent_model_fingerprints": {
                    client_id: list(fingerprints)
                    for client_id, fingerprints in sent_model_fingerprints.items()
                },
                "sent_model_sketches": {
                    client_id: list(sketches)
                    for client_id, sketches in sent_model_sketches.items()
                },
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
                    "methodology_version": config.methodology_version,
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
                    "candidate_clients": len(candidate_clients),
                    "reference_eligible_clients": len(reference_eligible_clients),
                    "reference_probation_clients": len(reference_probation_counts),
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
            "final_zero_penalty": zero_penalties[client_id],
            "final_magnitude_episode_penalty": magnitude_penalties[client_id],
            "reference_eligible_at_end": int(client_id in reference_eligible_clients),
            "reference_probation_cycles": reference_probation_counts.get(client_id, ""),
            "cycle_clean_cycles": cycle_clean_counts[client_id],
            "cycle_strong_cycles": cycle_strong_counts[client_id],
            "cycle_trusted_strong_cycles": cycle_trusted_strong_counts[client_id],
            "suspected_at_end": int(client_id in suspected_clients),
            "candidate_at_end": int(client_id in candidate_clients),
            "lifetime_trap_flags": lifetime_trap_flags[client_id],
            "zero_update_count": zero_update_counts[client_id],
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
            "final_candidate_clients": len(candidate_clients),
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
    run_config["checkpoint_cleanup_on_success"] = True
    run_config["checkpoints_deleted_on_success"] = []
    logger.write_all(run_config)
    deleted_checkpoints = delete_successful_checkpoints(logger.run_dir)
    run_config["checkpoints_deleted_on_success"] = deleted_checkpoints
    logger.write_completion(run_config, completed_rounds)
    return str(logger.run_dir)


def delete_successful_checkpoints(run_dir: Path) -> list[str]:
    """Delete recovery snapshots only after a run has completed successfully."""
    run_dir = run_dir.resolve()
    checkpoint_paths = sorted(run_dir.glob("checkpoint_round_*.pt"))
    latest_path = run_dir / "latest_checkpoint.pt"
    if latest_path.is_file():
        checkpoint_paths.append(latest_path)

    deleted: list[str] = []
    for checkpoint_path in checkpoint_paths:
        if checkpoint_path.is_file() and checkpoint_path.parent.resolve() == run_dir:
            checkpoint_path.unlink()
            deleted.append(checkpoint_path.name)
    return deleted


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
    flush_file_to_disk(temporary_path)
    replace_with_retry(temporary_path, checkpoint_path)

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
    flush_file_to_disk(latest_temporary)
    replace_with_retry(latest_temporary, latest_path)


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


def build_layer_profile(
    returned_state: dict[str, torch.Tensor],
    received_state: dict[str, torch.Tensor],
    zero_epsilon: float,
) -> torch.Tensor:
    """Return scale-free per-parameter-tensor shares of the submitted update."""
    layer_norms = torch.stack(
        [
            (returned_state[key] - received_state[key]).float().norm()
            for key in floating_keys(received_state)
        ]
    )
    total = layer_norms.sum()
    if float(total.item()) < zero_epsilon:
        return torch.zeros_like(layer_norms)
    return layer_norms / total


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
