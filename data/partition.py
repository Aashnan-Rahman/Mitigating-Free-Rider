from __future__ import annotations

import numpy as np

from config import ExperimentConfig


def _targets(dataset) -> np.ndarray:
    targets = getattr(dataset, "targets", None)
    if targets is None:
        targets = getattr(dataset, "labels", None)
    if targets is None:
        raise ValueError("Dataset must expose targets or labels for partitioning.")
    return np.asarray(targets)


def partition_dataset(dataset, config: ExperimentConfig) -> list[list[int]]:
    if config.distribution == "iid":
        return iid_partition(len(dataset), config.num_clients, config.seed)
    if config.distribution == "noniid":
        return dirichlet_partition(dataset, config)
    raise ValueError(f"Unsupported distribution: {config.distribution}")


def iid_partition(dataset_size: int, num_clients: int, seed: int) -> list[list[int]]:
    rng = np.random.default_rng(seed)
    indices = np.arange(dataset_size)
    rng.shuffle(indices)
    return [chunk.astype(int).tolist() for chunk in np.array_split(indices, num_clients)]


def dirichlet_partition(dataset, config: ExperimentConfig) -> list[list[int]]:
    labels = _targets(dataset)
    classes = np.unique(labels)
    rng = np.random.default_rng(config.seed)

    for _ in range(config.max_partition_attempts):
        client_indices: list[list[int]] = [[] for _ in range(config.num_clients)]
        for cls in classes:
            cls_indices = np.where(labels == cls)[0]
            rng.shuffle(cls_indices)
            proportions = rng.dirichlet(
                np.repeat(config.dirichlet_alpha, config.num_clients)
            )
            cuts = (np.cumsum(proportions) * len(cls_indices)).astype(int)[:-1]
            for client_id, split in enumerate(np.split(cls_indices, cuts)):
                client_indices[client_id].extend(split.astype(int).tolist())

        if min(len(indices) for indices in client_indices) >= config.min_partition_size:
            for indices in client_indices:
                rng.shuffle(indices)
            return client_indices

    raise RuntimeError(
        "Could not create a non-empty Dirichlet partition. "
        "Try increasing dirichlet_alpha or lowering num_clients."
    )
