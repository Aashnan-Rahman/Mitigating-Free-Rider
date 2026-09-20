from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from comparison.common import DetectorOutput


@dataclass(frozen=True)
class FradInputs:
    """Server-observable inputs to the paper-guided FRAD reproduction.

    The public FRAD record names computation, communication and data quality as
    its contribution factors.  Callers must say how each quantity was obtained;
    the detector must not silently use free-rider ground truth.
    """

    computation: torch.Tensor
    communication: torch.Tensor
    data_quality: torch.Tensor
    history: torch.Tensor | None = None


class _Dagmm(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int, components: int) -> None:
        super().__init__()
        hidden = max(8, input_dim * 2)
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden), nn.Tanh(), nn.Linear(hidden, latent_dim)
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden), nn.Tanh(), nn.Linear(hidden, input_dim)
        )
        self.estimation = nn.Sequential(
            nn.Linear(latent_dim + 2, max(8, latent_dim * 2)),
            nn.Tanh(),
            nn.Linear(max(8, latent_dim * 2), components),
            nn.Softmax(dim=1),
        )

    def forward(
        self, values: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        latent = self.encoder(values)
        reconstruction = self.decoder(latent)
        relative_euclidean = (values - reconstruction).norm(dim=1, keepdim=True) / values.norm(
            dim=1, keepdim=True
        ).clamp_min(1e-12)
        cosine = nn.functional.cosine_similarity(values, reconstruction, dim=1).unsqueeze(1)
        combined = torch.cat((latent, relative_euclidean, cosine), dim=1)
        responsibilities = self.estimation(combined)
        return reconstruction, combined, responsibilities


def _mixture_parameters(
    values: torch.Tensor, responsibilities: torch.Tensor, epsilon: float
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    component_mass = responsibilities.sum(dim=0).clamp_min(epsilon)
    phi = component_mass / responsibilities.shape[0]
    means = responsibilities.transpose(0, 1) @ values / component_mass.unsqueeze(1)
    differences = values.unsqueeze(1) - means.unsqueeze(0)
    covariance = torch.einsum(
        "nk,nkd,nke->kde", responsibilities, differences, differences
    ) / component_mass[:, None, None]
    identity = torch.eye(values.shape[1], device=values.device, dtype=values.dtype)
    covariance = covariance + epsilon * identity.unsqueeze(0)
    return phi, means, covariance


def _sample_energy(
    values: torch.Tensor,
    phi: torch.Tensor,
    means: torch.Tensor,
    covariance: torch.Tensor,
) -> torch.Tensor:
    dimensions = values.shape[1]
    differences = values.unsqueeze(1) - means.unsqueeze(0)
    inverse = torch.linalg.inv(covariance)
    quadratic = torch.einsum("nkd,kde,nke->nk", differences, inverse, differences)
    log_determinant = torch.logdet(covariance)
    log_probability = (
        torch.log(phi.clamp_min(1e-12)).unsqueeze(0)
        - 0.5 * (quadratic + log_determinant.unsqueeze(0) + dimensions * torch.log(
            torch.tensor(2.0 * torch.pi, device=values.device, dtype=values.dtype)
        ))
    )
    return -torch.logsumexp(log_probability, dim=1)


def _normalize_columns(values: torch.Tensor) -> torch.Tensor:
    minimum = values.amin(dim=0, keepdim=True)
    scale = (values.amax(dim=0, keepdim=True) - minimum).clamp_min(1e-12)
    return (values - minimum) / scale


def _pagerank_from_contributions(
    contributions: torch.Tensor, damping: float, iterations: int
) -> torch.Tensor:
    """Construct a reproducible similarity graph and calculate PageRank."""
    distance = torch.cdist(contributions, contributions, p=1)
    affinity = torch.exp(-distance)
    affinity.fill_diagonal_(0.0)
    transition = affinity / affinity.sum(dim=1, keepdim=True).clamp_min(1e-12)
    count = contributions.shape[0]
    rank = torch.full(
        (count,), 1.0 / count, device=contributions.device, dtype=contributions.dtype
    )
    teleport = (1.0 - damping) / count
    for _ in range(iterations):
        rank = teleport + damping * transition.transpose(0, 1).matmul(rank)
    return rank / rank.sum().clamp_min(1e-12)


class FradDetector:
    """Paper-guided FRAD contribution/reputation/DAGMM reproduction.

    This is not author code.  The public paper metadata specifies the pipeline,
    but no public reference implementation was found.  Consequently all
    architectural and graph-construction choices are exposed and reported.
    """

    def __init__(
        self,
        *,
        epochs: int = 25,
        learning_rate: float = 1e-3,
        latent_dim: int = 3,
        components: int = 2,
        anomaly_quantile: float = 0.8,
        damping: float = 0.85,
        pagerank_iterations: int = 30,
        energy_weight: float = 0.1,
        covariance_weight: float = 0.005,
    ) -> None:
        if epochs <= 0 or latent_dim <= 0 or components <= 0:
            raise ValueError("epochs, latent_dim and components must be positive")
        if not 0.0 < anomaly_quantile < 1.0:
            raise ValueError("anomaly_quantile must be in (0, 1)")
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.latent_dim = latent_dim
        self.components = components
        self.anomaly_quantile = anomaly_quantile
        self.damping = damping
        self.pagerank_iterations = pagerank_iterations
        self.energy_weight = energy_weight
        self.covariance_weight = covariance_weight

    def detect(self, inputs: FradInputs, device: torch.device) -> DetectorOutput:
        raw = self._validate_and_stack(inputs).to(device=device, dtype=torch.float32)
        contributions = _normalize_columns(raw)
        reputation = _pagerank_from_contributions(
            contributions, self.damping, self.pagerank_iterations
        ).unsqueeze(1)
        features = torch.cat((contributions, reputation), dim=1)
        if inputs.history is not None:
            history = inputs.history.to(device=device, dtype=torch.float32)
            if history.ndim == 1:
                history = history.unsqueeze(1)
            if history.shape[0] != features.shape[0]:
                raise ValueError("FRAD history must contain one row per client")
            features = torch.cat((features, _normalize_columns(history)), dim=1)

        network = _Dagmm(features.shape[1], self.latent_dim, self.components).to(device)
        optimizer = torch.optim.Adam(network.parameters(), lr=self.learning_rate)
        network.train()
        last_loss = 0.0
        for _ in range(self.epochs):
            optimizer.zero_grad(set_to_none=True)
            reconstruction, combined, responsibilities = network(features)
            phi, means, covariance = _mixture_parameters(
                combined, responsibilities, 1e-6
            )
            energy = _sample_energy(combined, phi, means, covariance)
            diagonal_penalty = sum(
                torch.reciprocal(torch.diagonal(item).clamp_min(1e-6)).sum()
                for item in covariance
            )
            loss = (
                nn.functional.mse_loss(reconstruction, features)
                + self.energy_weight * energy.mean()
                + self.covariance_weight * diagonal_penalty
            )
            loss.backward()
            optimizer.step()
            last_loss = float(loss.detach().item())

        network.eval()
        with torch.inference_mode():
            _, combined, responsibilities = network(features)
            phi, means, covariance = _mixture_parameters(
                combined, responsibilities, 1e-6
            )
            energy = _sample_energy(combined, phi, means, covariance)
            threshold = torch.quantile(energy, self.anomaly_quantile)

        scores = {index: float(value) for index, value in enumerate(energy.cpu())}
        flags = {index: value >= float(threshold) for index, value in scores.items()}
        return DetectorOutput(
            scores,
            flags,
            {
                "method": "frad_paper_guided_reimplementation",
                "official_code": False,
                "epochs": self.epochs,
                "components": self.components,
                "latent_dim": self.latent_dim,
                "anomaly_quantile": self.anomaly_quantile,
                "threshold": float(threshold),
                "training_loss": last_loss,
                "feature_columns": [
                    "computation",
                    "communication",
                    "data_quality",
                    "pagerank_reputation",
                ],
                "paper": "https://doi.org/10.1109/JIOT.2023.3298606",
            },
        )

    @staticmethod
    def _validate_and_stack(inputs: FradInputs) -> torch.Tensor:
        columns = (inputs.computation, inputs.communication, inputs.data_quality)
        if any(column.ndim != 1 for column in columns):
            raise ValueError("FRAD contribution inputs must be one-dimensional")
        lengths = {int(column.numel()) for column in columns}
        if len(lengths) != 1 or not lengths or next(iter(lengths)) < 2:
            raise ValueError("FRAD inputs must contain the same number of clients (at least two)")
        values = torch.stack(columns, dim=1)
        if not torch.isfinite(values).all():
            raise ValueError("FRAD inputs must be finite")
        return values
