"""Uncalibrated, label-blind separation certificates and bounded weak review.

This is a geometric heuristic, not a distribution-free false-positive bound.
No offline honest/attacker calibration, known prevalence, or round-30 switch.
"""
import math

import numpy as np

from server.v15_protocol import (
    measurements, build_schedule, screen as legacy_screen,
    audit_anomalies as legacy_audit,
    CycleState as LegacyState,
)

REVISION = "v15_1_evidence_gate_v1"
FEATURES = (("norm_low", "delta_norm", "low", "identity"),
            ("profile_high", "profile_distance", "high", "identity"),
            ("diagonal_high", "diagonal", "high", "identity"))


def policy():
    return {"revision": REVISION,
        "certificate": "screened minority; core gap > minority IQR; additionally core vs full-peer gap > minority IQR OR higher cohort density",
        "cohort_minimum": "ceil(N/ceil(sqrt(N)))",
        "features": [list(f) for f in FEATURES], "spread": "empirical interquartile range",
        "removal": "same certified component on A/B in consecutive complete cycles, or repeated exact sendback",
        "weak_evidence": "screening only; no removal strike or automatic quarantine",
        "review": "bounded followup; weak evidence cannot renew its own exclusion",
        "audit": "single-trap certificate only starts followup, never confirmation",
        "references": "all active clients, no label or passing-only filter",
        "calibration": "none", "round_dependent_thresholds": False,
        "pair_selection": "unchanged preselected A/B positions", "cosine": "not collected"}


def certificate(rows, field, direction, transform, candidates):
    """Test a screened cohort, using robust cores rather than forced partitions."""
    result = dict(field=field, direction=direction, transform=transform, supported=False,
                  members=[], reason="invalid_or_insufficient", gap=None, spread=None)
    values = []
    for r in rows:
        try:
            value = float(r.get(field))
            if not math.isfinite(value) or (transform == "log" and value <= 0):
                return result
            values.append(math.log(value) if transform == "log" else value)
        except (TypeError, ValueError):
            return result
    n = len(values)
    if n < 2 or len({r["client_id"] for r in rows}) != n:
        return result
    x = np.asarray(values)
    if np.ptp(x) == 0:
        result["reason"] = "constant_population"
        return result
    bins = math.ceil(math.sqrt(n))
    mask = np.asarray([r["client_id"] in candidates for r in rows])
    cohort, peers = x[mask], x[~mask]
    minimum = math.ceil(n / bins)
    result.update(clients=n, minimum_cohort=minimum,
                  cohort_size=int(mask.sum()), reason="not_supported_minority")
    if len(cohort) < minimum or len(cohort) >= len(peers):
        return result
    quartiles = np.quantile(cohort, [.25, .75])
    peer_quartiles = np.quantile(peers, [.25, .75])
    gap = float(peer_quartiles[0] - quartiles[1] if direction == "low" else quartiles[0] - peer_quartiles[1])
    spread = float(quartiles[1] - quartiles[0])
    peer_spread = float(peer_quartiles[1] - peer_quartiles[0])
    full_peer_gap = float(peers.min() - quartiles[1] if direction == "low" else quartiles[0] - peers.max())
    # Normalizing by sample intervals prevents a smaller slice of a continuous
    # population from looking more cohesive merely because it has fewer points.
    cohort_spacing = spread / (len(cohort) - 1) if len(cohort) > 1 else float("inf")
    peer_spacing = peer_spread / (len(peers) - 1) if len(peers) > 1 else 0.
    result.update(gap=gap, spread=spread, peer_spread=peer_spread,
                  full_peer_gap=full_peer_gap, cohort_spacing=cohort_spacing, peer_spacing=peer_spacing,
                  reason="insufficient_core_separation_or_cohesion")
    if gap > spread and gap > 0 and (full_peer_gap > spread or cohort_spacing < peer_spacing):
        peer_center = float(np.median(peers))
        individual = x < peer_center if direction == "low" else x > peer_center
        result.update(supported=True, reason="separated_cohesive_minority",
                      peer_center=peer_center,
                      members=[r["client_id"] for r, member in zip(rows, mask & individual) if member])
    return result


def screen(rows, round_index):
    # Reuse former screening for diagnostics only, never a removal shortcut.
    public = [{k: r.get(k) for k in ("client_id", "trap_id", "norm_z", "profile_z", "delta_norm",
              "profile_distance", "exact_zero_delta", "exact_sendback")} for r in rows]
    for r in public:
        r["diagonal"] = r["profile_z"] - r["norm_z"] if r["profile_z"] is not None and r["norm_z"] is not None else None
    decisions, old_metadata = legacy_screen(public, round_index)
    candidates = {d["client_id"] for d in decisions if d["state"] == "S"}
    evidence = {d["client_id"]: [] for d in decisions}
    certificates = {}
    for channel, field, direction, transform in FEATURES:
        pair = [certificate([r for r in public if r["trap_id"] == t], field, direction, transform, candidates) for t in (0, 1)]
        certificates[channel] = pair
        if all(c["supported"] for c in pair):
            for client in set(pair[0]["members"]) & set(pair[1]["members"]):
                evidence[client].append(channel)
    for d in decisions:
        old_state = d["state"]
        if d["reason"] in ("exact_zero_both_traps", "exact_sendback_both_traps"):
            evidence[d["client_id"]].append("exact_sendback")
        channels = evidence[d["client_id"]]
        d.update(screen_state=old_state, strong_channels=",".join(channels),
                 evidence_strength="strong" if channels else "weak" if old_state != "R" else "none",
                 state="S" if channels else "C" if old_state != "R" else "R",
                 reason="certified_" + "_and_".join(channels) if channels else
                        "weak_screening_no_removal" if old_state != "R" else "unflagged_no_strong_evidence")
    return decisions, dict(round=round_index, revision=REVISION, certificates=certificates,
        strong_clients=sum(bool(c) for c in evidence.values()),
        no_strong_evidence=not any(evidence.values()), diagnostic_screen=old_metadata)


