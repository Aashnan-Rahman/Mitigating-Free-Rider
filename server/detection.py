from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

import torch
import torch.nn.functional as F

from config import ExperimentConfig


@dataclass
class DetectionResult:
    flagged: bool
    penalty: int
    cosine_similarity: float | None
    delta_norm: float
    norm_z_score: float | None
    norm_median: float | None
    norm_mad: float | None
    loss_z_score: float | None
    loss_median: float | None
    loss_mad: float | None
    reason: str | None
    magnitude_flag: bool = False
    profile_flag: bool = False
    joint_flag_count: int = 0
    profile_score: float | None = None
    profile_z_score: float | None = None
    profile_median: float | None = None
    profile_mad: float | None = None


def combine_coverage_checks(results: list[DetectionResult]) -> DetectionResult:
    """Combine repeated coverage checks into one client-level decision.

    Every near-zero response contributes the configured send-back penalty.
    Nonzero checks contribute only the penalty already earned by joint
    magnitude/profile failure; one-signal anomalies contribute no points.
    """
    if not results:
        raise ValueError("At least one coverage result is required.")

    flagged = [result for result in results if result.flagged]
    if flagged:
        zero_updates = [result for result in flagged if result.reason == "zero_update"]
        representative = max(
            zero_updates or flagged,
            key=lambda result: abs(result.norm_z_score)
            if result.norm_z_score is not None
            else float("-inf"),
        )
        penalty = sum(result.penalty for result in flagged)
        return replace(
            representative,
            penalty=penalty,
            magnitude_flag=any(result.magnitude_flag for result in results),
            profile_flag=any(result.profile_flag for result in results),
            joint_flag_count=sum(result.joint_flag_count for result in results),
        )

    return replace(results[-1], flagged=False, penalty=0, reason=None)


def evaluate_suspicion_group(
    deltas: Mapping[int, torch.Tensor],
    profiles: Mapping[int, torch.Tensor],
    suspect_clients: set[int],
    anchor_clients: set[int],
    config: ExperimentConfig,
) -> dict[int, DetectionResult]:
    """Evaluate suspects against only the anchors that saw the same trap model."""
    valid_anchor_ids = [
        client_id
        for client_id in anchor_clients
        if client_id in deltas
        and float(deltas[client_id].norm().item()) >= config.zero_update_epsilon
    ]
    anchor_norms = [float(deltas[client_id].norm().item()) for client_id in valid_anchor_ids]
    median, mad, scale = build_mad_statistics(anchor_norms, config.mad_floor)
    anchor_vectors = [deltas[client_id] for client_id in valid_anchor_ids]
    reference = (
        torch.stack(anchor_vectors).median(dim=0).values
        if anchor_vectors
        else torch.zeros_like(next(iter(deltas.values())))
    )
    profile_statistics = build_profile_statistics(profiles, valid_anchor_ids, config)
    results: dict[int, DetectionResult] = {}
    for client_id in suspect_clients | anchor_clients:
        if client_id not in deltas:
            continue
        delta = deltas[client_id]
        norm = float(delta.norm().item())
        norm_z = (norm - median) / scale if anchor_norms else None
        base = evaluate_update(
            delta,
            reference,
            client_id in suspect_clients,
            config,
            norm_z_score=None,
            norm_median=median if anchor_norms else None,
            norm_mad=mad if anchor_norms else None,
        )
        magnitude_flag = (
            client_id in suspect_clients
            and norm_z is not None
            and abs(norm_z) > config.magnitude_z_threshold
            and base.reason != "zero_update"
        )
        base = apply_profile_decision(
            base,
            client_id,
            profiles,
            profile_statistics,
            magnitude_flag=magnitude_flag,
            anomaly_penalty=config.penalty_suspicion_flag,
            eligible=client_id in suspect_clients,
            norm_z_score=norm_z,
            magnitude_reason="anchor_norm_outlier",
            config=config,
        )
        results[client_id] = base
    return results


