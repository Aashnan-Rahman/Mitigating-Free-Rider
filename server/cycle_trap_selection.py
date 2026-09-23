from __future__ import annotations

import random
from typing import Any, Mapping

from config import ExperimentConfig
from server.trap_selection import TrapSelection


class CycleTrapSelector:
    """Schedule v9 warm-up, double-probe cycles, and single-probe sweeps."""

    def __init__(self, config: ExperimentConfig, rng: random.Random) -> None:
        self.config = config
        self.rng = rng
        self.mode = "double_probe"
        self.queue: list[tuple[int, list[int]]] = []
        self.cycle_index = 0

    @property
    def checks_per_client(self) -> int:
        return 2 if self.mode == "double_probe" else 1

    def state_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "queue": [
                {"trap_id": trap_id, "clients": clients[:]}
                for trap_id, clients in self.queue
            ],
            "cycle_index": self.cycle_index,
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.mode = str(state.get("mode", "double_probe"))
        self.queue = [
            (int(item["trap_id"]), [int(client_id) for client_id in item["clients"]])
            for item in state.get("queue", [])
        ]
        self.cycle_index = int(state.get("cycle_index", 0))

    def select(
        self,
        round_idx: int,
        active_clients: list[int],
        penalties: dict[int, float],
        times_flagged: dict[int, int],
        suspected_clients: set[int] | None = None,
        candidate_clients: set[int] | None = None,
    ) -> TrapSelection:
        del penalties, times_flagged, suspected_clients, candidate_clients
        if round_idx <= self.config.warmup_rounds or not active_clients:
            return TrapSelection("warmup", set(), set())

        if not self.queue:
            self.queue = self._build_cycle(active_clients)
        trap_id, scheduled = self.queue.pop(0)
        active = set(active_clients)
        trapped = {client_id for client_id in scheduled if client_id in active}
        return TrapSelection(
            phase=self.mode,
            trapped_clients=trapped,
            anchors=set(),
            coverage_complete=not self.queue,
            coverage_trap_id=trap_id,
            surveillance_clients=trapped if self.mode == "single_probe" else set(),
            surveillance_complete=not self.queue if self.mode == "single_probe" else False,
            anchor_rotation_cycle=self.cycle_index,
        )

    def finish_cycle(self, anomaly_found: bool) -> None:
        """A clean double cycle relaxes to surveillance; any anomaly uses double."""
        self.mode = "double_probe" if anomaly_found else "single_probe"
        self.queue.clear()
        self.cycle_index += 1

    def _build_cycle(self, active_clients: list[int]) -> list[tuple[int, list[int]]]:
        shuffled = active_clients[:]
        self.rng.shuffle(shuffled)
        group_count = min(self.config.surveillance_groups, len(shuffled))
        groups = [[] for _ in range(group_count)]
        for index, client_id in enumerate(shuffled):
            groups[index % group_count].append(client_id)

        if self.mode == "single_probe":
            order = list(range(group_count))
            self.rng.shuffle(order)
            return [(0, groups[index]) for index in order]

        # Probe two groups per round. Five assignments cover every group with
        # trap 0 and five more do the same with trap 1. The ten assignments are
        # then mixed, so the two probe rounds are not predictable by position.
        queue: list[tuple[int, list[int]]] = []
        for trap_id in (0, 1):
            order = list(range(group_count))
            self.rng.shuffle(order)
            for start in range(0, group_count, 2):
                clients: list[int] = []
                for group_index in order[start : start + 2]:
                    clients.extend(groups[group_index])
                queue.append((trap_id, clients))
        self.rng.shuffle(queue)
        return queue
