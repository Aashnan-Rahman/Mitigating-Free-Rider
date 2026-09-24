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
        self.clean_double_cycles = 0
        self.clean_single_cycles = 0
        self.dormant_rounds_elapsed = 0

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
            "clean_double_cycles": self.clean_double_cycles,
            "clean_single_cycles": self.clean_single_cycles,
            "dormant_rounds_elapsed": self.dormant_rounds_elapsed,
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.mode = str(state.get("mode", "double_probe"))
        self.queue = [
            (int(item["trap_id"]), [int(client_id) for client_id in item["clients"]])
            for item in state.get("queue", [])
        ]
        self.cycle_index = int(state.get("cycle_index", 0))
        self.clean_double_cycles = int(state.get("clean_double_cycles", 0))
        self.clean_single_cycles = int(state.get("clean_single_cycles", 0))
        self.dormant_rounds_elapsed = int(state.get("dormant_rounds_elapsed", 0))

    def select(
        self,
        round_idx: int,
        active_clients: list[int],
        penalties: dict[int, float],
        times_flagged: dict[int, int],
        suspected_clients: set[int] | None = None,
        candidate_clients: set[int] | None = None,
    ) -> TrapSelection:
        del penalties, times_flagged
        if round_idx <= self.config.warmup_rounds or not active_clients:
            return TrapSelection("warmup", set(), set())

        if self.config.methodology_version == "swtcp_v10" and self.mode == "dormant":
            if self.dormant_rounds_elapsed < self.config.cycle_dormant_rounds:
                self.dormant_rounds_elapsed += 1
                return TrapSelection(
                    "dormant",
                    set(),
                    set(),
                    anchor_rotation_cycle=self.cycle_index,
                )
            self.mode = "single_probe"
            self.dormant_rounds_elapsed = 0

        if not self.queue:
            self.queue = self._build_cycle(
                active_clients,
                suspected_clients or set(),
                candidate_clients or set(),
            )
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
        """Advance probing intensity after a completed population sweep."""
        if self.config.methodology_version != "swtcp_v10":
            self.mode = "double_probe" if anomaly_found else "single_probe"
            self.queue.clear()
            self.cycle_index += 1
            return

        if self.mode == "double_probe":
            if anomaly_found:
                self.clean_double_cycles = 0
            else:
                self.clean_double_cycles += 1
                if (
                    self.clean_double_cycles
                    >= self.config.cycle_double_clean_cycles_before_single
                ):
                    self.mode = "single_probe"
                    self.clean_single_cycles = 0
        elif self.mode == "single_probe":
            if anomaly_found:
                self.mode = "double_probe"
                self.clean_double_cycles = 0
                self.clean_single_cycles = 0
            else:
                self.clean_single_cycles += 1
                if (
                    self.clean_single_cycles
                    >= self.config.cycle_single_clean_cycles_before_dormant
                ):
                    self.mode = "dormant"
                    self.dormant_rounds_elapsed = 0
        self.queue.clear()
        self.cycle_index += 1

    def _build_cycle(
        self,
        active_clients: list[int],
        suspected_clients: set[int],
        candidate_clients: set[int],
    ) -> list[tuple[int, list[int]]]:
        groups = self._build_state_groups(
            active_clients, suspected_clients, candidate_clients
        )
        group_count = len(groups)

        if self.mode == "single_probe":
            order = list(range(group_count))
            self.rng.shuffle(order)
            return [(0, groups[index]) for index in order]

        # Probe two groups per round. Five assignments cover every group with
        # trap 0 and five more do the same with trap 1. The ten assignments are
        # then mixed, so the two probe rounds are not predictable by position.
        queue: list[tuple[int, list[int]]] = []
        previous_pairs: set[frozenset[int]] = set()
        for trap_id in (0, 1):
            order = self._nonrepeating_pair_order(group_count, previous_pairs)
            current_pairs: set[frozenset[int]] = set()
            for start in range(0, group_count, 2):
                clients: list[int] = []
                paired_groups = order[start : start + 2]
                current_pairs.add(frozenset(paired_groups))
                for group_index in paired_groups:
                    clients.extend(groups[group_index])
                queue.append((trap_id, clients))
            previous_pairs = current_pairs
        self.rng.shuffle(queue)
        return queue

    def _build_state_groups(
        self,
        active_clients: list[int],
        suspected_clients: set[int],
        candidate_clients: set[int],
    ) -> list[list[int]]:
        """Build exactly ten balanced, state-homogeneous groups when possible."""
        active = set(active_clients)
        pools = {
            "R": list(active - suspected_clients - candidate_clients),
            "C": list(active & candidate_clients - suspected_clients),
            "S": list(active & suspected_clients),
        }
        pools = {name: clients for name, clients in pools.items() if clients}
        for clients in pools.values():
            self.rng.shuffle(clients)

        group_count = min(self.config.surveillance_groups, len(active_clients))
        allocations = {name: 1 for name in pools}
        remaining = group_count - len(allocations)
        while remaining > 0:
            eligible = [
                name
                for name, clients in pools.items()
                if allocations[name] < len(clients)
            ]
            if not eligible:
                break
            chosen = max(
                eligible,
                key=lambda name: len(pools[name]) / allocations[name],
            )
            allocations[chosen] += 1
            remaining -= 1

        groups: list[list[int]] = []
        for name in ("R", "C", "S"):
            if name not in pools:
                continue
            state_groups = [[] for _ in range(allocations[name])]
            for index, client_id in enumerate(pools[name]):
                state_groups[index % len(state_groups)].append(client_id)
            groups.extend(state_groups)
        return groups

    def _nonrepeating_pair_order(
        self, group_count: int, forbidden: set[frozenset[int]]
    ) -> list[int]:
        """Return a random order whose adjacent pairs avoid the prior pass."""
        order = list(range(group_count))
        for _ in range(100):
            self.rng.shuffle(order)
            pairs = {
                frozenset(order[start : start + 2])
                for start in range(0, group_count, 2)
            }
            if group_count <= 2 or not (pairs & forbidden):
                return order
        # A deterministic one-position rotation is a safe fallback for the
        # normal ten-group case if random retries are exceptionally unlucky.
        return order[1:] + order[:1]
