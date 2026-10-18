"""Attack-blind v15 screening, homogeneous scheduling and cycle transitions."""
import copy
import math

import numpy as np
import torch

from server.diagonal_decision import (
    classify, policy as diagonal_policy, _boundaries,
    BOOTSTRAP_REPLICATES, BOOTSTRAP_CONFIDENCE, BOOTSTRAP_SEED,
)
from server.preliminary_signals import robust

REVISION = "v15_cycle_confirmation_v1"


def policy():
    return {"revision": REVISION, "diagonal": diagonal_policy(),
            "fallback": "same-trap leave-one-out norm median; below on both => S; one/undefined => C",
            "pair_selection": "uniform response positions fixed before observing scores",
            "removal": "consecutive completed double-trap S cycles only",
            "references": "all active clients, one selected response/client/trap; no label filtering",
            "cosine": "not collected or used", "audit": "single trap can escalate only"}


def measurements(observations, active, round_index, traps=(0, 1)):
    """Exact former preliminary norm/profile statistics, without full deltas."""
    result = []
    for trap in traps:
        responses = {c: observations.get(c, {}).get(trap) for c in active}
        available = {c: r for c, r in responses.items() if r is not None}
        for client in active:
            item = responses[client]
            peers = [r for c, r in available.items() if c != client]
            z = pz = distance = center = mad = pc = pmad = None
            if item is not None and peers:
                center, mad, z = robust([r["norm"] for r in peers], item["norm"])
                profiles = torch.tensor([r["profile"] for r in peers], dtype=torch.float32)
                profile_center = profiles.median(dim=0).values
                distances = [float((p - profile_center).norm()) for p in profiles]
                distance = float((torch.tensor(item["profile"]) - profile_center).norm())
                pc, pmad, pz = robust(distances, distance)
            result.append(dict(round=round_index, client_id=client, trap_id=trap,
                observation_round=item["round"] if item else None, reference_clients=len(peers),
                delta_norm=item["norm"] if item else None, norm_z=z, norm_median=center, norm_mad=mad,
                profile_distance=distance, profile_z=pz, profile_median=pc, profile_mad=pmad,
                exact_zero_delta=int(item is not None and item["norm"] == 0),
                exact_sendback=int(item is not None and item["sendback"]), enforced=0))
    return result


def screen(rows, round_index):
    # Decision functions receive only protocol allowlisted fields, not labels.
    rows = [{k: r.get(k) for k in ("client_id", "trap_id", "norm_z", "profile_z",
                                  "exact_zero_delta", "exact_sendback")} for r in rows]
    decisions, metadata = classify(rows)
    fallback = metadata["status"] != "provisional_split"
    pairs = {}
    for row in rows:
        pairs.setdefault(row["client_id"], {})[row["trap_id"]] = row
    for d in decisions:
        d.update(round=round_index, provisional=0, enforced=1)
        probes = pairs[d["client_id"]]
        if set(probes) == {0, 1} and all(probes[t].get("exact_sendback") for t in (0, 1)):
            d.update(state="S", reason="exact_sendback_both_traps")
        elif fallback and d["reason"] != "exact_zero_both_traps":
            valid = set(probes) == {0, 1} and all(
                probes[t]["norm_z"] is not None and math.isfinite(probes[t]["norm_z"]) for t in (0, 1))
            low = sum(probes[t]["norm_z"] < 0 for t in (0, 1)) if valid else None
            d.update(state="S" if low == 2 else "R" if low == 0 else "C",
                     reason="median_fallback_both_low" if low == 2 else
                            "median_fallback_both_clear" if low == 0 else "median_fallback_uncertain")
    return decisions, {**metadata, "round": round_index, "fallback_used": fallback}


