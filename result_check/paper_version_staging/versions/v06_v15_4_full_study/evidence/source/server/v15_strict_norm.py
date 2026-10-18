"""V15.3: overlapping low-norm cohorts cannot authorize permanent removal.

The rule is a conservative geometric heuristic, not an error guarantee.
It applies identically in every cycle and uses no attack labels or prevalence.
"""
from server import v15_evidence as baseline
from server.v15_protocol import audit_anomalies as diagnostic_audit

measurements = baseline.measurements
build_schedule = baseline.build_schedule
REVISION = "v15_3_strict_norm_v1"
PUBLIC_FIELDS = ("client_id", "trap_id", "norm_z", "profile_z", "delta_norm",
                 "profile_distance", "exact_zero_delta", "exact_sendback")


def policy():
    result = baseline.policy()
    result.update(
        revision=REVISION,
        certificate="strict full-peer separation for norm; unchanged v15.1 profile gate; diagonal diagnostic only",
        features=[list(feature) for feature in baseline.FEATURES if feature[0] != "diagonal_high"],
        norm_certificate="existing core gap > cohort IQR AND full-peer gap > cohort IQR; no density alternative",
        profile_certificate="unchanged v15.1 profile-distance certificate",
        diagonal="diagnostic only; not independent evidence of low norm",
        removal_channels=["norm_low", "profile_high", "exact_sendback"],
        followup="bounded v15.1 review; no median-only individual confirmation",
        risk="may delay or miss attackers; no false-positive or recall guarantee",
    )
    return result


def strict_norm_certificate(rows, candidates):
    result = baseline.certificate(rows, "delta_norm", "low", "identity", candidates)
    if result["supported"] and not result["full_peer_gap"] > result["spread"]:
        result.update(supported=False, members=[], reason="overlap_or_insufficient_full_peer_gap")
    return result


def screen(rows, round_index):
    public = [{key: row.get(key) for key in PUBLIC_FIELDS} for row in rows]
    decisions, metadata = baseline.screen(public, round_index)
    candidates = {d["client_id"] for d in decisions if d["screen_state"] == "S"}
    norm_pair = [strict_norm_certificate([r for r in public if r["trap_id"] == t], candidates)
                 for t in (0, 1)]
    norm_members = (set(norm_pair[0]["members"]) & set(norm_pair[1]["members"])
                    if all(c["supported"] for c in norm_pair) else set())
    for decision in decisions:
        diagnostic = decision["strong_channels"]
        channels = set(filter(None, diagnostic.split(",")))
        channels.discard("diagonal_high")
        if decision["client_id"] not in norm_members:
            channels.discard("norm_low")
        ordered = [c for c in ("norm_low", "profile_high", "exact_sendback") if c in channels]
        old_state = decision["screen_state"]
        decision.update(
            diagnostic_certified_channels=diagnostic,
            strong_channels=",".join(ordered),
            state="S" if ordered else "C" if old_state != "R" else "R",
            evidence_strength="strong" if ordered else "weak" if old_state != "R" else "none",
            reason="certified_" + "_and_".join(ordered) if ordered else
                   "weak_screening_no_removal" if old_state != "R" else "unflagged_no_strong_evidence",
        )
    metadata["certificates"]["norm_low"] = norm_pair
    for certificate in metadata["certificates"]["diagonal_high"]:
        certificate["enforcing"] = False
    metadata.update(revision=REVISION,
                    strong_clients=sum(bool(d["strong_channels"]) for d in decisions),
                    no_strong_evidence=not any(d["strong_channels"] for d in decisions))
    return decisions, metadata


def audit_anomalies(rows):
    public = [{key: row.get(key) for key in PUBLIC_FIELDS} for row in rows]
    candidates, _ = diagnostic_audit(public)
    clients = {r["client_id"] for r in public if r["exact_sendback"]}
    certificates = (strict_norm_certificate(public, candidates),
                    baseline.certificate(public, "profile_distance", "high", "identity", candidates))
    for certificate in certificates:
        clients.update(certificate["members"])
    return clients, "single_trap_strict_norm_or_profile_followup_only"


class CycleState(baseline.CycleState):
    def apply(self, decisions, cycle, round_index):
        # A derived score must never be smuggled into the removal state machine.
        for decision in decisions:
            if "diagonal_high" in decision.get("strong_channels", "").split(","):
                raise ValueError("v15.3 diagonal score is diagnostic only")
        return super().apply(decisions, cycle, round_index)
