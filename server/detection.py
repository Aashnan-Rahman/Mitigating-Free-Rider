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
    reason: str | None


def build_mad_threshold(norms: list[float], config: ExperimentConfig) -> tuple[float, float, float]:
    if not norms:
        return 0.0, config.mad_floor, config.mad_floor
    values = torch.tensor(norms, dtype=torch.float64)
    median = float(values.median().item())
    mad = float((values - median).abs().median().item())
    scale = max(mad, config.mad_floor)
    return median, mad, median + config.mad_threshold_k * scale


def evaluate_updates(
    deltas: Mapping[int, torch.Tensor],
    local_losses: Mapping[int, float],
    reference: torch.Tensor,
    trapped_clients: set[int],
    round_idx: int,
    config: ExperimentConfig,
) -> dict[int, DetectionResult]:
    norms = {client_id: float(delta.norm().item()) for client_id, delta in deltas.items()}
    threshold = None
    median = mad = 0.0
    if config.use_batch_mad_threshold:
        median, mad, threshold = build_mad_threshold(list(norms.values()), config)

    loss_threshold = None
    if config.use_loss_check and round_idx <= config.loss_check_rounds and local_losses:
        loss_values = torch.tensor(list(local_losses.values()), dtype=torch.float64)
        loss_threshold = float(torch.quantile(loss_values, config.loss_percentile / 100.0).item())
    results: dict[int, DetectionResult] = {}
    for client_id, delta in deltas.items():
        result = evaluate_update(
            delta,
            reference,
            client_id in trapped_clients,
            config,
            norm_threshold=threshold,
            norm_median=median,
            norm_mad=mad,
            loss=local_losses.get(client_id),
            loss_threshold=loss_threshold,
        )
        results[client_id] = result
    return results


def cosine_similarity(delta: torch.Tensor, reference: torch.Tensor) -> float:
    if delta.numel() == 0 or reference.numel() == 0:
        return 0.0
    return float(F.cosine_similarity(delta.flatten(), reference.flatten(), dim=0).item())


def evaluate_update(
    delta: torch.Tensor,
    reference: torch.Tensor,
    was_trapped: bool,
    config: ExperimentConfig,
    *,
    norm_threshold: float | None = None,
    norm_median: float = 0.0,
    norm_mad: float = 0.0,
    loss: float | None = None,
    loss_threshold: float | None = None,
) -> DetectionResult:
    norm = float(delta.norm().item())
    if norm < config.zero_update_epsilon:
        return DetectionResult(
            flagged=True,
            penalty=config.penalty_zero_update,
            cosine_similarity=None,
            delta_norm=norm,
            reason="zero_update",
        )

    similarity = cosine_similarity(delta, reference)
    magnitude_flag = norm_threshold is not None and norm > norm_threshold
    small_norm_flag = (
        norm_threshold is not None
        and norm_mad > 0
        and norm < norm_median - config.magnitude_z_threshold * max(norm_mad, config.mad_floor)
    )
    loss_flag = (
        loss_threshold is not None
        and loss is not None
        and loss > loss_threshold
        and (not config.loss_requires_small_norm or small_norm_flag)
    )
    if magnitude_flag or loss_flag:
        penalty = config.penalty_trap_flag if was_trapped else config.penalty_normal_flag
        return DetectionResult(
            flagged=True,
            penalty=penalty,
            cosine_similarity=similarity,
            delta_norm=norm,
            reason="magnitude" if magnitude_flag else "loss",
        )

    return DetectionResult(
        flagged=False,
        penalty=0,
        cosine_similarity=similarity,
        delta_norm=norm,
        reason=None,
    )
