from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from typing import Deque

import torch

from config import ExperimentConfig
from server.aggregation import clone_state, floating_keys

StateDict = Mapping[str, torch.Tensor]


class FreeRiderAttacker:
    def __init__(self, config: ExperimentConfig, device: torch.device) -> None:
        self.config = config
        self.device = device
        self.last_legit_state: dict[int, dict[str, torch.Tensor]] = {}
        self.fr3_buffers: dict[int, Deque[dict[str, torch.Tensor]]] = defaultdict(
            lambda: deque(maxlen=config.fr3_window)
        )
        self.previous_legit_state: dict[int, dict[str, torch.Tensor]] = {}
        self.fr4_delta_history: dict[int, Deque[torch.Tensor]] = defaultdict(
            lambda: deque(maxlen=config.fr4_history_size)
        )

    def observe_received(
        self, client_id: int, received_state: StateDict, is_trapped: bool
    ) -> None:
        if self.config.attack_type == "FR3":
            self.fr3_buffers[client_id].append(clone_state(received_state))

        if not is_trapped:
            current = clone_state(received_state)
            previous = self.previous_legit_state.get(client_id)
            if previous is not None:
                self.fr4_delta_history[client_id].append(
                    flatten_delta(current, previous).detach().cpu()
                )
            self.previous_legit_state[client_id] = clone_state(current)
            self.last_legit_state[client_id] = clone_state(current)

    def fabricate(
        self,
        client_id: int,
        received_state: StateDict,
        round_idx: int,
        generator: torch.Generator,
    ) -> dict[str, torch.Tensor]:
        attack_type = self.config.attack_type
        if attack_type == "FR1":
            return self._fr1(client_id, received_state)
        if attack_type == "FR2":
            return self._fr2(received_state, generator)
        if attack_type == "FR3":
            return self._fr3(client_id, received_state)
        if attack_type == "FR4":
            return self._fr4(client_id, received_state, round_idx, generator)
        raise ValueError(f"Unsupported attack type: {attack_type}")

    def _fr1(self, client_id: int, received_state: StateDict) -> dict[str, torch.Tensor]:
        return clone_state(self.last_legit_state.get(client_id, received_state))

    def _fr2(
        self, received_state: StateDict, generator: torch.Generator
    ) -> dict[str, torch.Tensor]:
        fabricated: dict[str, torch.Tensor] = {}
        for key, tensor in received_state.items():
            if torch.is_floating_point(tensor):
                std = tensor.detach().float().std(unbiased=False).clamp_min(
                    self.config.trap_noise_floor
                )
                mean = tensor.detach().float().mean()
                fabricated[key] = torch.randn(
                    tensor.shape,
                    generator=generator,
                    device=tensor.device,
                    dtype=tensor.dtype,
                ).mul(std).add(mean)
            else:
                fabricated[key] = tensor.detach().clone()
        return fabricated

    def _fr3(self, client_id: int, received_state: StateDict) -> dict[str, torch.Tensor]:
        buffer = self.fr3_buffers[client_id]
        if not buffer:
            return clone_state(received_state)
        averaged = clone_state(received_state)
        for key, tensor in averaged.items():
            if torch.is_floating_point(tensor):
                stacked = torch.stack([state[key].to(tensor.device) for state in buffer])
                averaged[key] = stacked.mean(dim=0)
        return averaged

    def _fr4(
        self,
        client_id: int,
        received_state: StateDict,
        round_idx: int,
        generator: torch.Generator,
    ) -> dict[str, torch.Tensor]:
        history = self.fr4_delta_history[client_id]
        keys = floating_keys(received_state)
        if history:
            expected = torch.stack([delta.to(self.device) for delta in history]).mean(dim=0)
            noise = torch.randn(
                expected.shape,
                generator=generator,
                device=expected.device,
                dtype=expected.dtype,
            )
            noise_norm = noise.norm().clamp_min(self.config.zero_update_epsilon)
            expected_norm = expected.norm().clamp_min(self.config.zero_update_epsilon)
            fabricated_delta = expected + (
                noise * (expected_norm / noise_norm) * self.config.fr4_noise_fraction
            )
        else:
            parts = [
                torch.randn(
                    received_state[key].numel(),
                    generator=generator,
                    device=received_state[key].device,
                    dtype=received_state[key].dtype,
                )
                * self.config.trap_noise_floor
                for key in keys
            ]
            fabricated_delta = torch.cat(parts) if parts else torch.empty(0, device=self.device)

        return add_flat_delta(received_state, fabricated_delta, keys)


def flatten_delta(new_state: StateDict, base_state: StateDict) -> torch.Tensor:
    pieces = []
    for key in floating_keys(base_state):
        pieces.append((new_state[key] - base_state[key]).detach().flatten().float())
    if not pieces:
        first = next(iter(base_state.values()))
        return torch.empty(0, device=first.device)
    return torch.cat(pieces)


def add_flat_delta(
    base_state: StateDict, flat_delta: torch.Tensor, keys: list[str]
) -> dict[str, torch.Tensor]:
    updated = clone_state(base_state)
    offset = 0
    for key in keys:
        tensor = base_state[key]
        width = tensor.numel()
        delta = flat_delta[offset : offset + width].to(device=tensor.device, dtype=tensor.dtype)
        updated[key] = tensor + delta.view_as(tensor)
        offset += width
    return updated
