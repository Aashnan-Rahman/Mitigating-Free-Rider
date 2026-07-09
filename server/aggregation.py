from __future__ import annotations

from collections.abc import Iterable, Mapping

import torch

StateDict = Mapping[str, torch.Tensor]


def clone_state(state: StateDict) -> dict[str, torch.Tensor]:
    return {key: value.detach().clone() for key, value in state.items()}


def floating_keys(state: StateDict) -> list[str]:
    return [key for key, value in state.items() if torch.is_floating_point(value)]


def fedavg_delta(
    base_state: StateDict, client_states: Iterable[StateDict]
) -> dict[str, torch.Tensor]:
    states = list(client_states)
    if not states:
        return clone_state(base_state)

    next_state = clone_state(base_state)
    for key, base_tensor in base_state.items():
        if not torch.is_floating_point(base_tensor):
            continue
        deltas = [state[key].to(base_tensor.device) - base_tensor for state in states]
        mean_delta = torch.stack(deltas).mean(dim=0)
        next_state[key] = base_tensor + mean_delta
    return next_state


def make_trap_state(
    base_state: StateDict, scale: float, floor: float, generator: torch.Generator
) -> dict[str, torch.Tensor]:
    trap_state = clone_state(base_state)
    for key, tensor in base_state.items():
        if torch.is_floating_point(tensor):
            std = tensor.detach().float().std(unbiased=False).clamp_min(floor)
            noise = torch.randn(
                tensor.shape,
                generator=generator,
                device=tensor.device,
                dtype=tensor.dtype,
            )
            trap_state[key] = tensor + noise * std * scale
    return trap_state
