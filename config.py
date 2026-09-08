from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ExperimentConfig:
    dataset: str = "mnist"
    distribution: str = "iid"
    dirichlet_alpha: float = 0.5
    num_clients: int = 100
    num_rounds: int = 100
    free_rider_pct: float = 0.10
    attack_type: str = "FR1"
    local_epochs: int = 3
    batch_size: int = 32
    optimizer: str = "sgd"
    learning_rate: float = 0.01
    momentum: float = 0.9
    warmup_rounds: int = 10
    trap_fraction: float = 0.10
    num_anchors: int = 3
    epsilon: float = 1.0
    similarity_threshold: float = 0.5
    penalty_zero_update: int = 4
    penalty_trap_flag: int = 2
    penalty_normal_flag: int = 1
    removal_threshold_pct: float = 0.10
    reset_flag_threshold: int = 1
    reset_window_size: int = 10
    reset_window_count: int = 2
    zero_update_epsilon: float = 1e-6
    use_batch_mad_threshold: bool = True
    mad_threshold_k: float = 3.0
    mad_floor: float = 0.05
    magnitude_z_threshold: float = 3.0
    use_loss_check: bool = False
    loss_check_rounds: int = 6
    loss_percentile: float = 75.0
    loss_requires_small_norm: bool = True
    full_participation: bool = True
    seed: int = 42
    output_dir: str = "./results/"
    run_name: str | None = None
    device: str = "auto"

    data_dir: str = "./data_cache/"
    download_data: bool = True
    num_workers: int = 0
    pin_memory: bool = True
    local_eval_batches: int = 1
    global_eval_batch_size: int = 256
    fr3_window: int = 5
    fr4_history_size: int = 5
    fr4_noise_fraction: float = 0.1
    trap_noise_scale: float = 0.01
    trap_noise_floor: float = 1e-4
    min_partition_size: int = 1
    max_partition_attempts: int = 50
    penalty_decay: int = 1
    save_checkpoints: bool = True
    checkpoint_every: int = 1

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ExperimentConfig":
        known = set(cls.__dataclass_fields__)
        unknown = sorted(set(values) - known)
        if unknown:
            raise ValueError(f"Unknown config field(s): {', '.join(unknown)}")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def removal_threshold(self) -> int:
        import math

        return math.ceil(self.removal_threshold_pct * self.num_rounds)

    def resolved_run_name(self) -> str:
        if self.run_name:
            return self.run_name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pct = int(round(self.free_rider_pct * 100))
        return (
            f"{self.dataset}_{self.distribution}_{self.attack_type}"
            f"_fr{pct}_{timestamp}"
        )

    def run_dir(self) -> Path:
        return Path(self.output_dir) / self.resolved_run_name()

    def validate(self) -> None:
        choices = {
            "dataset": {"mnist", "cifar10"},
            "distribution": {"iid", "noniid"},
            "attack_type": {"FR1", "FR2", "FR3", "FR4"},
            "optimizer": {"sgd", "adam"},
            "device": {"auto", "cpu", "cuda"},
        }
        for field, allowed in choices.items():
            value = getattr(self, field)
            if value not in allowed:
                raise ValueError(f"{field} must be one of {sorted(allowed)}, got {value!r}")
        if not self.full_participation:
            raise ValueError("This simulator currently implements full_participation=True only.")
        if self.num_clients <= 0 or self.num_rounds <= 0:
            raise ValueError("num_clients and num_rounds must be positive.")
        if not 0.0 <= self.free_rider_pct <= 1.0:
            raise ValueError("free_rider_pct must be between 0 and 1.")
        if not 0.0 < self.trap_fraction <= 1.0:
            raise ValueError("trap_fraction must be in (0, 1].")
        if self.num_anchors < 0:
            raise ValueError("num_anchors must be non-negative.")
        if self.penalty_decay < 0:
            raise ValueError("penalty_decay must be non-negative.")
        if self.mad_threshold_k <= 0 or self.mad_floor < 0:
            raise ValueError("mad_threshold_k must be positive and mad_floor non-negative.")
        if self.loss_check_rounds < 0 or not 0.0 < self.loss_percentile < 100.0:
            raise ValueError("loss_check_rounds must be non-negative and loss_percentile must be in (0, 100).")
        if self.checkpoint_every <= 0:
            raise ValueError("checkpoint_every must be positive.")
