"""V15.2: component-specific follow-up backed by an earlier cohort certificate.

Only the state machine can enrol a client from a fresh cohort certificate.
Follow-up uses fresh A/B observations, never attack metadata or a removal quota.
"""
import math

import numpy as np

from server.v15_evidence import (
    CycleState as EvidenceState, FEATURES, measurements, build_schedule,
    audit_anomalies, screen as evidence_screen, policy as evidence_policy,
)

REVISION = "v15_2_individual_followup_v1"
FOLLOWUP_COMPONENTS = tuple(feature[0] for feature in FEATURES)


def policy():
    return {**evidence_policy(), "revision": REVISION,
        "followup": "earlier cohort-certified component plus fresh matching A/B direction relative to current peers",
        "followup_norm": "signed leave-one-out norm-z below its median centre (zero) on both traps",
        "followup_profile": "signed leave-one-out profile-z above its median centre (zero) on both traps",
        "followup_diagonal": "diagonal score above leave-one-out same-trap score median on both traps",
        "followup_admission": "only fresh cohort certificates; neither weak C nor followup alone can enrol",
        "followup_clearance": "two complete consecutive clean cycles; mixed/undefined keeps watch but resets confirmation",
        "followup_cohort_size": "not required once individually enrolled from a prior certificate",
        "followup_quarantine": "unchanged bounded exclusion; watch can continue after exclusion ends",
        "followup_risk": "more permissive individual confirmation; no error guarantee"}


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def leave_one_out_medians(values):
    """O(N) central order-statistic selection, without sorting client scores."""
    clients = list(values)
    n = len(clients)
    x = np.array([_finite(values[c]) if _finite(values[c]) is not None else np.nan for c in clients])
    if n < 2 or not np.isfinite(x).all():
        return {c: None for c in clients}
    middle = n // 2
    if n % 2 == 0:
        ordered = np.partition(x, (middle - 1, middle))
        lower, upper = ordered[middle - 1], ordered[middle]
        medians = np.where(x <= lower, upper, lower)
    else:
        ordered = np.partition(x, (middle - 1, middle, middle + 1))
        lower, center, upper = ordered[middle - 1:middle + 2]
        medians = np.where(x < center, (center + upper) / 2,
                          np.where(x > center, (lower + center) / 2, (lower + upper) / 2))
    return {c: float(m) for c, m in zip(clients, medians)}


