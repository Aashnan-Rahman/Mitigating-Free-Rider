from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from typing import Any, Deque

import torch

from config import ExperimentConfig
from server.aggregation import clone_state, floating_keys

StateDict = Mapping[str, torch.Tensor]


class FreeRiderAttacker:
    def __init__(self, config: ExperimentConfig, device: torch.device) -> None:
        self.config = config
        self.device = device
        # Attackers only know models that the server sent to them. They are never
        # told whether a received model is a trap.
        self.last_received_state: dict[int, dict[str, torch.Tensor]] = {}
        self.fr3_buffers: dict[int, Deque[dict[str, torch.Tensor]]] = defaultdict(
            lambda: deque(maxlen=config.fr3_window)
        )
        self.previous_received_state: dict[int, dict[str, torch.Tensor]] = {}
        self.fr4_delta_history: dict[int, Deque[torch.Tensor]] = defaultdict(
            lambda: deque(maxlen=config.fr4_history_size)
        )

    def state_dict(self) -> dict[str, Any]:
        """Preserve attacker-visible history when continuing a simulation."""
        return {
            "last_received_state": {
                client_id: clone_state(state)
                for client_id, state in self.last_received_state.items()
            },
            "fr3_buffers": {
                client_id: [clone_state(state) for state in states]
                for client_id, states in self.fr3_buffers.items()
            },
            "previous_received_state": {
                client_id: clone_state(state)
                for client_id, state in self.previous_received_state.items()
            },
            "fr4_delta_history": {
                client_id: [delta.detach().clone() for delta in deltas]
                for client_id, deltas in self.fr4_delta_history.items()
            },
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        """Restore only history that the simulated client previously observed."""
        self.last_received_state = {
            int(client_id): clone_state(client_state)
            for client_id, client_state in state.get("last_received_state", {}).items()
        }
        self.fr3_buffers.clear()
        for client_id, states in state.get("fr3_buffers", {}).items():
            self.fr3_buffers[int(client_id)].extend(
                clone_state(client_state) for client_state in states
            )
        self.previous_received_state = {
            int(client_id): clone_state(client_state)
            for client_id, client_state in state.get("previous_received_state", {}).items()
        }
        self.fr4_delta_history.clear()
        for client_id, deltas in state.get("fr4_delta_history", {}).items():
            self.fr4_delta_history[int(client_id)].extend(
                delta.detach().clone() for delta in deltas
            )

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
        # Direct send-back: FR1 performs no training and returns the model from
        # this participation unchanged. Keep the observation in checkpointed
        # attacker state for backward compatibility with existing checkpoints,
        # but never use an older model as the fabricated response.
        fabricated = clone_state(received_state)
        self.last_received_state[client_id] = clone_state(received_state)
        return fabricated

    def _fr2(
        self, received_state: StateDict, generator: torch.Generator
    ) -> dict[str, torch.Tensor]:
        """Add a bounded, memoryless random update to the received model."""
        fabricated: dict[str, torch.Tensor] = {}
        for key, tensor in received_state.items():
            if torch.is_floating_point(tensor):
                random_update = torch.rand(
                    tensor.shape,
                    generator=generator,
                    device=tensor.device,
                    dtype=tensor.dtype,
                ).mul(2.0).sub(1.0).mul(self.config.fr2_update_range)
                fabricated[key] = tensor.detach() + random_update
            else:
                fabricated[key] = tensor.detach().clone()
        return fabricated

    def _fr3(self, client_id: int, received_state: StateDict) -> dict[str, torch.Tensor]:
        buffer = self.fr3_buffers[client_id]
        # The client cannot distinguish trap models, so every received model is
        # part of the same observable history.
        buffer.append(clone_state(received_state))
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
        # Derive public trajectory information from every model this client has
        # received. A secret trap therefore contaminates the attacker's estimate
        # just like any other model; there is intentionally no trap-status input.
        current = clone_state(received_state)
        previous = self.previous_received_state.get(client_id)
        if previous is not None:
            self.fr4_delta_history[client_id].append(
                flatten_delta(current, previous).detach().cpu()
            )
        self.previous_received_state[client_id] = current

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
                * self.config.fr4_cold_start_scale
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
