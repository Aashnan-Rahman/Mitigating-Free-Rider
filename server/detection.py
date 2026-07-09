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
    if similarity < config.similarity_threshold:
        penalty = config.penalty_trap_flag if was_trapped else config.penalty_normal_flag
        return DetectionResult(
            flagged=True,
            penalty=penalty,
            cosine_similarity=similarity,
            delta_norm=norm,
            reason="similarity",
        )

    return DetectionResult(
        flagged=False,
        penalty=0,
        cosine_similarity=similarity,
        delta_norm=norm,
        reason=None,
    )