def apply_surveillance_penalties(
    results: Mapping[int, DetectionResult], config: ExperimentConfig
) -> dict[int, DetectionResult]:
    """Only a joint surveillance anomaly earns magnitude evidence."""
    return {
        client_id: (
            result
            if result.reason == "zero_update"
            else replace(
                result,
                penalty=(
                    config.penalty_normal_flag
                    if result.joint_flag_count
                    else 0
                ),
            )
        )
        for client_id, result in results.items()
    }


def should_rehabilitate(
    probe_count: int, flag_count: int, config: ExperimentConfig
) -> bool:
    if probe_count < config.dodge_min_probes:
        return False
    return flag_count / probe_count <= config.dodge_max_flag_rate


def merge_detection_results(
    existing: DetectionResult | None, additional: DetectionResult
) -> DetectionResult:
    """Combine independent decisions without losing zero, signal, or joint evidence."""
    if existing is None:
        return additional
    penalty = (existing.penalty if existing.flagged else 0) + (
        additional.penalty if additional.flagged else 0
    )
    if not existing.flagged and not additional.flagged:
        return existing
    representative = (
        additional
        if additional.reason == "zero_update" or existing.reason != "zero_update"
        else existing
    )
    reasons = [reason for reason in (existing.reason, additional.reason) if reason]
    return replace(
        representative,
        flagged=True,
        penalty=penalty,
        reason="+".join(dict.fromkeys(reasons)),
        magnitude_flag=existing.magnitude_flag or additional.magnitude_flag,
        profile_flag=existing.profile_flag or additional.profile_flag,
        joint_flag_count=existing.joint_flag_count + additional.joint_flag_count,
    )


