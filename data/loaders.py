from __future__ import annotations

from pathlib import Path

from torch.utils.data import DataLoader

from config import ExperimentConfig


def get_datasets(config: ExperimentConfig):
    from torchvision import datasets, transforms

    root = Path(config.data_dir)
    dataset = config.dataset.lower()
    if dataset == "mnist":
        transform = transforms.Compose(
            [transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))]
        )
        train_set = datasets.MNIST(
            root=root, train=True, download=config.download_data, transform=transform
        )
        test_set = datasets.MNIST(
            root=root, train=False, download=config.download_data, transform=transform
        )
        return train_set, test_set
    if dataset == "cifar10":
        transform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(
                    (0.4914, 0.4822, 0.4465),
                    (0.2470, 0.2435, 0.2616),
                ),
            ]
        )
        train_set = datasets.CIFAR10(
            root=root, train=True, download=config.download_data, transform=transform
        )
        test_set = datasets.CIFAR10(
            root=root, train=False, download=config.download_data, transform=transform
        )
        return train_set, test_set
    raise ValueError(f"Unsupported dataset: {config.dataset}")


def make_eval_loader(config: ExperimentConfig, dataset) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=config.global_eval_batch_size,
        shuffle=False,
        num_workers=config.num_workers,
        pin_memory=config.pin_memory,
    )
