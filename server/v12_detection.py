from __future__ import annotations

import math
from dataclasses import replace
from statistics import median
from typing import Mapping

import torch

from config import ExperimentConfig
from server.aggregation import floating_keys
from server.v11_detection import (
    MAD_NORMAL_CONSISTENCY,
    cutoff_from_false_alarm_budget,
    evaluate_v11_cycle,
)


HISTORY_SIGNATURES = ("mean_replay", "trajectory_replay")


def compact_sketch(vector: torch.Tensor, width: int, seed: int) -> torch.Tensor:
    """Return a small deterministic linear sketch without retaining an update."""
    flat = vector.detach().flatten().float().cpu()
    if width <= 0:
        raise ValueError("Sketch width must be positive")
    if flat.numel() == 0:
        return torch.zeros(width, dtype=torch.float32)
    padding = (-flat.numel()) % width
    if padding:
        flat = torch.nn.functional.pad(flat, (0, padding))
    blocks = flat.view(-1, width)
    block_ids = torch.arange(blocks.shape[0], dtype=torch.int64).unsqueeze(1)
    bucket_ids = torch.arange(width, dtype=torch.int64).unsqueeze(0)
    hashes = block_ids * 1_103_515_245 + bucket_ids * 12_345 + int(seed)
    signs = ((hashes >> 16) & 1).mul(2).sub(1).to(torch.float32)
    return (blocks * signs).sum(dim=0)


def model_state_sketch(
    state: Mapping[str, torch.Tensor], width: int, seed: int
) -> torch.Tensor:
    pieces = [state[key].detach().flatten().float().cpu() for key in floating_keys(state)]
    vector = torch.cat(pieces) if pieces else torch.empty(0, dtype=torch.float32)
    return compact_sketch(vector, width, seed)


def history_reconstruction_scores(
    update_sketch: torch.Tensor,
    sent_history: list[torch.Tensor],
    window: int,
    epsilon: float,
) -> dict[str, float]:
    """Score how well an update is explained using only server-sent history."""
    if len(sent_history) < 2 or float(update_sketch.norm().item()) < epsilon:
        return {}
    current = sent_history[-1]
    scores: dict[str, float] = {}

    replay_scores: list[float] = []
    for size in range(2, min(window, len(sent_history)) + 1):
        predicted = torch.stack(sent_history[-size:]).mean(dim=0) - current
        replay_scores.append(_explainability(update_sketch, predicted, epsilon))
    if replay_scores:
        scores["mean_replay"] = max(replay_scores)

    recent = sent_history[-min(window + 1, len(sent_history)) :]
    differences = [recent[index] - recent[index - 1] for index in range(1, len(recent))]
    if differences:
        predicted = torch.stack(differences).mean(dim=0)
        scores["trajectory_replay"] = _explainability(
            update_sketch, predicted, epsilon
        )
    return scores


def _explainability(
    observed: torch.Tensor, predicted: torch.Tensor, epsilon: float
) -> float:
    denominator = float(observed.norm().item() + predicted.norm().item())
    relative_error = float((observed - predicted).norm().item()) / max(
        denominator, epsilon
    )
    return -math.log(max(relative_error, epsilon))


def one_sided_robust_z(
    values: Mapping[int, float], reference_ids: set[int], epsilon: float
) -> dict[int, float]:
    """Score a high-side anomaly without letting a high minority inflate scale."""
    reference = [float(values[item]) for item in reference_ids if item in values]
    if not reference:
        return {}
    center = float(median(reference))
    lower_deviations = [center - value for value in reference if value <= center]
    raw_scale = float(median(lower_deviations)) if lower_deviations else 0.0
    scale = max(MAD_NORMAL_CONSISTENCY * raw_scale, epsilon)
    return {client_id: (float(value) - center) / scale for client_id, value in values.items()}


def binomial_cluster_minimum(population: int, false_alarm_rate: float) -> int:
    """Smallest cohort size whose null upper-tail probability is within alpha."""
    if population <= 0:
        return 1
    probability = min(max(false_alarm_rate, 1e-12), 1.0 - 1e-12)
    for count in range(1, population + 1):
        tail = sum(
            math.comb(population, item)
            * probability**item
            * (1.0 - probability) ** (population - item)
            for item in range(count, population + 1)
        )
        if tail <= false_alarm_rate:
            return count
    return population


