from __future__ import annotations

from typing import Callable

from config import ExperimentConfig


def run_experiment(
    config: ExperimentConfig,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> str:
    if config.methodology_version in {"frida_loss", "frad_reproduction"}:
        from baseline_train import run_baseline_experiment

        return run_baseline_experiment(config, progress_callback)

    from train import run_experiment as run_swtcp_experiment

    return run_swtcp_experiment(config, progress_callback)
