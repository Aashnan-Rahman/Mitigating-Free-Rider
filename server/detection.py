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


def combine_coverage_checks(results: list[DetectionResult]) -> DetectionResult:
    """Combine repeated coverage checks into one client-level decision.

    Every near-zero response contributes the configured send-back penalty.
    Other anomalous checks contribute one point each.
    """
    if not results:
        raise ValueError("At least one coverage result is required.")

    flagged = [result for result in results if result.flagged]
    if flagged:
        zero_updates = [result for result in flagged if result.reason == "zero_update"]
        representative = max(
            zero_updates or flagged,
            key=lambda result: result.norm_z_score
            if result.norm_z_score is not None
            else float("-inf"),
        )
        penalty = sum(
            result.penalty if result.reason == "zero_update" else 1
            for result in flagged
        )
        return replace(representative, penalty=penalty)

    return replace(results[-1], flagged=False, penalty=0, reason=None)


def evaluate_suspicion_group(
    deltas: Mapping[int, torch.Tensor],
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
    anchor_vectors = [
        deltas[client_id] for client_id in valid_anchor_ids
    ]
    reference = (
        torch.stack(anchor_vectors).median(dim=0).values
        if anchor_vectors
        else torch.zeros_like(next(iter(deltas.values())))
    )
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
        if (
            client_id in suspect_clients
            and norm_z is not None
            and abs(norm_z) > config.magnitude_z_threshold
            and base.reason != "zero_update"
        ):
            base = replace(
                base,
                flagged=True,
                penalty=config.penalty_suspicion_flag,
                norm_z_score=norm_z,
                reason="anchor_norm_outlier",
            )
        else:
            base = replace(base, norm_z_score=norm_z)
        results[client_id] = base
    return results


def apply_surveillance_penalties(
    results: Mapping[int, DetectionResult], config: ExperimentConfig
) -> dict[int, DetectionResult]:
    """A one-check surveillance magnitude flag contributes one point."""
    return {
        client_id: (
            result
            if result.reason == "zero_update" or not result.flagged
            else replace(result, penalty=config.penalty_normal_flag)
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
    """Combine independent decisions without losing either one's penalty."""
    if existing is None:
        return additional
    penalty = (existing.penalty if existing.flagged else 0) + (
        additional.penalty if additional.flagged else 0
    )
    if not penalty:
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
    reference: torch.Tensor,
    trapped_clients: set[int],
    config: ExperimentConfig,
) -> dict[int, DetectionResult]:
    """Evaluate updates using only tensors observable by the server."""
    norms = {
        client_id: float(delta.norm().item()) for client_id, delta in deltas.items()
    }
    norm_median, norm_mad, norm_scale = build_mad_statistics(
        list(norms.values()), config.mad_floor
    )
    norm_z_scores = {
        client_id: (norm - norm_median) / norm_scale
        for client_id, norm in norms.items()
    }

    return {
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
    large_norm_flag = (
        norm_z_score is not None
        and norm_z_score > config.magnitude_z_threshold
    )
    flagged = large_norm_flag
    if large_norm_flag:
        penalty = config.penalty_trap_flag if was_trapped else config.penalty_normal_flag
    else:
        penalty = 0
    reason = "large_norm_z" if large_norm_flag else None
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
    )
