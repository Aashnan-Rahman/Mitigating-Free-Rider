"""Evaluation-only summaries; labels never feed server reference construction."""
from statistics import mean, median, quantiles


def compare_rows(rows):
    summaries = []
    for trap in (0, 1):
        for label in (0, 1):
            selected = [row for row in rows if int(row["trap_id"]) == trap
                        and int(row["is_free_rider"]) == label]
            for signal in ("norm_z", "cosine_similarity", "profile_z"):
                values = [float(row[signal]) for row in selected if row[signal] not in (None, "")]
                q = quantiles(values, n=4, method="inclusive") if len(values) > 1 else [None] * 3
                summaries.append({"trap_id": trap, "class": "free_rider" if label else "honest",
                    "signal": signal, "clients": len(selected), "valid": len(values),
                    "undefined": len(selected) - len(values),
                    "mean": mean(values) if values else None, "median": median(values) if values else None,
                    "q25": q[0], "q75": q[2], "min": min(values) if values else None,
                    "max": max(values) if values else None})
    return summaries