def evaluate_zero_updates_only(
    deltas: Mapping[int, torch.Tensor], config: ExperimentConfig
) -> dict[int, DetectionResult]:
    """Apply the universal send-back check without ordinary magnitude flags."""
    results: dict[int, DetectionResult] = {}
    for client_id, delta in deltas.items():
        norm = float(delta.norm().item())
        if norm < config.zero_update_epsilon:
            results[client_id] = DetectionResult(
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
    return results


def build_mad_statistics(values: list[float], floor: float) -> tuple[float, float, float]:
    """Return median, raw MAD, and a non-collapsing MAD scale."""
    if not values:
        return 0.0, 0.0, floor
    tensor = torch.tensor(values, dtype=torch.float64)
    median = float(tensor.median().item())
    mad = float((tensor - median).abs().median().item())
    return median, mad, max(mad, floor)


def evaluate_updates(
    deltas: Mapping[int, torch.Tensor],
    profiles: Mapping[int, torch.Tensor],
    reference: torch.Tensor,
    trapped_clients: set[int],
    config: ExperimentConfig,
    reference_ids: set[int] | None = None,
) -> dict[int, DetectionResult]:
    """Evaluate updates using only tensors observable by the server."""
    norms = {
        client_id: float(delta.norm().item()) for client_id, delta in deltas.items()
    }
    if reference_ids is None:
        reference_ids = set(norms)
    usable_reference_ids = [
        client_id
        for client_id in reference_ids
        if client_id in norms and norms[client_id] >= config.zero_update_epsilon
    ]
    norm_median, norm_mad, norm_scale = build_mad_statistics(
        [norms[client_id] for client_id in usable_reference_ids], config.mad_floor
    )
    norm_z_scores = {
        client_id: (norm - norm_median) / norm_scale
        for client_id, norm in norms.items()
    }

    profile_statistics = build_profile_statistics(
        profiles, usable_reference_ids, config
    )
    results = {
        client_id: evaluate_update(
            delta,
            reference,
            client_id in trapped_clients,
            config,
            norm_z_score=norm_z_scores[client_id],
            norm_median=norm_median,
            norm_mad=norm_mad,
        )
        for client_id, delta in deltas.items()
    }
    return {
        client_id: apply_profile_decision(
            result,
            client_id,
            profiles,
            profile_statistics,
            magnitude_flag=result.magnitude_flag,
            anomaly_penalty=(
                config.penalty_trap_flag
                if client_id in trapped_clients
                else config.penalty_normal_flag
            ),
            eligible=True,
            norm_z_score=result.norm_z_score,
            magnitude_reason="norm_z_outlier",
            config=config,
        )
        for client_id, result in results.items()
    }


def build_profile_statistics(
    profiles: Mapping[int, torch.Tensor],
    reference_ids: list[int],
    config: ExperimentConfig,
) -> tuple[torch.Tensor | None, float, float, float]:
    available = [profiles[client_id] for client_id in reference_ids if client_id in profiles]
    if not available:
        return None, 0.0, 0.0, config.profile_mad_floor
    center = torch.stack(available).median(dim=0).values
    distances = [float((profile - center).norm().item()) for profile in available]
    median, mad, scale = build_mad_statistics(distances, config.profile_mad_floor)
    return center, median, mad, scale


def apply_profile_decision(
    base: DetectionResult,
    client_id: int,
    profiles: Mapping[int, torch.Tensor],
    statistics: tuple[torch.Tensor | None, float, float, float],
    *,
    magnitude_flag: bool,
    anomaly_penalty: int,
    eligible: bool,
    norm_z_score: float | None,
    magnitude_reason: str,
    config: ExperimentConfig,
) -> DetectionResult:
    if base.reason == "zero_update":
        return replace(base, norm_z_score=norm_z_score)
    center, median, mad, scale = statistics
    profile_score = (
        float((profiles[client_id] - center).norm().item())
        if center is not None and client_id in profiles
        else None
    )
    profile_z = (
        (profile_score - median) / scale if profile_score is not None else None
    )
    profile_flag = bool(
        eligible
        and profile_z is not None
        and profile_z > config.profile_z_threshold
    )
    magnitude_flag = bool(eligible and magnitude_flag)
    anomalous = magnitude_flag or profile_flag
    joint = magnitude_flag and profile_flag
    if joint:
        reason = f"{magnitude_reason}+layer_profile_outlier"
    elif magnitude_flag:
        reason = magnitude_reason
    elif profile_flag:
        reason = "layer_profile_outlier"
    else:
        reason = None
    return replace(
        base,
        flagged=anomalous,
        penalty=anomaly_penalty if joint else 0,
        norm_z_score=norm_z_score,
        reason=reason,
        magnitude_flag=magnitude_flag,
        profile_flag=profile_flag,
        joint_flag_count=int(joint),
        profile_score=profile_score,
        profile_z_score=profile_z,
        profile_median=median if center is not None else None,
        profile_mad=mad if center is not None else None,
    )


def cosine_similarity(delta: torch.Tensor, reference: torch.Tensor) -> float:
    """Diagnostic only; cosine never participates in a flag decision."""
    if delta.numel() == 0 or reference.numel() == 0:
        return 0.0
    return float(F.cosine_similarity(delta.flatten(), reference.flatten(), dim=0).item())


def evaluate_update(
    delta: torch.Tensor,
    reference: torch.Tensor,
    was_trapped: bool,
    config: ExperimentConfig,
    *,
    norm_z_score: float | None = None,
    norm_median: float | None = None,
    norm_mad: float | None = None,
) -> DetectionResult:
    norm = float(delta.norm().item())
    if norm < config.zero_update_epsilon:
        return DetectionResult(
            True,
            config.penalty_zero_update,
            None,
            norm,
            norm_z_score,
            norm_median,
            norm_mad,
            None,
            None,
            None,
            "zero_update",
        )

    similarity = cosine_similarity(delta, reference)
    norm_outlier_flag = (
        norm_z_score is not None
        and abs(norm_z_score) > config.magnitude_z_threshold
    )
    flagged = norm_outlier_flag
    if norm_outlier_flag:
        penalty = config.penalty_trap_flag if was_trapped else config.penalty_normal_flag
    else:
        penalty = 0
    reason = "norm_z_outlier" if norm_outlier_flag else None
    return DetectionResult(
        flagged,
        penalty,
        similarity,
        norm,
        norm_z_score,
        norm_median,
        norm_mad,
        None,
        None,
        None,
        reason,
        magnitude_flag=norm_outlier_flag,
    )
