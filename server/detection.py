from __future__ import annotations

from dataclasses import dataclass
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
    local_losses: Mapping[int, float],
    reference: torch.Tensor,
    trapped_clients: set[int],
    round_idx: int,
    config: ExperimentConfig,
    observation_rounds: Mapping[int, int] | None = None,
) -> dict[int, DetectionResult]:
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

    observed_at = observation_rounds or {
        client_id: round_idx for client_id in deltas
    }
    early_loss_clients = [
        client_id
        for client_id in deltas
        if observed_at.get(client_id, round_idx) <= config.loss_check_rounds
        and client_id in local_losses
    ]
    loss_median = loss_mad = None
    loss_z_scores: dict[int, float] = {}
    if config.use_loss_check and len(early_loss_clients) >= config.mad_min_samples:
        loss_median_value, loss_mad_value, loss_scale = build_mad_statistics(
            [local_losses[client_id] for client_id in early_loss_clients],
            config.loss_mad_floor,
        )
        loss_median = loss_median_value
        loss_mad = loss_mad_value
        loss_z_scores = {
            client_id: (local_losses[client_id] - loss_median_value) / loss_scale
            for client_id in early_loss_clients
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
            loss_z_score=loss_z_scores.get(client_id),
            loss_median=loss_median,
            loss_mad=loss_mad,
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
    loss_z_score: float | None = None,
    loss_median: float | None = None,
    loss_mad: float | None = None,
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
            loss_z_score,
            loss_median,
            loss_mad,
            "zero_update",
        )

    similarity = cosine_similarity(delta, reference)
    large_norm_flag = (
        norm_z_score is not None
        and norm_z_score > config.magnitude_z_threshold
    )
    early_loss_low_norm_flag = (
        loss_z_score is not None
        and loss_z_score > config.loss_z_threshold
        and norm_z_score is not None
        and norm_z_score < config.loss_norm_z_threshold
    )
    flagged = large_norm_flag or early_loss_low_norm_flag
    if early_loss_low_norm_flag:
        penalty = max(
            config.early_loss_penalty,
            config.penalty_trap_flag if was_trapped else config.penalty_normal_flag,
        )
    elif large_norm_flag:
        penalty = config.penalty_trap_flag if was_trapped else config.penalty_normal_flag
    else:
        penalty = 0
    reason = (
        "large_norm_z"
        if large_norm_flag
        else "early_loss_low_norm"
        if early_loss_low_norm_flag
        else None
    )
    return DetectionResult(
        flagged,
        penalty,
        similarity,
        norm,
        norm_z_score,
        norm_median,
        norm_mad,
        loss_z_score,
        loss_median,
        loss_mad,
        reason,
    )