def audit_anomalies(rows):
    """Single-view screening for escalation, never confirmation or removal."""
    valid = [r for r in rows if r["norm_z"] is not None and r["profile_z"] is not None]
    if len(valid) != len(rows) or len(valid) < 2:
        return {r["client_id"] for r in rows}, "incomplete_audit"
    zero = {r["client_id"] for r in rows if r["exact_sendback"]}
    x = np.array([r["profile_z"] - r["norm_z"] for r in valid])
    if not np.isfinite(x).all() or np.ptp(x) == 0:
        return zero, "degenerate_audit"
    n = len(x)
    bins = math.ceil(math.sqrt(n))
    edges = np.linspace(x.min(), x.max(), bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    indices = np.clip(np.searchsorted(edges, x, side="right") - 1, 0, bins - 1)
    boundary = _boundaries(np.bincount(indices, minlength=bins)[None, :], centers, edges)[0]
    if np.count_nonzero(x <= boundary) <= n / 2:
        return zero | {r["client_id"] for r in valid if r["norm_z"] < 0}, "audit_median_escalation"
    samples = np.random.default_rng(BOOTSTRAP_SEED).integers(n, size=(BOOTSTRAP_REPLICATES, n))
    counts = np.zeros((BOOTSTRAP_REPLICATES, bins))
    np.add.at(counts, (np.arange(BOOTSTRAP_REPLICATES)[:, None], indices[samples]), 1)
    bounds = _boundaries(counts, centers, edges)
    if not np.isfinite(bounds).all():
        return zero, "unstable_audit"
    upper = np.quantile(bounds, 1 - (1 - BOOTSTRAP_CONFIDENCE) / 2, method="higher")
    return zero | {r["client_id"] for r, score in zip(valid, x) if score > upper}, "audit_diagonal_escalation"


def _groups(clients, count, rng):
    clients = list(clients)
    rng.shuffle(clients)
    return [clients[i::count] for i in range(count)] if count else []


def build_schedule(active, monitored, rng, group_limit=10, rounds=10, initial=False):
    """Ten rounds; homogeneous groups; each R twice, each monitored ten times."""
    active = list(active)
    if not active:
        return {"assignments": [(i % 2, []) for i in range(rounds)], "groups": [], "selected": {}}
    watched = [c for c in active if c in monitored]
    ordinary = [c for c in active if c not in monitored]
    total = min(group_limit, len(active))
    if watched and ordinary:
        # Nearest proportional allocation, ties down (42=>4, 45=>4, 46=>5).
        k = math.ceil(total * len(watched) / len(active) - .5)
        k = max(1, min(total - 1, len(watched), k))
        k = max(k, total - len(ordinary))
    else:
        k = total if watched else 0
    watched_groups = _groups(watched, k, rng)
    ordinary_groups = _groups(ordinary, total - k, rng)
    groups = [("monitored", g) for g in watched_groups] + [("R", g) for g in ordinary_groups]
    if initial:
        ordered = list(range(len(groups)))
        rng.shuffle(ordered)
        signs = [i % 2 for i in range((len(groups) + 1) // 2)]
        rng.shuffle(signs)
        first = [(signs[i // 2], [c for j in ordered[i:i + 2] for c in groups[j][1]])
                 for i in range(0, len(groups), 2)]
        assignments = first + [(1 - t, clients[:]) for t, clients in first]
        assignments += [(i % 2, []) for i in range(rounds - len(assignments))]
    else:
        assignments = [(i % 2, watched[:]) for i in range(rounds)]
        for trap in (0, 1):
            slots = [i for i in range(rounds) if i % 2 == trap]
            order = list(range(len(ordinary_groups)))
            rng.shuffle(order)
            for j, group in enumerate(order):
                assignments[slots[j % len(slots)]][1].extend(ordinary_groups[group])
    selected = {c: {} for c in active}
    for c in active:
        for trap in (0, 1):
            positions = [i for i, (t, members) in enumerate(assignments) if t == trap and c in members]
            if not positions:
                raise ValueError("Schedule missed a client/trap")
            selected[c][trap] = rng.choice(positions)
    return {"assignments": assignments, "groups": groups, "selected": selected}


class CycleState:
    def __init__(self, clients, strong_cycles=2, clean_cycles=2, probation_cycles=1):
        self.strong_cycles = strong_cycles
        self.clean_cycles = clean_cycles
        self.probation_cycles = probation_cycles
        self.records = {c: dict(category="R", strong=0, clean=0, probation=0,
                                last_cycle=-1, last_screen="", removed_round=None) for c in clients}

    @property
    def active(self):
        return [c for c, r in self.records.items() if r["category"] != "X"]

    @property
    def monitored(self):
        return {c for c, r in self.records.items() if r["category"] in ("S", "C")}

    @property
    def pending_probation(self):
        return any(r["category"] == "R" and r["probation"] > 0 for r in self.records.values())

    def apply(self, decisions, cycle, round_index):
        ids = [d["client_id"] for d in decisions]
        if len(set(ids)) != len(ids) or set(ids) != set(self.active):
            raise ValueError("Transition requires a complete active-client cycle")
        events = []
        for d in decisions:
            c = d["client_id"]
            r = self.records[c]
            previous = r["category"]
            state = d["state"]
            if state == "S":
                r["strong"] = r["strong"] + 1 if r["last_cycle"] == cycle - 1 and r["last_screen"] == "S" else 1
                r.update(clean=0, probation=0, category="S")
                if r["strong"] >= self.strong_cycles:
                    r.update(category="X", removed_round=round_index)
                    events.append(dict(client_id=c, event="remove", reason="consecutive_double_trap_cycles"))
            elif state == "C":
                r.update(category="C", strong=0, clean=0, probation=0)
            elif state == "R":
                r["strong"] = 0
                if previous in ("S", "C"):
                    r["clean"] = r["clean"] + 1 if r["last_cycle"] == cycle - 1 and r["last_screen"] == "R" else 1
                    r["category"] = "C"
                    if r["clean"] >= self.clean_cycles:
                        r.update(category="R", probation=self.probation_cycles)
                        events.append(dict(client_id=c, event="rehabilitate", reason="two_complete_clean_cycles"))
                else:
                    r["probation"] = max(0, r["probation"] - 1)
            else:
                raise ValueError("Unknown screening category")
            r.update(last_cycle=cycle, last_screen=state)
            d.update(category_after=r["category"], strong_cycles=r["strong"], clean_cycles=r["clean"],
                     reference_eligible=int(r["category"] == "R" and r["probation"] == 0),
                     removed=int(r["category"] == "X"))
        return events

    def escalate_audit(self, clients):
        for c in clients:
            if c in self.records and self.records[c]["category"] != "X":
                self.records[c].update(category="C", strong=0, clean=0, probation=0)

    def state_dict(self):
        return copy.deepcopy(self.records)

    def load_state_dict(self, records):
        self.records = copy.deepcopy(records)
