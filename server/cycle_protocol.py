from __future__ import annotations

from dataclasses import dataclass

from config import ExperimentConfig


@dataclass(frozen=True)
class CycleTransition:
    role: str
    score: float
    clean_cycles: int
    strong_cycles: int
    trusted_strong_cycles: int
    rehabilitated: bool
    remove: bool


def transition_cycle_state(
    *,
    role: str,
    failed_probes: int,
    checks: int,
    score: float,
    clean_cycles: int,
    strong_cycles: int,
    trusted_strong_cycles: int,
    initial_cycle: bool,
    trusted_cycle: bool,
    config: ExperimentConfig,
    coherent_strong: bool | None = None,
) -> CycleTransition:
    """Apply one completed v10 probe cycle to a client's detector state."""
    if role not in {"R", "C", "S"}:
        raise ValueError(f"Unsupported cycle role: {role}")
    if checks <= 0 or not 0 <= failed_probes <= checks:
        raise ValueError("failed_probes must be between zero and checks")

    strong = (
        checks >= 2 and failed_probes >= 2
        if coherent_strong is None
        else coherent_strong
    )
    rehabilitated = False

    if failed_probes == 0:
        next_score = min(0.0, score + config.cycle_clear_reward) if score < 0 else 0.0
        next_clean = clean_cycles + 1
        next_role = role
        if role == "C" and next_clean >= config.cycle_candidate_clean_cycles:
            next_role = "R"
            next_clean = 0
            rehabilitated = True
        elif role == "S" and next_clean >= config.cycle_suspect_clean_cycles:
            next_role = "C"
            next_clean = 0
        elif role == "R":
            next_clean = 0
    else:
        next_clean = 0
        if initial_cycle:
            next_role = "S" if strong else "C"
        elif role == "R":
            # A previously trusted client always enters C first. It must be
            # independently confirmed in a later double cycle before S/removal.
            next_role = "C"
        elif strong:
            next_role = "S"
        else:
            next_role = role
        cost = (
            config.cycle_suspicious_cost
            if strong
            else 0.0
            if config.methodology_version in {"swtcp_v11", "swtcp_v12"}
            else config.cycle_candidate_cost
        )
        next_score = min(0.0, score - cost)
        if strong:
            strong_cycles += 1
            if trusted_cycle and not initial_cycle:
                trusted_strong_cycles += 1

    remove = (
        next_score <= config.cycle_removal_score
        and strong_cycles >= config.cycle_strong_cycles_for_removal
        and trusted_strong_cycles >= 1
    )
    return CycleTransition(
        role=next_role,
        score=next_score,
        clean_cycles=next_clean,
        strong_cycles=strong_cycles,
        trusted_strong_cycles=trusted_strong_cycles,
        rehabilitated=rehabilitated,
        remove=remove,
    )
