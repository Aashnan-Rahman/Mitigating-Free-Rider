from __future__ import annotations

import hashlib
from collections.abc import Mapping

import torch


def model_fingerprint(state: Mapping[str, torch.Tensor]) -> str:
    """Return a deterministic fingerprint of every tensor in a model state."""
    digest = hashlib.sha256()
    for key in sorted(state):
        tensor = state[key].detach().contiguous().cpu()
        digest.update(key.encode("utf-8"))
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(repr(tuple(tensor.shape)).encode("ascii"))
        digest.update(tensor.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()
