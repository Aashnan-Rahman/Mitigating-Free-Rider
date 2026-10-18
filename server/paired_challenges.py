"""Server-observable paired response measurements; no classification or labels.

Storage is O(clients * layers), not a history of full client updates. The two
challenge models already held by the server define the perturbation direction.
"""
from __future__ import annotations

import hashlib
import math

import torch

from server.aggregation import clone_state, floating_keys, make_trap_state

REVISION = "paired_measurement_v1"
STREAM_NAMES = ("partition", "attacker_selection", "model", "training",
                "schedule", "trap", "attack")


def derive_seed(master: int, name: str) -> int:
    digest = hashlib.sha256(f"swtcp-paired-v1:{master}:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**63 - 1)


def stream_seeds(config) -> dict[str, int]:
    return {name: (getattr(config, name + "_seed")
                   if getattr(config, name + "_seed") is not None
                   else derive_seed(config.seed, name)) for name in STREAM_NAMES}


def make_pair(base, scale: float, floor: float, generator: torch.Generator):
    plus = make_trap_state(base, scale, floor, generator)
    minus = clone_state(base)
    for key in floating_keys(base):
        minus[key] = base[key] - (plus[key] - base[key])
    return {0: plus, 1: minus}


def summarize_response(delta: torch.Tensor, pair) -> dict:
    """Project a response onto h=(theta_plus-theta_minus)/2, by layer."""
    dots, energies, offset = [], [], 0
    for key in floating_keys(pair[0]):
        h = ((pair[0][key] - pair[1][key]) * .5).detach().flatten().float()
        width = h.numel()
        part = delta[offset:offset + width].float()
        dots.append(float(torch.dot(part, h).item()))
        energies.append(float(torch.dot(h, h).item()))
        offset += width
    if offset != delta.numel():
        raise ValueError("Response shape does not match challenge model")
    return {"dots": dots, "energies": energies, "norm": float(delta.norm().item())}


def pair_features(observations: dict[int, dict]) -> dict:
    """Gain=<Delta_plus-Delta_minus,h>/(2<h,h>); no expected attack value."""
    if set(observations) != {0, 1}:
        raise ValueError("Both challenge responses are required")
    plus, minus = observations[0], observations[1]
    energies = plus["energies"]
    if energies != minus["energies"] or len(plus["dots"]) != len(minus["dots"]):
        raise ValueError("Responses are not from the same challenge pair")
    if not all(math.isfinite(x) for o in (plus, minus)
               for x in o["dots"] + o["energies"] + [o["norm"]]):
        raise ValueError("Nonfinite challenge measurement")
    total = sum(energies)
    gains = [(a - b) / (2 * e) if e > 0 else None
             for a, b, e in zip(plus["dots"], minus["dots"], energies)]
    total_gain = sum(a - b for a, b in zip(plus["dots"], minus["dots"])) / (2 * total) if total > 0 else None
    return {"directional_gain": total_gain, "layer_gains": gains,
            "perturbation_energy": total, "plus_update_norm": plus["norm"],
            "minus_update_norm": minus["norm"]}


def measurement_evidence():
    # Existing training loop compatibility; no inferred clearance, flags, or
    # personal histories. Statistical decisions are explicitly disabled.
    return {"results": {}, "checks": {}, "flags": {}, "joint_flags": {},
            "zero_counts": {}, "decision_rounds": {}, "reference_outliers": set(),
            "reference_valid": False, "coherent_strong": {}, "cycle_scores": {},
            "frozen_reference_ids": set(), "norm_scales": [], "profile_scales": [],
            "cutoff": float("inf")}
