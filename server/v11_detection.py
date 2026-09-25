from __future__ import annotations

import math
from statistics import NormalDist, median
from typing import Mapping

import torch

from config import ExperimentConfig
from server.detection import DetectionResult, combine_coverage_checks


MAD_NORMAL_CONSISTENCY = 1.0 / NormalDist().inv_cdf(0.75)


def cutoff_from_false_alarm_budget(
    config: ExperimentConfig,
    checks: int,
    calibration_history: list[list[float]],
) -> float:
    """Derive a cycle cutoff from a risk budget and prior R-cycle scores only."""
    tail_opportunities = max(1, checks * 3)  # norm low/high plus profile high
    base = NormalDist().inv_cdf(
        1.0 - config.cycle_target_false_alarm_rate / tail_opportunities
    )
    prior_cycles = calibration_history[-config.cycle_calibration_window_cycles :]
    cycle_cutoffs = [
        empirical_upper_cutoff(scores, config.cycle_target_false_alarm_rate)
        for scores in prior_cycles
        if scores
    ]
    return max(base, float(median(cycle_cutoffs))) if cycle_cutoffs else base


def empirical_upper_cutoff(values: list[float], tail_rate: float) -> float:
    ordered = sorted(float(value) for value in values)
    rank = max(0, min(len(ordered) - 1, math.ceil((1.0 - tail_rate) * len(ordered)) - 1))
    return ordered[rank]


def corrected_scale(
    values: list[float],
    prior_scales: list[float],
    config: ExperimentConfig,
) -> tuple[float, float, float]:
    """Return median, raw MAD, and a history-stabilized robust sigma estimate."""
    if not values:
        return 0.0, 0.0, config.cycle_scale_epsilon
    center = float(median(values))
    raw_mad = float(median(abs(value - center) for value in values))
    current = max(MAD_NORMAL_CONSISTENCY * raw_mad, config.cycle_scale_epsilon)
    if not prior_scales:
        return center, raw_mad, current
    historical = max(float(median(prior_scales)), config.cycle_scale_epsilon)
    weight = len(values) / (len(values) + config.cycle_scale_prior_strength)
    effective = math.sqrt(weight * current * current + (1.0 - weight) * historical * historical)
    return center, raw_mad, max(effective, config.cycle_scale_epsilon)


