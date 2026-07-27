from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from config import ExperimentConfig


class RunLogger:
    def __init__(self, config: ExperimentConfig, run_name: str) -> None:
        self.config = config
        self.run_name = run_name
        self.run_dir = Path(config.output_dir) / run_name
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.trap_rows: list[dict[str, Any]] = []
        self.global_rows: list[dict[str, Any]] = []
        self.client_rows: list[dict[str, Any]] = []
        self.penalty_rows: list[dict[str, Any]] = []
        self.removal_rows: list[dict[str, Any]] = []
        self.summary_rows: list[dict[str, Any]] = []
        self.threshold_rows: list[dict[str, Any]] = []

    def log_trap_matrix_row(
        self, round_idx: int, phase: str, trapped: set[int], num_clients: int
    ) -> None:
        row: dict[str, Any] = {"round": round_idx, "phase": phase}
        row.update({str(client_id): int(client_id in trapped) for client_id in range(num_clients)})
        self.trap_rows.append(row)

    def write_all(self, run_config: dict[str, Any]) -> None:
        self._write_csv("trap_matrix.csv", self.trap_rows)
        self._write_csv("global_metrics.csv", self.global_rows)
        self._write_csv("client_metrics.csv", self.client_rows)
        self._write_csv("penalty_tracker.csv", self.penalty_rows)
        self._write_csv("removals.csv", self.removal_rows)
        self._write_csv("detection_summary.csv", self.summary_rows)
        self._write_csv("thresholds.csv", self.threshold_rows)
        with (self.run_dir / "run_config.json").open("w", encoding="utf-8") as handle:
            json.dump(run_config, handle, indent=2, sort_keys=True)

    def _write_csv(self, filename: str, rows: list[dict[str, Any]]) -> None:
        path = self.run_dir / filename
        if rows:
            fieldnames = []
            for row in rows:
                for key in row:
                    if key not in fieldnames:
                        fieldnames.append(key)
        else:
            fieldnames = CSV_HEADERS.get(filename, [])
        with path.open("w", newline="", encoding="utf-8") as handle:
            if not fieldnames:
                return
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            if rows:
                writer.writerows(rows)


CSV_HEADERS: dict[str, list[str]] = {
    "removals.csv": ["round", "client_id", "is_free_rider", "final_penalty"],
    "detection_summary.csv": [
        "removed_free_riders",
        "removed_honest_clients",
        "missed_free_riders",
        "precision",
        "recall",
        "f1",
        "false_positive_removal_rate",
    ],
}
