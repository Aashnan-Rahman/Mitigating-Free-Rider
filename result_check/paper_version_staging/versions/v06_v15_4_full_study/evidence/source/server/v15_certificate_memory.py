"""V15.4: remember fresh strict certificates across ambiguous full cycles.

No certificate is weakened or inferred from stored evidence. Repeated events
need the same component; two consecutive clean cycles clear statistical memory.
Quarantine and audits keep v15.3 behavior. This is not an error guarantee.
"""
import json

from server import v15_strict_norm as strict

measurements = strict.measurements
build_schedule = strict.build_schedule
audit_anomalies = strict.audit_anomalies
REVISION = "v15_4_fresh_certificate_memory_v1"
STATISTICAL_COMPONENTS = ("norm_low", "profile_high")


def policy():
    result = strict.policy()
    result.update(
        revision=REVISION,
        certificate_revision=strict.REVISION,
        removal="same statistical component freshly certified on both traps in configured number of distinct full cycles; adjacency not required",
        memory_clearance="configured clean-cycle count of consecutive full R cycles; C pauses but does not erase certificates",
        exact_sendback="unchanged consecutive complete-cycle confirmation",
        audit="single trap cannot confirm or clear statistical certificate memory",
        quarantine="unchanged bounded review; stored certificates cannot renew exclusion or force probing",
        memory_lifetime="until clean-cycle clearance or removal; no round-based expiry",
        risk="persistent correlated false certificates may accumulate; no recall or false-positive guarantee",
    )
    return result


def screen(rows, round_index):
    decisions, metadata = strict.screen(rows, round_index)
    metadata.update(revision=REVISION, certificate_revision=strict.REVISION)
    return decisions, metadata


class CycleState(strict.CycleState):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for record in self.records.values():
            record.update(fresh_certificate_counts={}, certificate_clean_cycles=0)

    def apply(self, decisions, cycle, round_index):
        ids = [decision["client_id"] for decision in decisions]
        if len(set(ids)) != len(ids) or set(ids) != set(self.active):
            raise ValueError("Transition requires a complete active-client cycle")
        pending = {}
        cleared = []
        allowed = set(STATISTICAL_COMPONENTS) | {"exact_sendback"}
        for decision in decisions:
            client = decision["client_id"]
            record = self.records[client]
            if cycle <= record["last_cycle"]:
                raise ValueError("Certificate confirmation requires a distinct, newer full cycle")
            if decision["state"] not in {"S", "C", "R"}:
                raise ValueError("Unknown screening category")
            channels = set(filter(None, decision.get("strong_channels", "").split(",")))
            if not channels <= allowed:
                raise ValueError("Unknown or diagnostic-only removal-evidence component")
            counts = dict(record["fresh_certificate_counts"])
            clean = 0
            if decision["state"] == "R":
                adjacent = record["last_cycle"] == cycle - 1 and record["last_screen"] == "R"
                clean = record["certificate_clean_cycles"] + 1 if adjacent else 1
                if clean >= self.clean_cycles and counts:
                    cleared.append(client)
                    counts.clear()
            elif decision["state"] == "S":
                for component in STATISTICAL_COMPONENTS:
                    if component in channels:
                        counts[component] = counts.get(component, 0) + 1
            pending[client] = (counts, clean)

        # Keep scheduling, bounded quarantine, exact-sendback streaks and rehab
        # unchanged. Statistical memory by itself never starts/renews exclusion.
        events = super().apply(decisions, cycle, round_index)
        existing_removals = {e["client_id"]: e for e in events if e["event"] == "remove"}
        for decision in decisions:
            client = decision["client_id"]
            record = self.records[client]
            counts, clean = pending[client]
            record.update(fresh_certificate_counts=counts, certificate_clean_cycles=clean)
            fresh_channels = set(filter(None, decision.get("strong_channels", "").split(",")))
            confirmed = sorted(component for component, count in counts.items()
                               if component in fresh_channels and count >= self.strong_cycles)
            if decision["state"] == "S" and confirmed:
                reason = "repeated_fresh_component_certificates"
                if client in existing_removals:
                    existing_removals[client]["reason"] = reason
                else:
                    record.update(category="X", removed_round=round_index, review=0, quarantined=False)
                    events.append(dict(client_id=client, event="remove", reason=reason))
                record["strong"] = max(counts[c] for c in confirmed)
            decision.update(
                fresh_certificate_counts=json.dumps(counts, sort_keys=True),
                certificate_clean_cycles=clean,
                confirmed_statistical_components=",".join(confirmed),
                strong_cycles=record["strong"],
                category_after=record["category"],
                reference_eligible=int(record["category"] == "R" and record["probation"] == 0),
                removed=int(record["category"] == "X"),
                quarantined=int(record["quarantined"]),
                review_cycles_remaining=record["review"],
            )
        events.extend(dict(client_id=client, event="clear_certificate_memory",
                           reason="consecutive_complete_clean_cycles") for client in cleared)
        return events