def evaluate_v12_cycle(
    *,
    coverage_norms: Mapping[int, list[float]],
    coverage_profiles: Mapping[int, list[torch.Tensor]],
    coverage_history_scores: Mapping[int, list[dict[str, float]]],
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
    """Evaluate static outliers plus paired, attack-agnostic history reconstruction."""
    evidence = evaluate_v11_cycle(
        coverage_norms=coverage_norms,
        coverage_profiles=coverage_profiles,
        coverage_trap_ids=coverage_trap_ids,
        coverage_observation_rounds=coverage_observation_rounds,
        active_clients=active_clients,
        checks=checks,
        config=config,
        trusted_reference_clients=trusted_reference_clients,
        calibration_history=calibration_history,
        norm_scale_history=norm_scale_history,
        profile_scale_history=profile_scale_history,
    )
    if not evidence["reference_valid"]:
        return evidence

    static_signatures: dict[int, list[set[str]]] = evidence["signatures"]  # type: ignore[assignment]
    combined_signatures = {
        client_id: [set(item) for item in signatures]
        for client_id, signatures in static_signatures.items()
    }
    history_z_by_client: dict[int, list[dict[str, float]]] = {
        client_id: [dict() for _ in scores]
        for client_id, scores in coverage_history_scores.items()
    }
    history_cutoff = cutoff_from_false_alarm_budget(config, checks, [])

    for trap_id in range(checks):
        reference_ids = set(active_clients)
        if trusted_reference_clients is not None:
            reference_ids &= trusted_reference_clients
        for signature in HISTORY_SIGNATURES:
            values: dict[int, float] = {}
            indices: dict[int, int] = {}
            for client_id, observations in coverage_history_scores.items():
                if client_id not in active_clients:
                    continue
                for index, scores in enumerate(observations):
                    if coverage_trap_ids[client_id][index] == trap_id and signature in scores:
                        values[client_id] = float(scores[signature])
                        indices[client_id] = index
            z_scores = one_sided_robust_z(
                values, reference_ids, config.cycle_scale_epsilon
            )
            for client_id, z_score in z_scores.items():
                index = indices[client_id]
                history_z_by_client[client_id][index][signature] = z_score
                if z_score > history_cutoff:
                    combined_signatures.setdefault(
                        client_id,
                        [set() for _ in range(checks)],
                    )[trap_id].add(signature)

    coherent_by_client: dict[int, set[str]] = {}
    for client_id, signatures in combined_signatures.items():
        if len(signatures) >= 2:
            coherent_by_client[client_id] = set.intersection(*signatures)
        else:
            coherent_by_client[client_id] = set()

    cohort_minimum = binomial_cluster_minimum(
        len(active_clients), config.cycle_target_false_alarm_rate
    )
    # A precise averaged-model reconstruction dominates the less specific
    # trajectory hypothesis. Honest training can legitimately align with the
    # global trajectory, so do not let that secondary signal quarantine extra
    # clients when a cohort is already explained by mean replay.
    mean_replay_count = sum(
        "mean_replay" in signatures for signatures in coherent_by_client.values()
    )
    if mean_replay_count >= cohort_minimum:
        for signatures in combined_signatures.values():
            for observation in signatures:
                observation.discard("trajectory_replay")
        coherent_by_client = {
            client_id: set.intersection(*signatures)
            if len(signatures) >= 2
            else set()
            for client_id, signatures in combined_signatures.items()
        }

    static_counts: dict[str, int] = {}
    for signatures in coherent_by_client.values():
        for signature in signatures - set(HISTORY_SIGNATURES) - {"zero_update"}:
            static_counts[signature] = static_counts.get(signature, 0) + 1
    cohort_signatures = {
        signature
        for signature, count in static_counts.items()
        if count >= cohort_minimum
    }

    coherent_strong: dict[int, bool] = {}
    flag_counts: dict[int, int] = {}
    cycle_scores: dict[int, float] = dict(evidence["cycle_scores"])  # type: ignore[arg-type]
    results = dict(evidence["results"])  # type: ignore[arg-type]
    trajectory_count = sum(
        "trajectory_replay" in item for item in coherent_by_client.values()
    )
    mean_count = sum("mean_replay" in item for item in coherent_by_client.values())
    for client_id, signatures in combined_signatures.items():
        flag_counts[client_id] = sum(bool(item) for item in signatures)
        coherent = coherent_by_client.get(client_id, set())
        history_strong = (
            "mean_replay" in coherent and mean_count >= cohort_minimum
        ) or (
            "trajectory_replay" in coherent and trajectory_count >= cohort_minimum
        )
        multimodal_static = "profile_high" in coherent and bool(
            coherent & {"norm_high", "norm_low"}
        )
        cohort_static = bool(coherent & cohort_signatures)
        coherent_strong[client_id] = history_strong or multimodal_static or cohort_static

        history_scores = [
            value
            for observation in history_z_by_client.get(client_id, [])
            for value in observation.values()
            if math.isfinite(value)
        ]
        if history_scores:
            cycle_scores[client_id] = max(
                cycle_scores.get(client_id, float("-inf")), max(history_scores)
            )
        if any(set(item) & set(HISTORY_SIGNATURES) for item in signatures):
            base = results.get(client_id)
            if base is not None:
                history_reasons = sorted(
                    set().union(*signatures) & set(HISTORY_SIGNATURES)
                )
                results[client_id] = replace(
                    base,
                    flagged=True,
                    reason="+".join(history_reasons),
                )

    evidence.update(
        {
            "results": results,
            "flags": flag_counts,
            "coherent_strong": coherent_strong,
            "cycle_scores": cycle_scores,
            "signatures": combined_signatures,
            "history_z_scores": history_z_by_client,
            "cohort_minimum": cohort_minimum,
        }
    )
    return evidence
