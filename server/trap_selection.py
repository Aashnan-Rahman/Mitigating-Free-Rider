from __future__ import annotations

import math
import random
from dataclasses import dataclass

from config import ExperimentConfig


@dataclass
class TrapSelection:
    phase: str
    trapped_clients: set[int]
    anchors: set[int]
    checked_clients: set[int]


class TrapSelector:
    def __init__(self, config: ExperimentConfig, rng: random.Random) -> None:
        self.config = config
        self.rng = rng
        self.phase = "warmup"
        self.coverage_queue: list[list[int]] = []
        self.suspicion_window_rounds = 0
        self.suspicion_window_flags = 0
        self.quiet_windows = 0
        self.suspect_queue: list[int] = []
        self.clean_queue: list[int] = []
        self.next_suspicion_round_flagged = True

    def select(
        self,
        round_idx: int,
        active_clients: list[int],
        penalties: dict[int, int],
        times_flagged: dict[int, int],
    ) -> TrapSelection:
        if round_idx <= self.config.warmup_rounds or not active_clients:
            self.phase = "warmup"
            return TrapSelection("warmup", set(), set(), set())

        if self.phase == "warmup":
            self.start_coverage(active_clients)

        if self.phase == "coverage":
            group = self._next_coverage_group(active_clients)
            if group:
                clients = set(group)
                return TrapSelection("coverage", clients, set(), clients)
            self.phase = "suspicion"

        phase, trapped, anchors, checked = self._select_suspicion(
            active_clients, penalties, times_flagged
        )
        return TrapSelection(phase, trapped, anchors, checked)

    def start_coverage(self, active_clients: list[int]) -> None:
        self.phase = "coverage"
        self.coverage_queue = self._build_coverage_queue(active_clients)
        self.suspicion_window_rounds = 0
        self.suspicion_window_flags = 0
        self.quiet_windows = 0
        self.suspect_queue = []
        self.clean_queue = []
        self.next_suspicion_round_flagged = True

    def observe_round(self, phase: str, new_flags: int, active_clients: list[int]) -> None:
        if not phase.startswith("suspicion"):
            return
        self.suspicion_window_rounds += 1
        self.suspicion_window_flags += new_flags
        if self.suspicion_window_rounds < self.config.reset_window_size:
            return

        if self.suspicion_window_flags <= self.config.reset_flag_threshold:
            self.quiet_windows += 1
        else:
            self.quiet_windows = 0
        self.suspicion_window_rounds = 0
        self.suspicion_window_flags = 0

        if self.quiet_windows >= self.config.reset_window_count:
            self.start_coverage(active_clients)

    def _build_coverage_queue(self, active_clients: list[int]) -> list[list[int]]:
        shuffled = active_clients[:]
        self.rng.shuffle(shuffled)
        size = self._trap_size(active_clients)
        return [shuffled[start : start + size] for start in range(0, len(shuffled), size)]

    def _next_coverage_group(self, active_clients: list[int]) -> list[int]:
        active = set(active_clients)
        while self.coverage_queue:
            group = [client_id for client_id in self.coverage_queue.pop(0) if client_id in active]
            if group:
                return group
        return []

    def _select_suspicion(
        self,
        active_clients: list[int],
        penalties: dict[int, int],
        times_flagged: dict[int, int],
    ) -> tuple[str, set[int], set[int], set[int]]:
        flagged_clients = [
            client_id
            for client_id in active_clients
            if penalties.get(client_id, 0) > 0 or times_flagged.get(client_id, 0) > 0
        ]
        clean_clients = [
            client_id
            for client_id in active_clients
            if penalties.get(client_id, 0) == 0 and times_flagged.get(client_id, 0) == 0
        ]

        use_flagged = self.next_suspicion_round_flagged
        if use_flagged and not flagged_clients:
            use_flagged = False
        elif not use_flagged and not clean_clients:
            use_flagged = True
        self.next_suspicion_round_flagged = not self.next_suspicion_round_flagged

        if use_flagged:
            return self._select_flagged_suspicion(
                active_clients, flagged_clients, penalties, times_flagged
            )
        return self._select_clean_suspicion(active_clients, clean_clients)

    def _select_flagged_suspicion(
        self,
        active_clients: list[int],
        flagged_clients: list[int],
        penalties: dict[int, int],
        times_flagged: dict[int, int],
    ) -> tuple[str, set[int], set[int], set[int]]:
        size = self._trap_size(active_clients)
        anchor_count_target = min(self.config.num_anchors, size)
        suspect_count = max(1, size - anchor_count_target)
        suspects = self._next_suspects(flagged_clients, penalties, times_flagged, suspect_count)
        remaining = [client_id for client_id in active_clients if client_id not in suspects]
        anchor_count = min(self.config.num_anchors, size - len(suspects), len(remaining))
        anchors = self._anchor_sample(remaining, penalties, times_flagged, anchor_count)
        trapped = set(suspects) | set(anchors)

        if len(trapped) < size:
            fill_from = [client_id for client_id in active_clients if client_id not in trapped]
            self.rng.shuffle(fill_from)
            trapped.update(fill_from[: size - len(trapped)])
        return "suspicion_flagged", trapped, set(anchors), set(suspects)

    def _select_clean_suspicion(
        self, active_clients: list[int], clean_clients: list[int]
    ) -> tuple[str, set[int], set[int], set[int]]:
        size = self._trap_size(active_clients)
        clean_group = self._next_clean_group(clean_clients, size)
        trapped = set(clean_group)
        if len(trapped) < size:
            fill_from = [client_id for client_id in active_clients if client_id not in trapped]
            self.rng.shuffle(fill_from)
            trapped.update(fill_from[: size - len(trapped)])
        return "suspicion_clean", trapped, set(), trapped

    def _next_suspects(
        self,
        flagged_clients: list[int],
        penalties: dict[int, int],
        times_flagged: dict[int, int],
        count: int,
    ) -> list[int]:
        flagged = set(flagged_clients)
        self.suspect_queue = [client_id for client_id in self.suspect_queue if client_id in flagged]
        if not self.suspect_queue:
            self.suspect_queue = sorted(
                flagged_clients,
                key=lambda client_id: (
                    -penalties.get(client_id, 0),
                    -times_flagged.get(client_id, 0),
                    self.rng.random(),
                ),
            )
        selected: list[int] = []
        while self.suspect_queue and len(selected) < count:
            selected.append(self.suspect_queue.pop(0))
        return selected

    def _next_clean_group(self, clean_clients: list[int], count: int) -> list[int]:
        clean = set(clean_clients)
        self.clean_queue = [client_id for client_id in self.clean_queue if client_id in clean]
        if not self.clean_queue:
            self.clean_queue = clean_clients[:]
            self.rng.shuffle(self.clean_queue)
        selected: list[int] = []
        while self.clean_queue and len(selected) < count:
            selected.append(self.clean_queue.pop(0))
        return selected

    def _weighted_sample(
        self, clients: list[int], penalties: dict[int, int], count: int
    ) -> list[int]:
        pool = clients[:]
        selected: list[int] = []
        for _ in range(min(count, len(pool))):
            weights = [penalties.get(client_id, 0) + self.config.epsilon for client_id in pool]
            total = sum(weights)
            pick = self.rng.random() * total
            cursor = 0.0
            chosen_index = 0
            for idx, weight in enumerate(weights):
                cursor += weight
                if cursor >= pick:
                    chosen_index = idx
                    break
            selected.append(pool.pop(chosen_index))
        return selected

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