def audit_anomalies(rows):
    public = [{k: r.get(k) for k in ("client_id", "delta_norm", "profile_distance", "norm_z", "profile_z", "exact_sendback")} for r in rows]
    for r in public:
        r["diagonal"] = r["profile_z"] - r["norm_z"] if r["profile_z"] is not None and r["norm_z"] is not None else None
    clients = {r["client_id"] for r in public if r["exact_sendback"]}
    candidates, _ = legacy_audit(public)
    for _, field, direction, transform in FEATURES:
        c = certificate(public, field, direction, transform, candidates)
        clients.update(c["members"])
    return clients, "single_trap_certificates_followup_only"


class CycleState(LegacyState):
    def __init__(self, clients, strong_cycles=2, clean_cycles=2, probation_cycles=1,
                 review_cycles=2, cooldown_cycles=2):
        super().__init__(clients, strong_cycles, clean_cycles, probation_cycles)
        self.review_cycles, self.cooldown_cycles = review_cycles, cooldown_cycles
        for r in self.records.values():
            r.update(component_streaks={}, review=0, quarantined=False, audit_cooldown=0)

    @property
    def monitored(self):
        return {c for c, r in self.records.items() if r["category"] != "X" and r["review"] > 0}

    @property
    def quarantined(self):
        return {c for c, r in self.records.items() if r["category"] != "X" and r["quarantined"]}

    def apply(self, decisions, cycle, round_index):
        ids = [d["client_id"] for d in decisions]
        if len(set(ids)) != len(ids) or set(ids) != set(self.active):
            raise ValueError("Transition requires a complete active-client cycle")
        events = []
        for d in decisions:
            c, label = d["client_id"], d["state"]
            r = self.records[c]
            previous = r["category"]
            previous_review = r["review"]
            channels = set(filter(None, d.get("strong_channels", "").split(",")))
            allowed_channels = {f[0] for f in FEATURES} | {"exact_sendback"}
            if not channels <= allowed_channels:
                raise ValueError("Unknown removal-evidence component")
            if label != "S":
                channels.clear()
            adjacent = r["last_cycle"] == cycle - 1
            streaks = {channel: r["component_streaks"].get(channel, 0) + 1 if adjacent else 1 for channel in channels}
            r.update(component_streaks=streaks, strong=max(streaks.values(), default=0))
            if label == "S" and channels:
                r.update(category="S", clean=0, probation=0, review=self.review_cycles,
                         quarantined=True, audit_cooldown=0)
                if r["strong"] >= self.strong_cycles:
                    r.update(category="X", removed_round=round_index, review=0, quarantined=False)
                    events.append(dict(client_id=c, event="remove", reason="consecutive_certified_component_cycles"))
            else:
                r["review"] = max(0, r["review"] - 1)
                if label == "R" and previous in ("S", "C"):
                    r["clean"] = r["clean"] + 1 if adjacent and r["last_screen"] == "R" else 1
                    if r["clean"] >= self.clean_cycles:
                        r.update(category="R", probation=self.probation_cycles, review=0, quarantined=False)
                        events.append(dict(client_id=c, event="rehabilitate", reason="two_complete_clean_cycles"))
                    else:
                        r["category"] = "C"
                elif label == "R":
                    r.update(category="R", probation=max(0, r["probation"] - 1))
                else:
                    r.update(category="C", clean=0, probation=0)
                if r["review"] == 0 and r["quarantined"]:
                    r.update(quarantined=False, audit_cooldown=self.cooldown_cycles)
                    events.append(dict(client_id=c, event="release_unconfirmed", reason="no_strong_evidence_within_review"))
                elif r["review"] == 0 and previous_review > 0 and r["category"] == "C":
                    r["audit_cooldown"] = self.cooldown_cycles
                    events.append(dict(client_id=c, event="end_unconfirmed_followup", reason="weak_followup_did_not_confirm"))
            r.update(last_cycle=cycle, last_screen=label)
            d.update(category_after=r["category"], strong_cycles=r["strong"], clean_cycles=r["clean"],
                reference_eligible=int(r["category"] == "R" and r["probation"] == 0),
                removed=int(r["category"] == "X"), quarantined=int(r["quarantined"]), review_cycles_remaining=r["review"])
        return events

    def escalate_audit(self, clients):
        cooling = {c for c, r in self.records.items() if r["audit_cooldown"] > 0}
        for r in self.records.values():
            r["audit_cooldown"] = max(0, r["audit_cooldown"] - 1)
        for c in clients:
            r = self.records[c]
            if r["category"] != "X" and c not in cooling:
                r.update(category="C", review=self.review_cycles, clean=0,
                         component_streaks={}, strong=0, quarantined=False)