def screen(rows, round_index, followup_context=None):
    public = [{key: r.get(key) for key in ("client_id", "trap_id", "norm_z", "profile_z", "delta_norm",
        "profile_distance", "exact_zero_delta", "exact_sendback")} for r in rows]
    decisions, metadata = evidence_screen(public, round_index)
    context = followup_context or {}
    pairs = {}
    diagonals = {0: {}, 1: {}}
    for r in public:
        c, t = r["client_id"], r["trap_id"]
        pairs.setdefault(c, {})[t] = r
        nz, pz = _finite(r["norm_z"]), _finite(r["profile_z"])
        diagonals[t][c] = pz - nz if nz is not None and pz is not None else None
    references = {t: leave_one_out_medians(values) for t, values in diagonals.items()}
    checks = {}
    for d in decisions:
        c = d["client_id"]
        fresh = set(filter(None, d["strong_channels"].split(",")))
        watched = set(context.get(c, ()))
        if not watched <= set(FOLLOWUP_COMPONENTS):
            raise ValueError("Unknown followup component")
        matched, clean = set(), set()
        checks[c] = {}
        probes = pairs[c]
        for component in FOLLOWUP_COMPONENTS:
            if component not in watched:
                continue
            readings = []
            for trap in (0, 1):
                row = probes.get(trap, {})
                if component == "norm_low":
                    readings.append((_finite(row.get("norm_z")), 0., "low"))
                elif component == "profile_high":
                    readings.append((_finite(row.get("profile_z")), 0., "high"))
                else:
                    readings.append((diagonals[trap].get(c), references[trap].get(c), "high"))
            valid = all(value is not None and ref is not None for value, ref, _ in readings)
            failed = [value < ref if direction == "low" else value > ref for value, ref, direction in readings] if valid else []
            status = "matching_both_traps" if valid and all(failed) else "clean_both_traps" if valid and not any(failed) else "mixed_or_undefined"
            if status == "matching_both_traps":
                matched.add(component)
            elif status == "clean_both_traps":
                clean.add(component)
            checks[c][component] = dict(status=status,
                A_value=readings[0][0], A_reference=readings[0][1],
                B_value=readings[1][0], B_reference=readings[1][1])
        all_channels = fresh | matched
        if all_channels:
            d.update(state="S", strong_channels=",".join(sorted(all_channels)),
                evidence_strength="individual_followup" if matched - fresh else "strong",
                reason="followup_confirmed_" + "_and_".join(sorted(matched)) if matched - fresh else d["reason"])
        elif watched:
            d.update(state="R" if clean == watched else "C", strong_channels="",
                evidence_strength="none" if clean == watched else "weak",
                reason="followup_clean_both_traps" if clean == watched else "followup_unresolved_no_confirmation")
        d.update(cohort_certified_channels=",".join(sorted(fresh)),
                 followup_matched_channels=",".join(sorted(matched)),
                 followup_clean_channels=",".join(sorted(clean)))
    metadata.update(revision=REVISION, cohort_revision=metadata.get("revision"), followup_checks=checks,
        strong_clients=sum(d["state"] == "S" for d in decisions),
        no_strong_evidence=not any(d["state"] == "S" for d in decisions))
    return decisions, metadata


class CycleState(EvidenceState):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for r in self.records.values():
            r.update(followup_pending={}, followup_origins={})

    @property
    def monitored(self):
        return super().monitored | {c for c, r in self.records.items() if r["category"] != "X" and r["followup_pending"]}

    def confirmation_context(self):
        return {c: tuple(component for component in FOLLOWUP_COMPONENTS if component in r["followup_pending"])
                for c, r in self.records.items() if r["category"] != "X" and r["followup_pending"]}

    def apply(self, decisions, cycle, round_index):
        previous = {c: (r["last_cycle"], dict(r["followup_pending"])) for c, r in self.records.items()}
        events = super().apply(decisions, cycle, round_index)
        by_client = {d["client_id"]: d for d in decisions}
        for event in events:
            if event["event"] == "remove":
                c = event["client_id"]
                fresh = set(filter(None, by_client[c].get("cohort_certified_channels", "").split(",")))
                confirmed = {component for component, count in self.records[c]["component_streaks"].items()
                             if count >= self.strong_cycles}
                if confirmed - fresh:
                    event["reason"] = "prior_certificate_plus_consecutive_paired_followup"
        for d in decisions:
            c = d["client_id"]
            r = self.records[c]
            pending = dict(r["followup_pending"])
            if r["category"] == "X":
                pending.clear()
                r["followup_origins"].clear()
            else:
                fresh = set(filter(None, d.get("cohort_certified_channels", "").split(","))) & set(FOLLOWUP_COMPONENTS)
                fresh &= set(filter(None, d.get("strong_channels", "").split(","))) if d["state"] == "S" else set()
                clean = set(filter(None, d.get("followup_clean_channels", "").split(",")))
                for component in list(pending):
                    if component in fresh:
                        continue
                    count = previous[c][1].get(component, 0) + 1 if previous[c][0] == cycle - 1 else 1
                    pending[component] = count if component in clean else 0
                    if pending[component] >= self.clean_cycles:
                        del pending[component]
                        r["followup_origins"].pop(component, None)
                for component in fresh:
                    pending[component] = 0
                    r["followup_origins"][component] = cycle
            r["followup_pending"] = pending
            d.update(followup_pending_channels=",".join(sorted(pending)),
                     followup_origin_cycles=",".join(f"{component}:{r['followup_origins'][component]}" for component in sorted(pending)))
        return events
