"""Frozen, attack-agnostic, three-cycle combined scoring. Shadow decisions only.

Rank calibration is empirical in FL: correlated clients and distribution shift
prevent a deployment-wide false-positive guarantee. No labels enter this class.
"""
from __future__ import annotations

import hashlib
import json
import math
from statistics import NormalDist, median
from pathlib import Path

REVISION = "paired_combined_shadow_v1"
WINDOW = 3
CONTEXT_FIELDS = ("dataset", "distribution", "dirichlet_alpha", "num_clients",
                  "num_rounds", "warmup_rounds", "local_epochs", "batch_size",
                  "optimizer", "learning_rate", "momentum", "surveillance_groups",
                  "trap_noise_scale", "trap_noise_floor")


def load_artifact(path, expected_sha256=None):
    raw = Path(path).read_bytes()
    if expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256.lower():
        raise ValueError("Frozen calibration file changed; start a new protocol")
    return json.loads(raw)


def context_from_config(config):
    return {key: getattr(config, key) for key in CONTEXT_FIELDS}


def feature_vector(features):
    # All components are specified before fresh evaluation. Two-sided scoring
    # never checks a known FR signature/window or a handpicked numerical cutoff.
    norms = [float(features[key]) for key in ("plus_update_norm", "minus_update_norm")]
    profile = float(features["profile_difference"])
    if min(norms + [profile]) <= 0:
        raise ValueError("Positive norms and profile difference required")
    layers = features["layer_gains"]
    if isinstance(layers, str):
        layers = json.loads(layers)
    values = [float(features["directional_gain"]),
              sum(math.log(norm) for norm in norms) / 2, math.log(profile)]
    values.extend(float(value) for value in layers)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Nonfinite combined feature")
    return values


def window_vector(vectors):
    if len(vectors) != WINDOW or len({len(vector) for vector in vectors}) != 1:
        raise ValueError("Exactly three matching feature vectors required")
    return [median(column) for column in zip(*vectors)]


def combined_score(vector, center, scale):
    if not len(vector) == len(center) == len(scale):
        raise ValueError("Feature dimensions changed")
    return max(abs(value - location) / width
               for value, location, width in zip(vector, center, scale))


def fit_artifact(fit_vectors, calibration_vectors, *, context, alpha, provenance):
    from server.v13_detection import upper_quantile
    if not fit_vectors or not calibration_vectors:
        raise ValueError("Separate fitting and calibration windows required")
    if len({len(vector) for vector in fit_vectors + calibration_vectors}) != 1:
        raise ValueError("Feature dimensions changed")
    if not fit_vectors[0] or not all(math.isfinite(value)
                                   for vector in fit_vectors + calibration_vectors for value in vector):
        raise ValueError("Finite, nonempty fitting/calibration vectors required")
    center = [median(column) for column in zip(*fit_vectors)]
    factor = 1 / NormalDist().inv_cdf(.75)
    scale = [factor * median(abs(value - location) for value in column)
             for column, location in zip(zip(*fit_vectors), center)]
    # No fitted variance floor or silent dropped features. Degenerate fitting
    # data cannot support this scoring model and requires new calibration.
    if any(not math.isfinite(value) or value <= 0 for value in scale):
        raise ValueError("Degenerate fitting scale; do not invent a threshold")
    scores = [combined_score(vector, center, scale) for vector in calibration_vectors]
    cutoff = upper_quantile(scores, alpha)
    return {"revision": REVISION, "window": WINDOW, "context": context,
            "alpha": alpha, "center": center, "scale": scale,
            "cutoff": cutoff if math.isfinite(cutoff) else None,
            "calibration_windows": len(scores), "fit_windows": len(fit_vectors),
            "provenance": provenance,
            "guarantee": "Empirical FL calibration; no lifetime/distribution-free guarantee"}


class PairedShadow:
    def __init__(self, artifact, *, context, alpha):
        if artifact.get("revision") != REVISION or artifact.get("window") != WINDOW:
            raise ValueError("Unsupported shadow calibration protocol")
        if artifact.get("context") != context or artifact.get("alpha") != alpha:
            raise ValueError("Shadow calibration context/risk budget mismatch")
        if len(artifact["center"]) != len(artifact["scale"]) or not artifact["center"]:
            raise ValueError("Invalid shadow calibration dimensions")
        if not all(math.isfinite(value) for value in artifact["center"]):
            raise ValueError("Invalid calibration center")
        if not all(math.isfinite(value) and value > 0 for value in artifact["scale"]):
            raise ValueError("Invalid calibration scale")
        cutoff = artifact["cutoff"]
        if cutoff is not None and (not math.isfinite(cutoff) or cutoff < 0):
            raise ValueError("Invalid calibration cutoff")
        self.artifact = artifact
        self.fingerprint = hashlib.sha256(json.dumps(artifact, sort_keys=True, allow_nan=False).encode()).hexdigest()
        self.histories = {}
        self.last_cycles = {}
        self.proposed = set()

    def observe(self, client: int, cycle: int, features: dict):
        result = {"client_id": client, "cycle": cycle, "score": None,
                  "cutoff": self.artifact["cutoff"], "proposed_remove": 0,
                  "reason": "awaiting_three_cycles", "alpha": self.artifact["alpha"],
                  "calibration_windows": self.artifact["calibration_windows"],
                  "calibration_fingerprint": self.fingerprint,
                  "enforced": 0}
        history = self.histories.setdefault(client, [])
        previous = self.last_cycles.get(client)
        if previous is not None and cycle <= previous:
            raise ValueError("Repeated/out-of-order shadow observation")
        if previous is not None and cycle != previous + 1:
            history.clear()
        self.last_cycles[client] = cycle
        try:
            vector = feature_vector(features)
            if len(vector) != len(self.artifact["center"]):
                raise ValueError("Feature dimensions changed")
        except (ValueError, TypeError):
            history.clear()
            result["reason"] = "invalid_features_deferred"
            return result
        history.append((cycle, vector))
        if len(history) < WINDOW:
            return result
        aggregate = window_vector([vector for _, vector in history])
        history.clear()  # Non-overlapping windows; never reuse an old strike.
        result["score"] = combined_score(aggregate, self.artifact["center"], self.artifact["scale"])
        if result["cutoff"] is None:
            result["reason"] = "insufficient_calibration_deferred"
        else:
            result["proposed_remove"] = int(result["score"] > result["cutoff"])
            result["reason"] = "combined_window_exceeds_boundary" if result["proposed_remove"] else "within_calibrated_boundary"
            if result["proposed_remove"]:
                self.proposed.add(client)
        return result

    def state_dict(self):
        return {"fingerprint": self.fingerprint, "histories": self.histories,
                "last_cycles": self.last_cycles,
                "proposed": sorted(self.proposed)}

    def load_state_dict(self, state):
        if state["fingerprint"] != self.fingerprint:
            raise ValueError("Shadow calibration changed; start a fresh run")
        self.histories = state["histories"]
        self.last_cycles = state["last_cycles"]
        self.proposed = set(state["proposed"])
