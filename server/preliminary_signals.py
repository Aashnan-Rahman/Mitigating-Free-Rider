"""V14.1 preliminary same-trap measurements; no labels or decisions."""
import json
from statistics import median, NormalDist
import torch

REVISION = "v14.1 preli"


def robust(values, value):
    center = median(values)
    mad = median(abs(item - center) for item in values)
    scale = mad / NormalDist().inv_cdf(.75)
    return center, mad, (value - center) / scale if scale > 0 else None


class PreliminarySignals:
    def __init__(self):
        self.responses = {0: {}, 1: {}}

    def observe(self, client, trap, delta, profile, round_index):
        if not torch.isfinite(delta).all() or not torch.isfinite(profile).all():
            raise ValueError("Nonfinite preliminary response")
        if client in self.responses[trap]:
            raise ValueError("Duplicate preliminary probe")
        self.responses[trap][client] = {"delta": delta.detach().float().cpu().clone(),
            "profile": profile.detach().float().cpu().clone(), "round": round_index}

    def complete(self, expected_clients=None):
        if set(self.responses[0]) != set(self.responses[1]) or not self.responses[0]:
            raise ValueError("Incomplete two-trap coverage")
        if expected_clients is not None and set(self.responses[0]) != set(expected_clients):
            raise ValueError("Missing preliminary clients")
        rows = []
        for trap, responses in self.responses.items():
            norms = {client: float(item["delta"].norm()) for client, item in responses.items()}
            total = torch.zeros_like(next(iter(responses.values()))["delta"])
            for item in responses.values():
                total.add_(item["delta"])
            for client, item in sorted(responses.items()):
                peers = [peer for peer in responses if peer != client]
                if not peers:
                    raise ValueError("Peer comparison requires other clients")
                center, mad, z = robust([norms[peer] for peer in peers], norms[client])
                reference = (total - item["delta"]) / len(peers)
                rn = float(reference.norm())
                cosine = float(torch.dot(item["delta"], reference)) / (norms[client] * rn) if norms[client] > 0 and rn > 0 else None
                profiles = torch.stack([responses[peer]["profile"] for peer in peers])
                profile_center = profiles.median(dim=0).values
                distances = [float((profile - profile_center).norm()) for profile in profiles]
                distance = float((item["profile"] - profile_center).norm())
                pc, pmad, pz = robust(distances, distance)
                rows.append({"round": 20, "client_id": client, "trap_id": trap,
                    "observation_round": item["round"], "reference_clients": len(peers),
                    "delta_norm": norms[client], "norm_z": z, "norm_median": center, "norm_mad": mad,
                    "cosine_similarity": max(-1., min(1., cosine)) if cosine is not None else None,
                    "cosine_reference_norm": rn, "profile_distance": distance,
                    "profile_z": pz, "profile_median": pc, "profile_mad": pmad,
                    "layer_profile": json.dumps(item["profile"].tolist()),
                    "exact_zero_delta": int(norms[client] == 0), "enforced": 0})
        return rows

    def state_dict(self):
        return self.responses

    def load_state_dict(self, state):
        self.responses = state
