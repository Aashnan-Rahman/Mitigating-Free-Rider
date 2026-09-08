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
    mahalanobis_distance: float | None
    reason: str | None


def evaluate_updates(
    deltas: Mapping[int, torch.Tensor],
    local_losses: Mapping[int, float],
    reference: torch.Tensor,
    trapped_clients: set[int],
    round_idx: int,
    config: ExperimentConfig,
) -> dict[int, DetectionResult]:
    md_scores, norm_z_scores = z_normalized_mahalanobis_scores(deltas, config)

    loss_threshold = None
    if config.use_loss_check and round_idx <= config.loss_check_rounds and local_losses:
        # Estimate the honest-loss distribution without using ground-truth
        # labels: low-norm candidates (the FR3 signature) cannot define their
        # own threshold. This implements percentile_75(honest_loss) with a
        # server-observable proxy for the honest reference set.
        reference_losses = [
            loss
            for client_id, loss in local_losses.items()
            if norm_z_scores.get(client_id, 0.0) >= config.loss_norm_z_threshold
        ]
        if len(reference_losses) < config.md_min_samples:
            reference_losses = list(local_losses.values())
        loss_values = torch.tensor(reference_losses, dtype=torch.float64)
        loss_threshold = float(torch.quantile(loss_values, config.loss_percentile / 100.0).item())
    results: dict[int, DetectionResult] = {}
    for client_id, delta in deltas.items():
        result = evaluate_update(
            delta,
            reference,
            client_id in trapped_clients,
            config,
            mahalanobis_distance=md_scores.get(client_id),
            norm_z_score=norm_z_scores.get(client_id),
            loss=local_losses.get(client_id),
            loss_threshold=loss_threshold,
        )
        results[client_id] = result
    return results


def cosine_similarity(delta: torch.Tensor, reference: torch.Tensor) -> float:
    if delta.numel() == 0 or reference.numel() == 0:
        return 0.0
    return float(F.cosine_similarity(delta.flatten(), reference.flatten(), dim=0).item())


def z_normalized_mahalanobis_scores(
    deltas: Mapping[int, torch.Tensor], config: ExperimentConfig
) -> tuple[dict[int, float], dict[int, float]]:
    """Return MD scores over z-normalized, update-distribution features.

    Using compact features keeps the covariance estimate well-conditioned even
    though a model update can have many more parameters than there are clients.
    Both unusually small and unusually large updates receive a high distance.
    """
    usable = {
        client_id: delta.detach().flatten().to(dtype=torch.float64, device="cpu")
        for client_id, delta in deltas.items()
        if delta.numel() and float(delta.norm().item()) >= config.zero_update_epsilon
    }
    if len(usable) < config.md_min_samples:
        return {}, {}

    client_ids = list(usable)
    rows = []
    for client_id in client_ids:
        update = usable[client_id]
        norm = update.norm().clamp_min(config.zero_update_epsilon)
        mean_abs = update.abs().mean().clamp_min(config.zero_update_epsilon)
        std = update.std(unbiased=False).clamp_min(config.zero_update_epsilon)
        rows.append(
            torch.stack(
                (
                    torch.log(norm),
                    torch.log(mean_abs),
                    torch.log(std),
                    update.abs().max() / norm,
                )
            )
        )
    features = torch.stack(rows)

    # Median/MAD z-normalization is resistant to a minority attack cluster.
    # The real scale floor prevents the small homogeneous suspicion groups
    # identified in false_detection_analysis-1.md from collapsing the scale.
    feature_center = features.median(dim=0).values
    feature_mad = (features - feature_center).abs().median(dim=0).values
    feature_scale = (config.md_mad_consistency * feature_mad).clamp_min(
        config.md_scale_floor
    )
    z_features = (features - feature_center) / feature_scale

    # Estimate feature correlation after winsorizing extremes. This avoids
    # counting the three magnitude-related features as independent evidence,
    # while preventing a 40% attack cluster from dominating the covariance.
    covariance_rows = z_features.clamp(
        min=-config.md_covariance_clip, max=config.md_covariance_clip
    )
    covariance = covariance_rows.T @ covariance_rows / max(len(client_ids) - 1, 1)
    diagonal = covariance.diag().clamp_min(config.md_covariance_regularization).sqrt()
    correlation = covariance / torch.outer(diagonal, diagonal)
    correlation += config.md_covariance_regularization * torch.eye(
        correlation.shape[0], dtype=correlation.dtype
    )
    precision = torch.linalg.pinv(correlation)
    squared = torch.einsum(
        "ni,ij,nj->n", z_features, precision, z_features
    ).clamp_min(0.0)
    distances = squared.sqrt()
    md = {client_id: float(distances[i].item()) for i, client_id in enumerate(client_ids)}
    norm_z = {
        client_id: float(z_features[i, 0].item()) for i, client_id in enumerate(client_ids)
    }
    return md, norm_z


def evaluate_update(
    delta: torch.Tensor,
    reference: torch.Tensor,
    was_trapped: bool,
    config: ExperimentConfig,
    *,
    mahalanobis_distance: float | None = None,
    norm_z_score: float | None = None,
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
            norm_z_score=None,
            mahalanobis_distance=None,
            reason="zero_update",
        )

    similarity = cosine_similarity(delta, reference)
    md_flag = (
        mahalanobis_distance is not None
        and mahalanobis_distance > config.mahalanobis_threshold
    )
    early_loss_flag = (
        loss_threshold is not None
        and loss is not None
        and loss > loss_threshold
        and (
            not config.loss_requires_low_norm
            or (norm_z_score is not None and norm_z_score < config.loss_norm_z_threshold)
        )
    )
    if md_flag or early_loss_flag:
        penalty = config.penalty_trap_flag if was_trapped else config.penalty_normal_flag
        return DetectionResult(
            flagged=True,
            penalty=penalty,
            cosine_similarity=similarity,
            delta_norm=norm,
            norm_z_score=norm_z_score,
            mahalanobis_distance=mahalanobis_distance,
            reason="z_norm_mahalanobis" if md_flag else "early_loss_low_norm",
        )

    return DetectionResult(
        flagged=False,
        penalty=0,
        cosine_similarity=similarity,
        delta_norm=norm,
        norm_z_score=norm_z_score,
        mahalanobis_distance=mahalanobis_distance,
        reason=None,
    )
