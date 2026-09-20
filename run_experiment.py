from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from config import ExperimentConfig
from experiment_runner import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SWT-CP free-rider FL simulation.")
    parser.add_argument("--config", type=Path, help="Path to a JSON config override file.")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a config field. Values are parsed as JSON when possible.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a tiny configuration for quick syntax/data-flow validation.",
    )
    args = parser.parse_args()

    values: dict[str, Any] = {}
    if args.config:
        values.update(json.loads(args.config.read_text(encoding="utf-8")))
    for item in args.set:
        key, value = parse_assignment(item)
        values[key] = value
    if args.smoke:
        values.update(
            {
                "num_clients": 4,
                "num_rounds": 2,
                "warmup_rounds": 1,
                "local_epochs": 1,
                "batch_size": 16,
                "trap_fraction": 0.5,
                "run_name": values.get("run_name", "smoke"),
            }
        )

    config = ExperimentConfig.from_dict(values)
    run_dir = run_experiment(config)
    print(f"Run complete. Outputs written to: {run_dir}")


def parse_assignment(item: str) -> tuple[str, Any]:
    if "=" not in item:
        raise ValueError(f"Expected KEY=VALUE, got {item!r}")
    key, raw = item.split("=", 1)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    return key, value


if __name__ == "__main__":
    main()
