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
        self.trap_assignment_rows: list[dict[str, Any]] = []
        self.global_rows: list[dict[str, Any]] = []
        self.client_rows: list[dict[str, Any]] = []
        self.penalty_rows: list[dict[str, Any]] = []
        self.removal_rows: list[dict[str, Any]] = []
        self.rehabilitation_rows: list[dict[str, Any]] = []
        self.dodge_rows: list[dict[str, Any]] = []
        self.summary_rows: list[dict[str, Any]] = []
        self.detection_round_rows: list[dict[str, Any]] = []
        self.detection_event_rows: list[dict[str, Any]] = []
        self.client_summary_rows: list[dict[str, Any]] = []

    def log_trap_matrix_row(
        self, round_idx: int, phase: str, trapped: set[int], num_clients: int
    ) -> None:
        row: dict[str, Any] = {"round": round_idx, "phase": phase}
        row.update({str(client_id): int(client_id in trapped) for client_id in range(num_clients)})
        self.trap_rows.append(row)

    def write_all(self, run_config: dict[str, Any]) -> None:
        self._write_csv("trap_matrix.csv", self.trap_rows)
        self._write_csv("trap_assignments.csv", self.trap_assignment_rows)
        self._write_csv("global_metrics.csv", self.global_rows)
        self._write_csv("client_metrics.csv", self.client_rows)
        self._write_csv("penalty_tracker.csv", self.penalty_rows)
        self._write_csv("removals.csv", self.removal_rows)
        self._write_csv("rehabilitations.csv", self.rehabilitation_rows)
        self._write_csv("dodge_tracker.csv", self.dodge_rows)
        self._write_csv("detection_summary.csv", self.summary_rows)
        self._write_csv("round_detection_metrics.csv", self.detection_round_rows)
        self._write_csv("detection_events.csv", self.detection_event_rows)
        self._write_csv("client_detection_summary.csv", self.client_summary_rows)
        self._write_metric_matrix("norm_z_matrix.csv", "norm_z_score")
        self._write_metric_matrix("loss_z_matrix.csv", "loss_z_score")
        self._write_metric_matrix("delta_norm_matrix.csv", "delta_norm")
        self._write_metric_matrix("flag_matrix.csv", "flagged")
        with (self.run_dir / "run_config.json").open("w", encoding="utf-8") as handle:
            json.dump(run_config, handle, indent=2, sort_keys=True)

    def write_progress(self, round_idx: int, run_config: dict[str, Any]) -> None:
        self.write_all({**run_config, "latest_round": round_idx})
        latest = {
            "run_name": self.run_name,
            "latest_round": round_idx,
            "latest_global_metrics": self.global_rows[-1] if self.global_rows else {},
            "files": sorted(path.name for path in self.run_dir.iterdir()),
        }
        with (self.run_dir / "latest_results.json").open("w", encoding="utf-8") as handle:
            json.dump(latest, handle, indent=2, sort_keys=True)

    def load_existing(
        self,
        completed_round: int,
        checkpoint_global_metrics: dict[str, Any] | None = None,
    ) -> None:
        """Restore round logs when continuing a checkpointed run."""
        loaders = (
            ("trap_matrix.csv", "trap_rows"),
            ("trap_assignments.csv", "trap_assignment_rows"),
            ("global_metrics.csv", "global_rows"),
            ("client_metrics.csv", "client_rows"),
            ("penalty_tracker.csv", "penalty_rows"),
            ("removals.csv", "removal_rows"),
            ("rehabilitations.csv", "rehabilitation_rows"),
            ("dodge_tracker.csv", "dodge_rows"),
            ("round_detection_metrics.csv", "detection_round_rows"),
            ("detection_events.csv", "detection_event_rows"),
        )
        for filename, attribute in loaders:
            path = self.run_dir / filename
            if not path.exists():
                continue
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            restored = [_coerce_row(row) for row in rows]
            if attribute != "removal_rows":
                restored = [
                    row for row in restored
                    if row.get("round", completed_round) in ("", None)
                    or int(row.get("round", completed_round)) <= completed_round
                ]
            setattr(self, attribute, restored)
        if checkpoint_global_metrics is not None and not any(
            int(row.get("round", -1)) == completed_round for row in self.global_rows
        ):
            self.global_rows.append(dict(checkpoint_global_metrics))

    def _write_csv(self, filename: str, rows: list[dict[str, Any]]) -> None:
        path = self.run_dir / filename
        fieldnames = list(rows[0].keys()) if rows else CSV_HEADERS.get(filename, [])
        with path.open("w", newline="", encoding="utf-8") as handle:
            if not fieldnames:
                return
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            if rows:
                writer.writerows(rows)

    def _write_metric_matrix(self, filename: str, value_field: str) -> None:
        """Pivot a client metric to one row per observation round."""
        by_round: dict[int, dict[str, Any]] = {}
        for row in self.client_rows:
            value = row.get(value_field, "")
            if value == "" or value is None:
                continue
            observation_round = row.get("detection_observation_round", "")
            matrix_round = int(observation_round) if observation_round != "" else int(row["round"])
            matrix_row = by_round.setdefault(matrix_round, {"round": matrix_round})
            matrix_row[f"client_{int(row['client_id'])}"] = value
        fieldnames = ["round"] + [
            f"client_{client_id}" for client_id in range(self.config.num_clients)
        ]
        path = self.run_dir / filename
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for matrix_round in sorted(by_round):
                writer.writerow(by_round[matrix_round])


def _coerce_row(row: dict[str, str]) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    for key, value in row.items():
        if value == "":
            converted[key] = ""
            continue
        try:
            converted[key] = int(value)
            continue
        except ValueError:
            pass
        try:
            converted[key] = float(value)
        except ValueError:
            converted[key] = value
    return converted

CSV_HEADERS: dict[str, list[str]] = {
    "trap_assignments.csv": ["round", "client_id", "phase", "role", "group_id"],
    "removals.csv": ["round", "client_id", "is_free_rider", "final_penalty"],
    "rehabilitations.csv": [
        "round", "client_id", "is_free_rider", "penalty", "probes", "flags", "dodge_index"
    ],
    "dodge_tracker.csv": [
        "round", "client_id", "is_suspected", "episode_probes", "episode_flags",
        "dodge_index", "lifetime_trap_flags"
    ],
    "detection_summary.csv": [
        "removed_free_riders",
        "removed_honest_clients",
        "missed_free_riders",
        "precision",
        "recall",
        "f1",
        "detection_accuracy",
        "false_positive_removal_rate",
    ],
    "round_detection_metrics.csv": [
        "round", "evaluated_clients", "true_positives", "false_positives",
        "true_negatives", "false_negatives", "detection_accuracy", "precision",
        "recall", "f1", "false_positive_rate", "false_negative_rate",
        "specificity", "new_removals", "new_rehabilitations", "num_suspected",
    ],
}
