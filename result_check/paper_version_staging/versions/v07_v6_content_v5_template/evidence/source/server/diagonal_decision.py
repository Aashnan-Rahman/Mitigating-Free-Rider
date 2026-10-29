"""Label-blind, provisional round-20 diagonal histogram screening.

Bootstrap intervals describe boundary stability, not an honest-client error
guarantee. No decisions from this module authorize removal or quarantine.
"""
import math
import numpy as np

REVISION = "diagonal_histogram_bootstrap_v1"
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_CONFIDENCE = .99
BOOTSTRAP_SEED = 20261011


def policy():
    return dict(revision=REVISION, score="profile_z - norm_z",
                views=["average", "trap_A", "trap_B"], bins="ceil(sqrt(valid_clients))",
                bootstrap_replicates=BOOTSTRAP_REPLICATES,
                bootstrap_confidence=BOOTSTRAP_CONFIDENCE,
                bootstrap_seed=BOOTSTRAP_SEED, enforced=False)


def _boundaries(counts, centers, edges):
    weights = counts / counts.sum(axis=1, keepdims=True)
    left = np.cumsum(weights, axis=1)[:, :-1]
    moments = np.cumsum(weights * centers, axis=1)[:, :-1]
    total = np.sum(weights * centers, axis=1)[:, None]
    valid = (left > 0) & (left < 1)
    variance = np.full(left.shape, -np.inf)
    numerator = (total * left - moments) ** 2
    np.divide(numerator, left * (1 - left), out=variance, where=valid)
    result = edges[np.argmax(variance, axis=1) + 1].astype(float)
    result[~np.any(valid, axis=1)] = np.nan
    return result


def classify(rows):
    """Accept only public scalar responses, never attack metadata or labels."""
    clients = {}
    for row in rows:
        client = row["client_id"]
        trap = int(row["trap_id"])
        if trap not in (0, 1) or trap in clients.setdefault(client, {}):
            raise ValueError("Expected one response per client per trap")
        # Explicit allowlist: ignore any evaluation-only fields in caller data.
        clients[client][trap] = {key: row.get(key) for key in
                               ("norm_z", "profile_z", "exact_zero_delta")}
    decisions, usable = [], []
    for client, probes in clients.items():
        scores = []
        zero = set(probes) == {0, 1} and all(
            probes[t]["exact_zero_delta"] in (1, True, "1") for t in (0, 1))
        for trap in (0, 1):
            try:
                score = float(probes[trap]["profile_z"]) - float(probes[trap]["norm_z"])
                scores.append(score if math.isfinite(score) else None)
            except (KeyError, TypeError, ValueError):
                scores.append(None)
        row = dict(round=20, client_id=client, D_A=scores[0], D_B=scores[1],
                   D_average=(sum(scores) / 2 if None not in scores else None),
                   state="S" if zero else "C",
                   reason="exact_zero_both_traps" if zero else "undefined_or_unresolved",
                   provisional=1, enforced=0)
        decisions.append(row)
        if None not in scores:
            usable.append(len(decisions) - 1)
    metadata = {**policy(), "clients": len(clients), "valid_clients": len(usable),
                "majority_gate": False, "boundaries": [], "status": "insufficient_or_degenerate"}
    if len(usable) < 2:
        return decisions, metadata
    values = np.array([[decisions[i]["D_average"], decisions[i]["D_A"], decisions[i]["D_B"]]
                       for i in usable])
    if np.any(np.ptp(values, axis=0) == 0):
        return decisions, metadata
    n = len(values)
    bins = math.ceil(math.sqrt(n))
    samples = np.random.default_rng(BOOTSTRAP_SEED).integers(n, size=(BOOTSTRAP_REPLICATES, n))
    alpha = (1 - BOOTSTRAP_CONFIDENCE) / 2
    for column in range(3):
        x = values[:, column]
        edges = np.linspace(x.min(), x.max(), bins + 1)
        centers = (edges[:-1] + edges[1:]) / 2
        indices = np.clip(np.searchsorted(edges, x, side="right") - 1, 0, bins - 1)
        original = _boundaries(np.bincount(indices, minlength=bins)[None, :], centers, edges)[0]
        counts = np.zeros((BOOTSTRAP_REPLICATES, bins))
        np.add.at(counts, (np.arange(BOOTSTRAP_REPLICATES)[:, None], indices[samples]), 1)
        thresholds = _boundaries(counts, centers, edges)
        # Any resample with no split defers the whole statistical decision.
        if not np.all(np.isfinite(thresholds)):
            return decisions, metadata
        metadata["boundaries"].append(dict(view=policy()["views"][column], threshold=float(original),
            lower=float(np.quantile(thresholds, alpha, method="lower")),
            upper=float(np.quantile(thresholds, 1 - alpha, method="higher"))))
    # A minority of valid observations must not certify an honest majority.
    majority = np.count_nonzero(values[:, 0] <= metadata["boundaries"][0]["threshold"]) > len(clients) / 2
    metadata.update(majority_gate=bool(majority), bins=bins,
                    status="provisional_split" if majority else "majority_gate_failed")
    if not majority:
        return decisions, metadata
    lower = np.array([b["lower"] for b in metadata["boundaries"]])
    upper = np.array([b["upper"] for b in metadata["boundaries"]])
    for i, point in zip(usable, values):
        if decisions[i]["reason"] == "exact_zero_both_traps":
            continue
        state = "R" if np.all(point < lower) else "S" if np.all(point > upper) else "C"
        decisions[i].update(state=state, reason={"R": "all_views_below_band", "S": "all_views_above_band",
                                               "C": "boundary_or_view_disagreement"}[state])
    return decisions, metadata


def evaluation_summary(rows):
    """Evaluation only; never used by classify."""
    return [dict(round=20, population=label,
                 suspected=sum(r["state"] == "S" for r in rows if int(r["is_free_rider"]) == flag),
                 candidate=sum(r["state"] == "C" for r in rows if int(r["is_free_rider"]) == flag),
                 safe=sum(r["state"] == "R" for r in rows if int(r["is_free_rider"]) == flag), enforced=0)
            for label, flag in (("free_rider", 1), ("honest", 0))]
