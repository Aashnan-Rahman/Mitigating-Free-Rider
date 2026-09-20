from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import torch


@dataclass
class DetectorOutput:
    """Scores and decisions returned by a comparison detector."""

    scores: dict[int, float]
    flags: dict[int, bool]
    metadata: dict[str, Any] = field(default_factory=dict)


def upper_z_flags(
    scores: dict[int, float], threshold: float, epsilon: float = 1e-12
) -> tuple[dict[int, bool], dict[int, float]]:
    """Flag high outliers using the population z-score used by FRIDA loss MIA."""
    if not scores:
        return {}, {}
    client_ids = list(scores)
    values = torch.tensor([scores[item] for item in client_ids], dtype=torch.float64)
    mean = values.mean()
    std = values.std(unbiased=False)
    if float(std) <= epsilon:
        z_values = torch.zeros_like(values)
    else:
        z_values = (values - mean) / std
    z_scores = {item: float(z_values[index]) for index, item in enumerate(client_ids)}
    return (
        {item: z_scores[item] >= threshold for item in client_ids},
        z_scores,
    )
