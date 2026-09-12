from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ExperimentConfig:
    methodology_version: str = "swtcp_v6"
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
    coverage_checks_per_client: int = 2
    candidate_confirmation_flags: int = 2
    suspicion_target_group_size: int = 10
    anchors_per_suspicion_group: int = 3
    max_suspicion_anchors: int = 10
    surveillance_groups: int = 10
    penalty_zero_update: int = 5
    penalty_trap_flag: int = 2
    penalty_normal_flag: int = 1
    penalty_suspicion_flag: int = 3
    removal_threshold_points: int = 15
    dodge_min_probes: int = 10
    dodge_max_flag_rate: float = 0.10
    zero_update_epsilon: float = 1e-6
    magnitude_z_threshold: float = 3.0
    mad_floor: float = 0.05
    full_participation: bool = True
    seed: int = 42
    output_dir: str = "./results/"
    run_name: str | None = None
    resume_checkpoint: str | None = None
    device: str = "auto"

    data_dir: str = "./data_cache/"
    download_data: bool = True
    num_workers: int = 0
    pin_memory: bool = True
    local_eval_batches: int = 1
    global_eval_batch_size: int = 256
    fr2_update_range: float = 1e-3
    fr3_window: int = 5
    fr4_history_size: int = 5
    fr4_noise_fraction: float = 0.1
    fr4_cold_start_scale: float = 1e-4
    trap_noise_scale: float = 0.01
    trap_noise_floor: float = 1e-4
    min_partition_size: int = 1
    max_partition_attempts: int = 50
    save_checkpoints: bool = True
    checkpoint_keep_last: int = 5

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ExperimentConfig":
        values = dict(values)
        legacy_interval = values.pop("checkpoint_every", 1)
        if legacy_interval != 1:
            raise ValueError(
                "checkpoint_every is no longer configurable: checkpoints are saved "
                "every round; use checkpoint_keep_last to control storage."
            )
        known = set(cls.__dataclass_fields__)
        unknown = sorted(set(values) - known)
        if unknown:
            raise ValueError(f"Unknown config field(s): {', '.join(unknown)}")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def removal_threshold(self) -> int:
        return self.removal_threshold_points

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
        if self.coverage_checks_per_client not in {1, 2}:
            raise ValueError("coverage_checks_per_client must be 1 or 2.")
        if self.candidate_confirmation_flags < 2:
            raise ValueError("candidate_confirmation_flags must be at least 2.")
        if (
            self.suspicion_target_group_size <= 0
            or self.anchors_per_suspicion_group <= 0
            or self.max_suspicion_anchors <= 0
            or self.surveillance_groups <= 0
        ):
            raise ValueError("Suspicion and surveillance group settings must be positive.")
        if self.removal_threshold_points <= 0 or any(
            penalty <= 0
            for penalty in (
                self.penalty_zero_update,
                self.penalty_trap_flag,
                self.penalty_normal_flag,
                self.penalty_suspicion_flag,
            )
        ):
            raise ValueError("Suspicion penalties and removal threshold must be positive.")
        if self.dodge_min_probes <= 0 or not 0.0 <= self.dodge_max_flag_rate <= 1.0:
            raise ValueError("Dodge-index settings are invalid.")
        if (
            self.zero_update_epsilon <= 0
            or self.magnitude_z_threshold <= 0
            or self.mad_floor <= 0
        ):
            raise ValueError("Zero epsilon, magnitude z threshold, and MAD floor must be positive.")
        if self.checkpoint_keep_last <= 0:
            raise ValueError("checkpoint_keep_last must be positive.")
        if self.fr2_update_range <= 0:
            raise ValueError("fr2_update_range must be positive.")
        if self.fr3_window <= 0 or self.fr4_history_size <= 0:
            raise ValueError("Attack history windows must be positive.")
        if self.fr4_noise_fraction < 0 or self.fr4_cold_start_scale <= 0:
            raise ValueError("FR4 noise settings are invalid.")
