from __future__ import annotations

import csv

import logging_utils
from config import ExperimentConfig
from logging_utils import RunLogger


def test_metric_matrix_is_published_by_atomic_replace(tmp_path, monkeypatch) -> None:
    config = ExperimentConfig(output_dir=str(tmp_path), num_clients=2)
    logger = RunLogger(config, "atomic-matrix")
    logger.client_rows = [
        {
            "round": 1,
            "client_id": 0,
            "detection_observation_round": 1,
            "delta_norm": 1.25,
        },
        {
            "round": 1,
            "client_id": 1,
            "detection_observation_round": 1,
            "delta_norm": 2.5,
        },
    ]
    replacements: list[tuple[str, str]] = []
    real_replace = logging_utils.replace_with_retry

    def record_replace(source, destination) -> None:
        replacements.append((source.name, destination.name))
        real_replace(source, destination)

    monkeypatch.setattr(logging_utils, "replace_with_retry", record_replace)

    logger._write_metric_matrix("delta_norm_matrix.csv", "delta_norm")

    assert replacements == [
        (f".delta_norm_matrix.csv.{__import__('os').getpid()}.tmp", "delta_norm_matrix.csv")
    ]
    with (logger.run_dir / "delta_norm_matrix.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == [
            {"round": "1", "client_0": "1.25", "client_1": "2.5"}
        ]
    assert not list(logger.run_dir.glob("*.tmp"))
