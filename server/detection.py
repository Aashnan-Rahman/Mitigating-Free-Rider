from __future__ import annotations

from dataclasses import dataclass

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
    reason: str | None


def cosine_similarity(delta: torch.Tensor, reference: torch.Tensor) -> float:
    if delta.numel() == 0 or reference.numel() == 0:
        return 0.0
    return float(F.cosine_similarity(delta.flatten(), reference.flatten(), dim=0).item())


def evaluate_update(
    delta: torch.Tensor,
    reference: torch.Tensor,
    was_trapped: bool,
    config: ExperimentConfig,
    norm_z_score: float | None = None,
) -> DetectionResult:
    norm = float(delta.norm().item())
    if norm < config.zero_update_epsilon:
        return DetectionResult(
            flagged=True,
            penalty=config.penalty_zero_update,
            cosine_similarity=None,
            delta_norm=norm,
            norm_z_score=norm_z_score,
            reason="zero_update",
        )

    similarity = cosine_similarity(delta, reference)
    similarity_flagged = similarity > config.similarity_threshold
    magnitude_flagged = (
        config.use_magnitude_check
        and norm_z_score is not None
        and norm_z_score > config.magnitude_z_threshold
    )
    if magnitude_flagged:
        penalty = config.penalty_trap_flag if was_trapped else config.penalty_normal_flag
        reason = "magnitude_outlier"
        return DetectionResult(
            flagged=True,
            penalty=penalty,
            cosine_similarity=similarity,
            delta_norm=norm,
            norm_z_score=norm_z_score,
            reason=reason,
        )

    return DetectionResult(
        flagged=False,
        penalty=0,
        cosine_similarity=similarity,
        delta_norm=norm,
        norm_z_score=norm_z_score,
        reason=None,
    )


def evaluate_update_with_norm_threshold(
    delta: torch.Tensor,
    reference: torch.Tensor,
    was_trapped: bool,
    config: ExperimentConfig,
    norm_z_score: float | None,
    norm_threshold: float,
) -> DetectionResult:
    norm = float(delta.norm().item())
    if norm < config.zero_update_epsilon:
        return DetectionResult(
            flagged=True,
            penalty=config.penalty_zero_update,
            cosine_similarity=None,
            delta_norm=norm,
            norm_z_score=norm_z_score,
            reason="zero_update",
        )

    similarity = cosine_similarity(delta, reference)
    if config.use_magnitude_check and norm > norm_threshold:
        penalty = config.penalty_trap_flag if was_trapped else config.penalty_normal_flag
        return DetectionResult(
            flagged=True,
            penalty=penalty,
            cosine_similarity=similarity,
            delta_norm=norm,
            norm_z_score=norm_z_score,
            reason="mad_norm_outlier",
        )

    return DetectionResult(
        flagged=False,
        penalty=0,
        cosine_similarity=similarity,
        delta_norm=norm,
        norm_z_score=norm_z_score,
        reason=None,
    )
