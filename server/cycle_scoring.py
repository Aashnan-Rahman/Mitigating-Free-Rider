from __future__ import annotations


def cycle_classification(joint_failures: int, checks: int) -> str:
    """Classify only joint magnitude/profile failures; isolated signals are clear."""
    if checks <= 0:
        raise ValueError("checks must be positive")
    if checks >= 2 and joint_failures >= 2:
        return "S"
    if joint_failures >= 1:
        return "C"
    return "clear"


def score_change(
    classification: str,
    clear_reward: float = 0.5,
    candidate_cost: float = 1.0,
    suspicious_cost: float = 2.0,
) -> float:
    return {
        "clear": clear_reward,
        "C": -candidate_cost,
        "S": -suspicious_cost,
    }[classification]


def score_requires_removal(score: float, threshold: float = -4.0) -> bool:
    return score <= threshold


def sendbacks_require_removal(
    count: int, round_idx: int, warmup_rounds: int, limit: int = 5
) -> bool:
    return round_idx >= warmup_rounds and count >= limit
