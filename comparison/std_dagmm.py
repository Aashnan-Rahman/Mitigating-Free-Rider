"""Paper-guided full-update STD-DAGMM for COMPUTATIONAL pilots, not author code.

Lin et al., https://arxiv.org/pdf/1911.12560 : latent reconstruction plus
relative L2, cosine and input STD; joint reconstruction/energy/covariance loss.
FRIDA https://arxiv.org/html/2410.05020v2 : widths 128,64,32, K=3,
energy weight .1, covariance weight .005. Symmetric decoder, estimation width
10, dropout .5, Adam rate .001 and epoch budget are explicit reproduction
choices, NOT verified original training settings. No threshold or class labels.
"""
from __future__ import annotations

import math

import torch
from torch import nn


class StdDagmm(nn.Module):
    def __init__(self, input_dim, widths=(128, 64, 32), components=3, ridge=1e-6):
        super().__init__()
        if input_dim < 1 or not widths or min(widths) < 1 or components < 1 or ridge <= 0:
            raise ValueError('Dimensions and covariance ridge must be positive')
        self.ridge = ridge
        def network(sizes):
            layers = []
            for i, (left, right) in enumerate(zip(sizes, sizes[1:])):
                layers.append(nn.Linear(left, right))
                if i < len(sizes)-2:
                    layers.append(nn.Tanh())
            return nn.Sequential(*layers)
        self.encoder = network((input_dim, *widths))
        self.decoder = network((*reversed(widths), input_dim))
        dimensions = widths[-1] + 3
        self.estimation = nn.Sequential(nn.Linear(dimensions, 10), nn.Tanh(),
            nn.Dropout(.5), nn.Linear(10, components), nn.Softmax(dim=1))

    def forward(self, x):
        latent = self.encoder(x)
        reconstruction = self.decoder(latent)
        relative = (x-reconstruction).norm(dim=1) / x.norm(dim=1).clamp_min(1e-12)
        cosine = nn.functional.cosine_similarity(x, reconstruction, dim=1, eps=1e-12)
        std = x.std(dim=1, correction=0)
        z = torch.cat((latent, relative[:, None], cosine[:, None], std[:, None]), dim=1)
        return reconstruction, z, self.estimation(z)

    def mixture(self, z, gamma):
        # Small covariance computations use float64, not a larger full-vector AE.
        # The ridge handles rank-deficient mini-batches; it is numerical, not a cutoff.
        z, gamma = z.double(), gamma.double()
        mass = gamma.sum(0).clamp_min(1e-12)
        phi = mass/mass.sum()
        mu = gamma.T @ z / mass[:, None]
        difference = z[:, None, :] - mu[None, :, :]
        covariance = torch.einsum('nk,nkd,nke->kde', gamma, difference, difference) / mass[:, None, None]
        covariance = (covariance + covariance.transpose(-1, -2))/2
        covariance = covariance + self.ridge*torch.eye(z.shape[1], dtype=z.dtype, device=z.device)
        return phi, mu, covariance

    @staticmethod
    def energy(z, mixture):
        phi, mu, covariance = mixture
        z = z.double()
        cholesky = torch.linalg.cholesky(covariance)
        difference = (z[:, None, :] - mu[None, :, :]).permute(1, 2, 0)
        whitened = torch.linalg.solve_triangular(cholesky, difference, upper=False)
        quadratic = whitened.square().sum(1).T
        logdet = 2*cholesky.diagonal(dim1=-2, dim2=-1).log().sum(1)
        logp = phi.log()[None, :] - .5*(quadratic + logdet[None, :] + z.shape[1]*math.log(2*math.pi))
        return -torch.logsumexp(logp, dim=1)

    def objective(self, x, reconstruction, z, gamma):
        mixture = self.mixture(z, gamma)
        energy = self.energy(z, mixture)
        penalty = mixture[2].diagonal(dim1=-2, dim2=-1).reciprocal().sum()
        loss = nn.functional.mse_loss(reconstruction, x) + .1*energy.mean() + .005*penalty
        return loss, energy
