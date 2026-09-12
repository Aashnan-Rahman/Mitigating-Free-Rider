from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping

from config import ExperimentConfig


@dataclass
class TrapSelection:
    phase: str
    trapped_clients: set[int]
    anchors: set[int]
    coverage_complete: bool = False
    coverage_trap_id: int | None = None
    suspicion_groups: list[tuple[set[int], set[int], set[int]]] = field(default_factory=list)
    candidate_clients: set[int] = field(default_factory=set)
    surveillance_clients: set[int] = field(default_factory=set)
    surveillance_complete: bool = False


class TrapSelector:
    def __init__(self, config: ExperimentConfig, rng: random.Random) -> None:
        self.config = config
        self.rng = rng
        self.phase = "warmup"
        self.coverage_queue: list[tuple[int, list[int]]] = []
        self.initial_coverage_done = False
        self.surveillance_queue: list[list[int]] = []
        self.completed_surveillance_clients: set[int] = set()
        self.anchor_pool: set[int] = set()

    def state_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "coverage_queue": [
                {"trap_id": trap_id, "clients": clients[:]}
                for trap_id, clients in self.coverage_queue
            ],
            "initial_coverage_done": self.initial_coverage_done,
            "surveillance_queue": [group[:] for group in self.surveillance_queue],
            "completed_surveillance_clients": sorted(self.completed_surveillance_clients),
            "anchor_pool": sorted(self.anchor_pool),
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.phase = str(state.get("phase", "suspicion"))
        self.coverage_queue = [
            (
                int(item["trap_id"]),
                [int(client_id) for client_id in item["clients"]],
            )
            for item in state.get("coverage_queue", [])
        ]
        self.initial_coverage_done = bool(state.get("initial_coverage_done", False))
        self.surveillance_queue = [
            [int(client_id) for client_id in group]
            for group in state.get("surveillance_queue", [])
        ]
        self.completed_surveillance_clients = {
            int(client_id)
            for client_id in state.get("completed_surveillance_clients", [])
        }
        self.anchor_pool = {int(client_id) for client_id in state.get("anchor_pool", [])}

    def select(
        self,
        round_idx: int,
        active_clients: list[int],
        penalties: dict[int, int],
        times_flagged: dict[int, int],
        suspected_clients: set[int] | None = None,
        candidate_clients: set[int] | None = None,
    ) -> TrapSelection:
        if round_idx <= self.config.warmup_rounds or not active_clients:
            self.phase = "warmup"
            return TrapSelection("warmup", set(), set())

        if not self.initial_coverage_done and self.phase == "warmup":
            self.start_coverage(active_clients)

        if not self.initial_coverage_done and self.phase == "coverage":
            coverage_item = self._next_coverage_group(active_clients)
            group = coverage_item[1] if coverage_item else []
            if group:
                complete = not self.coverage_queue
                if complete:
                    self.initial_coverage_done = True
                return TrapSelection(
                    "coverage",
                    set(group),
                    set(),
                    complete,
                    coverage_trap_id=coverage_item[0],
                )
            self.initial_coverage_done = True

        return self._select_post_coverage(
            active_clients,
            suspected_clients or set(),
            candidate_clients or set(),
            penalties,
            times_flagged,
        )

    def start_coverage(self, active_clients: list[int]) -> None:
        self.phase = "coverage"
        self.coverage_queue = self._build_coverage_queue(active_clients)

    def _select_post_coverage(
        self,
        active_clients: list[int],
        suspected_clients: set[int],
        candidate_clients: set[int],
        penalties: dict[int, int],
        times_flagged: dict[int, int],
    ) -> TrapSelection:
        active = set(active_clients)
        suspects = active & suspected_clients
        candidates = active & candidate_clients - suspects
        unflagged = active - suspects - candidates
        x_groups = max(1, len(suspects) // self.config.suspicion_target_group_size) if suspects else 0
        probe_group_count = x_groups if x_groups else int(bool(candidates))
        anchor_eligible = {
            client_id
            for client_id in unflagged
            if times_flagged.get(client_id, 0) == 0
        }
        desired_anchors = min(
            self.config.max_suspicion_anchors,
            self.config.anchors_per_suspicion_group * probe_group_count,
            len(anchor_eligible),
        )

        if not self.surveillance_queue:
            self.completed_surveillance_clients.clear()
            self.anchor_pool = set(
                self._anchor_sample(
                    list(anchor_eligible), penalties, times_flagged, desired_anchors
                )
            )
            surveillance = list(unflagged - self.anchor_pool)
            self.rng.shuffle(surveillance)
            self.surveillance_queue = [[] for _ in range(self.config.surveillance_groups)]
            for index, client_id in enumerate(surveillance):
                self.surveillance_queue[index % self.config.surveillance_groups].append(client_id)
        else:
            self.anchor_pool &= anchor_eligible
            if len(self.anchor_pool) > desired_anchors:
                released = list(self.anchor_pool)
                self.rng.shuffle(released)
                released = released[desired_anchors:]
                self.anchor_pool.difference_update(released)
                for client_id in released:
                    if client_id not in self.completed_surveillance_clients:
                        self.rng.choice(self.surveillance_queue).append(client_id)
            elif len(self.anchor_pool) < desired_anchors:
                anchor_candidates = list(anchor_eligible - self.anchor_pool)
                additions = self._anchor_sample(
                    anchor_candidates,
                    penalties,
                    times_flagged,
                    desired_anchors - len(self.anchor_pool),
                )
                self.anchor_pool.update(additions)
                for group in self.surveillance_queue:
                    group[:] = [client_id for client_id in group if client_id not in self.anchor_pool]

            scheduled_unflagged = self.anchor_pool | self.completed_surveillance_clients | {
                client_id for group in self.surveillance_queue for client_id in group
            }
            newly_available = list(unflagged - scheduled_unflagged)
            self.rng.shuffle(newly_available)
            for client_id in newly_available:
                self.rng.choice(self.surveillance_queue).append(client_id)

        suspect_list = list(suspects)
        self.rng.shuffle(suspect_list)
        suspect_groups = [[] for _ in range(probe_group_count)]
        for index, client_id in enumerate(suspect_list):
            suspect_groups[index % probe_group_count].append(client_id)

        candidate_list = list(candidates)
        self.rng.shuffle(candidate_list)
        candidate_groups = [[] for _ in range(probe_group_count)]
        for index, client_id in enumerate(candidate_list):
            candidate_groups[index % probe_group_count].append(client_id)

        anchors = list(self.anchor_pool)
        self.rng.shuffle(anchors)
        anchor_groups = [[] for _ in range(probe_group_count)]
        for index, client_id in enumerate(anchors):
            anchor_groups[index % probe_group_count].append(client_id)

        grouped = [
            (
                set(suspect_groups[index]),
                set(candidate_groups[index]),
                set(anchor_groups[index]),
            )
            for index in range(probe_group_count)
        ]
        surveillance_group = {
            client_id
            for client_id in self.surveillance_queue.pop(0)
            if client_id in unflagged and client_id not in self.anchor_pool
        }
        self.completed_surveillance_clients.update(surveillance_group)
        surveillance_complete = not self.surveillance_queue
        if surveillance_complete:
            self.anchor_pool.clear()

        anchors_set = set().union(*(group_anchors for _, _, group_anchors in grouped)) if grouped else set()
        trapped = surveillance_group | anchors_set | suspects | candidates
        self.phase = "suspicion" if suspects else "confirmation" if candidates else "surveillance"
        return TrapSelection(
            self.phase,
            trapped,
            anchors_set,
            suspicion_groups=grouped,
            candidate_clients=candidates,
            surveillance_clients=surveillance_group,
            surveillance_complete=surveillance_complete,
        )

    def _build_coverage_queue(self, active_clients: list[int]) -> list[tuple[int, list[int]]]:
        shuffled = active_clients[:]
        self.rng.shuffle(shuffled)
        size = self._trap_size(active_clients)
        groups = [shuffled[start : start + size] for start in range(0, len(shuffled), size)]

        if self.config.coverage_checks_per_client == 1:
            return [(0, group) for group in groups]

        first_indices = self._pair_group_indices(len(groups), shuffle=True)
        first_pass = [
            [client_id for group_index in pair for client_id in groups[group_index]]
            for pair in first_indices
        ]
        first_pairs = {
            frozenset(group_index for group_index in pair)
            for pair in first_indices
            if len(pair) == 2
        }
        second_indices = self._pair_group_indices(len(groups), shuffle=True)
        attempts = 0
        while (
            any(frozenset(pair) in first_pairs for pair in second_indices if len(pair) == 2)
            and attempts < 100
        ):
            second_indices = self._pair_group_indices(len(groups), shuffle=True)
            attempts += 1
        second_pass = [
            [client_id for group_index in pair for client_id in groups[group_index]]
            for pair in second_indices
        ]
        return [(0, clients) for clients in first_pass] + [
            (1, clients) for clients in second_pass
        ]

    def _pair_group_indices(self, count: int, *, shuffle: bool) -> list[list[int]]:
        indices = list(range(count))
        if shuffle:
            self.rng.shuffle(indices)
        return [indices[start : start + 2] for start in range(0, count, 2)]

    def _next_coverage_group(
        self, active_clients: list[int]
    ) -> tuple[int, list[int]] | None:
        active = set(active_clients)
        while self.coverage_queue:
            trap_id, queued = self.coverage_queue.pop(0)
            group = [client_id for client_id in queued if client_id in active]
            if group:
                return trap_id, group
        return None

    def _anchor_sample(
        self,
        clients: list[int],
        penalties: dict[int, int],
        times_flagged: dict[int, int],
        count: int,
    ) -> list[int]:
        grouped = sorted(
            clients,
            key=lambda client_id: (
                times_flagged.get(client_id, 0),
                penalties.get(client_id, 0),
                self.rng.random(),
            ),
        )
        return grouped[:count]

    def _trap_size(self, active_clients: list[int]) -> int:
        return max(1, math.ceil(self.config.trap_fraction * len(active_clients)))