def evaluate_v11_cycle(
    *,
    coverage_norms: Mapping[int, list[float]],
    coverage_profiles: Mapping[int, list[torch.Tensor]],
    coverage_trap_ids: Mapping[int, list[int]],
    coverage_observation_rounds: Mapping[int, list[int]],
    active_clients: set[int],
    checks: int,
    config: ExperimentConfig,
    trusted_reference_clients: set[int] | None,
    calibration_history: list[list[float]],
    norm_scale_history: list[float],
    profile_scale_history: list[float],
) -> dict[str, object]:
    """Evaluate a complete v11 cycle from scalar norms and small layer profiles."""
    cutoff = cutoff_from_false_alarm_budget(config, checks, calibration_history)
    per_client_results: dict[int, list[DetectionResult]] = {}
    per_client_signatures: dict[int, list[set[str]]] = {}
    per_client_component_scores: dict[int, list[float]] = {}
    current_norm_scales: list[float] = []
    current_profile_scales: list[float] = []
    frozen_reference_ids: set[int] = set()
    reference_valid = True

    for trap_id in range(checks):
        trap_norms: dict[int, float] = {}
        trap_profiles: dict[int, torch.Tensor] = {}
        for client_id, norms in coverage_norms.items():
            if client_id not in active_clients:
                continue
            for index, norm in enumerate(norms):
                if coverage_trap_ids[client_id][index] == trap_id:
                    trap_norms[client_id] = float(norm)
                    trap_profiles[client_id] = coverage_profiles[client_id][index]

        reference_ids = set(trap_norms)
        if trusted_reference_clients is not None:
            reference_ids &= trusted_reference_clients
            if len(reference_ids) < config.cycle_min_reference_clients:
                reference_valid = False
                break
        frozen_reference_ids.update(reference_ids)
        usable_reference_ids = {
            client_id
            for client_id in reference_ids
            if trap_norms[client_id] >= config.zero_update_epsilon
        }
        if not usable_reference_ids:
            reference_valid = False
            break

        norm_center, norm_mad, norm_scale = corrected_scale(
            [trap_norms[client_id] for client_id in usable_reference_ids],
            norm_scale_history,
            config,
        )
        current_norm_scales.append(norm_scale)

        profile_stack = torch.stack(
            [trap_profiles[client_id].detach().float().cpu() for client_id in usable_reference_ids]
        )
        profile_center = profile_stack.median(dim=0).values
        profile_distances = {
            client_id: float(
                torch.linalg.vector_norm(
                    trap_profiles[client_id].detach().float().cpu() - profile_center
                ).item()
            )
            for client_id in trap_profiles
        }
        profile_center_distance, profile_mad, profile_scale = corrected_scale(
            [profile_distances[client_id] for client_id in usable_reference_ids],
            profile_scale_history,
            config,
        )
        current_profile_scales.append(profile_scale)

        for client_id, norm in trap_norms.items():
            if norm < config.zero_update_epsilon:
                result = DetectionResult(
                    True,
                    config.penalty_zero_update,
                    None,
                    norm,
                    None,
                    norm_center,
                    norm_mad,
                    None,
                    None,
                    None,
                    "zero_update",
                )
                signatures = {"zero_update"}
                component_score = float("inf")
            else:
                norm_z = (norm - norm_center) / norm_scale
                profile_score = profile_distances[client_id]
                profile_z = (profile_score - profile_center_distance) / profile_scale
                magnitude_flag = abs(norm_z) > cutoff
                profile_flag = profile_z > cutoff
                signatures: set[str] = set()
                if magnitude_flag:
                    signatures.add("norm_high" if norm_z > 0 else "norm_low")
                if profile_flag:
                    signatures.add("profile_high")
                flagged = bool(signatures)
                result = DetectionResult(
                    flagged,
                    0,
                    None,
                    norm,
                    norm_z,
                    norm_center,
                    norm_mad,
                    None,
                    None,
                    None,
                    "+".join(sorted(signatures)) if signatures else None,
                    magnitude_flag=magnitude_flag,
                    profile_flag=profile_flag,
                    joint_flag_count=int(magnitude_flag and profile_flag),
                    profile_score=profile_score,
                    profile_z_score=profile_z,
                    profile_median=profile_center_distance,
                    profile_mad=profile_mad,
                )
                component_score = max(abs(norm_z), profile_z)
            per_client_results.setdefault(client_id, []).append(result)
            per_client_signatures.setdefault(client_id, []).append(signatures)
            per_client_component_scores.setdefault(client_id, []).append(component_score)

    checks_used = {
        client_id: len(coverage_norms.get(client_id, []))
        for client_id in active_clients
        if client_id in coverage_norms
    }
    if not reference_valid:
        per_client_results.clear()
        per_client_signatures.clear()
        per_client_component_scores.clear()
        for client_id in checks_used:
            for norm in coverage_norms[client_id]:
                if norm < config.zero_update_epsilon:
                    per_client_results.setdefault(client_id, []).append(
                        DetectionResult(
                            True,
                            config.penalty_zero_update,
                            None,
                            norm,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            "zero_update",
                        )
                    )

    combined_results = {
        client_id: combine_coverage_checks(results)
        for client_id, results in per_client_results.items()
        if results
    }
    coherent_strong = {
        client_id: (
            len(signatures) >= 2
            and bool(set.intersection(*signatures))
            and "zero_update" not in set.intersection(*signatures)
        )
        for client_id, signatures in per_client_signatures.items()
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
    return {
        "results": combined_results,
        "checks": checks_used,
        "flags": flag_counts,
        "joint_flags": joint_counts,
        "zero_counts": zero_counts,
        "decision_rounds": {
            client_id: max(coverage_observation_rounds[client_id])
            for client_id in checks_used
        },
        "reference_outliers": set(),
        "reference_valid": reference_valid,
        "coherent_strong": coherent_strong,
        "signatures": per_client_signatures,
        "cycle_scores": {
            client_id: max(scores)
            for client_id, scores in per_client_component_scores.items()
            if scores and all(math.isfinite(score) for score in scores)
        },
        "frozen_reference_ids": frozen_reference_ids,
        "norm_scales": current_norm_scales,
        "profile_scales": current_profile_scales,
        "cutoff": cutoff,
    }
