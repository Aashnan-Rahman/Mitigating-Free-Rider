"""Generic norm/profile screening with bounded, reversible cycle evidence.

The detector receives only server-observable response summaries. No model-history
reconstruction, attack parameters, private sample counts, or telemetry is used.
Empirical cutoffs are operational calibration, not distribution-free guarantees.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from statistics import NormalDist, median
from typing import Mapping

import torch

from server.cycle_protocol import CycleTransition
from server.detection import DetectionResult, combine_coverage_checks


@dataclass(frozen=True)
class V13Settings:
    false_alarm_rate: float
    min_reference_clients: int
    calibration_cycles: int
    scale_prior_strength: float
    epsilon: float
    zero_epsilon: float
    personal_window: int
    personal_min_cycles: int
    quarantine_max_cycles: int
    evidence_window: int
    cooldown_cycles: int
    strong_cycles_for_removal: int
    reference_probation_cycles: int
    strong_cost: float
    removal_score: float


def settings_from_config(config) -> V13Settings:
    # Explicit allowlist: the detector never retains the simulation config.
    return V13Settings(
        config.cycle_target_false_alarm_rate, config.cycle_min_reference_clients,
        config.cycle_calibration_window_cycles, config.cycle_scale_prior_strength,
        config.cycle_scale_epsilon, config.zero_update_epsilon,
        config.v13_personal_window_cycles, config.v13_personal_min_cycles,
        config.v13_quarantine_max_cycles, config.v13_evidence_window_cycles,
        config.v13_reentry_cooldown_cycles, config.cycle_strong_cycles_for_removal,
        config.cycle_reference_probation_cycles,
        config.cycle_suspicious_cost, config.cycle_removal_score,
    )


def upper_quantile(values: list[float], alpha: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil((1 - alpha) * len(ordered)) - 1))]


class V13Detector:
    def __init__(self, settings: V13Settings) -> None:
        self.settings = settings
        self.cycle = 0
        self.calibration: list[dict[int, float]] = []
        self.scales: list[tuple[float, float]] = []
        # Residual summaries, not full updates, retained separately by client.
        self.personal: dict[int, list[tuple[float, float]]] = {}
        self.evidence: dict[int, list[tuple[int, str]]] = {}
        self.ages: dict[int, int] = {}
        self.cooldowns: dict[int, int] = {}
        self.last_reasons: dict[int, str] = {}
        self.last_cutoffs: dict[int, float] = {}

    def state_dict(self) -> dict:
        return {"settings": asdict(self.settings), **{
            name: getattr(self, name) for name in (
                "cycle", "calibration", "scales", "personal", "evidence",
                "ages", "cooldowns", "last_reasons", "last_cutoffs",
            )
        }}

    def load_state_dict(self, state: dict) -> None:
        if state.get("settings") != asdict(self.settings):
            raise ValueError("v13 checkpoint detector settings do not match")
        for name in ("cycle", "calibration", "scales", "personal", "evidence",
                     "ages", "cooldowns", "last_reasons", "last_cutoffs"):
            setattr(self, name, state[name])

    def cutoff(self, client: int, checks: int) -> float:
        s = self.settings
        # Normal reference is only a bootstrap; observed previous cycle maxima
        # may raise it. Client's own scores never set its current cutoff.
        base = NormalDist().inv_cdf(1 - s.false_alarm_rate / (3 * checks))
        prior = [upper_quantile([value for item, value in batch.items() if item != client],
                                s.false_alarm_rate)
                 for batch in self.calibration
                 if any(item != client for item in batch)]
        return max(base, median(prior)) if prior else base

    def scale(self, values: list[float], component: int) -> tuple[float, float, float]:
        s = self.settings
        center = median(values)
        mad = median(abs(value - center) for value in values)
        factor = 1 / NormalDist().inv_cdf(0.75)
        current = max(factor * mad, s.epsilon)
        if self.scales:
            prior = median(batch[component] for batch in self.scales)
            weight = len(values) / (len(values) + s.scale_prior_strength)
            current = math.sqrt(weight * current ** 2 + (1 - weight) * prior ** 2)
        return center, mad, max(current, s.epsilon)

    def consistent_with_self(self, client: int, residuals: list[tuple[float, float]],
                             cutoff: float) -> bool:
        prior = self.personal.get(client, [])
        if len(prior) < self.settings.personal_min_cycles:
            return False
        # Only earlier non-joint cycles qualify this baseline. A persistently
        # joint-anomalous attacker cannot certify itself by repetition.
        for component in (0, 1):
            values = [item[component] for item in prior]
            center = median(values)
            mad = median(abs(value - center) for value in values)
            # Residuals are already in population robust-sigma units; shrink
            # small personal samples toward unit variance, not an absolute floor.
            weight = len(values) / (len(values) + self.settings.scale_prior_strength)
            variance = weight * (mad / NormalDist().inv_cdf(0.75)) ** 2 + (1 - weight)
            if any(abs(item[component] - center) / math.sqrt(variance) > cutoff
                   for item in residuals):
                return False
        return True

    def evaluate_cycle(
        self, *, coverage_norms: Mapping[int, list[float]],
        coverage_profiles: Mapping[int, list[torch.Tensor]],
        coverage_trap_ids: Mapping[int, list[int]],
        coverage_observation_rounds: Mapping[int, list[int]],
        active_clients: set[int], checks: int,
    ) -> dict:
        s = self.settings
        by_trap = {
            trap: {client: index for client in sorted(active_clients)
                   for index, item in enumerate(coverage_trap_ids.get(client, []))
                   if item == trap}
            for trap in range(checks)
        }
        # Reject partial or undersized batches rather than letting three peers
        # become a permanent-removal reference. No current outlier is trimmed.
        valid = all(
            set(batch) == active_clients
            and sum(coverage_norms[client][index] >= s.zero_epsilon
                    for client, index in batch.items()) - 1 >= s.min_reference_clients
            for batch in by_trap.values()
        )
        results: dict[int, list[DetectionResult]] = {}
        residuals: dict[int, list[tuple[float, float]]] = {}
        signatures: dict[int, list[str]] = {}
        scores: dict[int, float] = {}
        current_scales: list[tuple[float, float]] = []
        self.last_cutoffs = {client: self.cutoff(client, checks) for client in active_clients}
        for trap, batch in by_trap.items():
            for client, index in batch.items():
                norm = coverage_norms[client][index]
                if norm < s.zero_epsilon:
                    result = DetectionResult(True, 0, None, norm, None, None, None,
                                             None, None, None, "zero_update")
                    results.setdefault(client, []).append(result)
                    continue
                if not valid:
                    continue
                peers = [peer for peer in batch if peer != client
                         and coverage_norms[peer][batch[peer]] >= s.zero_epsilon]
                log_norms = [math.log(coverage_norms[peer][batch[peer]]) for peer in peers]
                center, mad, sigma = self.scale(log_norms, 0)
                norm_z = (math.log(norm) - center) / sigma
                peer_profiles = torch.stack([
                    coverage_profiles[peer][batch[peer]].detach().float().cpu()
                    for peer in peers])
                profile_center = peer_profiles.median(dim=0).values
                distances = [float((profile - profile_center).norm()) for profile in peer_profiles]
                pcenter, pmad, psigma = self.scale(distances, 1)
                distance = float((coverage_profiles[client][index].detach().float().cpu()
                                  - profile_center).norm())
                profile_z = (distance - pcenter) / psigma
                current_scales.append((sigma, psigma))
                cutoff = self.last_cutoffs[client]
                nf, pf = abs(norm_z) > cutoff, profile_z > cutoff
                joint = nf and pf
                signature = ("norm_high" if norm_z > 0 else "norm_low") if joint else ""
                signatures.setdefault(client, []).append(signature)
                residuals.setdefault(client, []).append((norm_z, profile_z))
                scores[client] = max(scores.get(client, 0), abs(norm_z), profile_z)
                reason = "joint_population_screen" if joint else "weak_population_screen" if nf or pf else None
                result = DetectionResult(nf or pf, 0, None, norm, norm_z,
                                         math.exp(center), mad, None, None, None, reason,
                                         magnitude_flag=nf, profile_flag=pf,
                                         joint_flag_count=int(joint), profile_score=distance,
                                         profile_z_score=profile_z, profile_median=pcenter,
                                         profile_mad=pmad)
                results.setdefault(client, []).append(result)
        combined = {client: combine_coverage_checks(items) for client, items in results.items()}
        strong: dict[int, bool] = {}
        flags: dict[int, int] = {}
        eligible_calibration: dict[int, float] = {}
        self.last_reasons = {}
        for client, items in results.items():
            pair = signatures.get(client, [])
            coherent = checks >= 2 and len(pair) == checks and bool(pair[0]) and len(set(pair)) == 1
            personal_ok = valid and self.consistent_with_self(
                client, residuals.get(client, []), self.last_cutoffs[client])
            if personal_ok:
                items = [replace(item, flagged=False, joint_flag_count=0,
                                 reason="within_personal_baseline")
                         if item.reason != "zero_update" else item for item in items]
                results[client] = items
                combined[client] = combine_coverage_checks(items)
            strong[client] = coherent and not personal_ok
            flags[client] = sum(item.flagged and item.reason != "zero_update" for item in items)
            self.last_reasons[client] = pair[0] if strong[client] else ""
            if valid and residuals.get(client) and not any(pair) and not any(item.reason == "zero_update" for item in items):
                history = self.personal.setdefault(client, [])
                history.append(tuple(median(item[k] for item in residuals[client]) for k in (0, 1)))
                del history[:-s.personal_window]
            if valid and flags[client] == 0 and scores.get(client) is not None:
                eligible_calibration[client] = scores[client]
        if valid:
            # Commit only after all clients have been judged against prior state.
            self.calibration.append(eligible_calibration)
            del self.calibration[:-s.calibration_cycles]
            if current_scales:
                self.scales.append(tuple(median(item[k] for item in current_scales) for k in (0, 1)))
                del self.scales[:-s.calibration_cycles]
        self.cycle += 1
        return {
            "results": combined, "checks": {client: len(items) for client, items in results.items()},
            "flags": flags, "joint_flags": {client: sum(item.joint_flag_count for item in items)
                                            for client, items in results.items()},
            "zero_counts": {client: sum(item.reason == "zero_update" for item in items)
                            for client, items in results.items()},
            "decision_rounds": {client: max(coverage_observation_rounds[client]) for client in results},
            "reference_outliers": set(), "reference_valid": valid,
            "coherent_strong": strong, "cycle_scores": scores,
            "frozen_reference_ids": set(active_clients), "norm_scales": [], "profile_scales": [],
            "cutoff": max(self.last_cutoffs.values(), default=0),
        }

    def transition(self, *, client: int, role: str, failed_probes: int,
                   coherent_strong: bool, clean_cycles: int) -> CycleTransition:
        s = self.settings
        recent = [item for item in self.evidence.get(client, [])
                  if item[0] > self.cycle - s.evidence_window]
        if coherent_strong:
            signature = self.last_reasons.get(client, "")
            # A clean/weak intervening cycle invalidates consecutive confirmation.
            if not recent or recent[-1] != (self.cycle - 1, signature):
                recent = []
            recent.append((self.cycle, signature))
        else:
            recent = []
        self.evidence[client] = recent
        count = len(recent)
        remove = (coherent_strong and count >= s.strong_cycles_for_removal
                  and -s.strong_cost * count <= s.removal_score)
        next_clean = clean_cycles + 1 if failed_probes == 0 else 0
        cooldown = self.cooldowns.get(client, 0)
        next_role = "C" if failed_probes else role
        if count:
            next_role = "S" if count > 1 else "C"
        age = self.ages.get(client, 0) + 1 if role != "R" or next_role != "R" else 0
        rehabilitated = False
        if not remove and (
            next_clean >= s.reference_probation_cycles
            or age >= s.quarantine_max_cycles
            or (role == "R" and cooldown > 0 and not coherent_strong)
        ):
            rehabilitated = role != "R"
            next_role, next_clean, age = "R", 0, 0
            if rehabilitated:
                self.cooldowns[client] = s.cooldown_cycles
            elif cooldown:
                self.cooldowns[client] = cooldown - 1
            # Unconfirmed evidence cannot survive a release deadline.
            recent = []
            self.evidence[client] = []
            count = 0
        self.ages[client] = age
        return CycleTransition(next_role, -s.strong_cost * count, next_clean, count,
                               max(0, count - 1), rehabilitated, remove)
