from __future__ import annotations

from collections.abc import Mapping

import torch
from torch import nn
from torch.utils.data import DataLoader

from comparison.common import DetectorOutput, upper_z_flags

StateDict = Mapping[str, torch.Tensor]


class FridaLossDetector:
    """FRIDA's loss-based membership-inference detector.

    This implements Algorithm 1 of Recasens et al., arXiv:2410.05020v2:
    evaluate every returned client model on the shared canary set and flag high
    canary-loss outliers with a z-test.  Honest-client training on the canaries
    is a protocol requirement and is intentionally not hidden inside this
    server-side detector.
    """

    def __init__(self, z_threshold: float = 2.0) -> None:
        if z_threshold <= 0:
            raise ValueError("z_threshold must be positive")
        self.z_threshold = z_threshold

    @torch.inference_mode()
    def detect(
        self,
        model: nn.Module,
        client_states: Mapping[int, StateDict],
        canary_loader: DataLoader,
        device: torch.device,
    ) -> DetectorOutput:
        if not client_states:
            return DetectorOutput({}, {}, {"z_scores": {}})

        original_state = {
            key: value.detach().clone() for key, value in model.state_dict().items()
        }
        was_training = model.training
        loss_fn = nn.CrossEntropyLoss(reduction="sum")
        scores: dict[int, float] = {}
        try:
            model.eval()
            for client_id, state in client_states.items():
                model.load_state_dict(state)
                total_loss = 0.0
                total_samples = 0
                for inputs, targets in canary_loader:
                    inputs = inputs.to(device, non_blocking=True)
                    targets = targets.to(device, non_blocking=True)
                    total_loss += float(loss_fn(model(inputs), targets).item())
                    total_samples += int(targets.numel())
                if total_samples == 0:
                    raise ValueError("The FRIDA canary loader is empty")
                scores[int(client_id)] = total_loss / total_samples
        finally:
            model.load_state_dict(original_state)
            model.train(was_training)

        flags, z_scores = upper_z_flags(scores, self.z_threshold)
        return DetectorOutput(
            scores,
            flags,
            {
                "method": "frida_loss_mia",
                "z_threshold": self.z_threshold,
                "z_scores": z_scores,
                "canary_samples": len(canary_loader.dataset),
                "paper": "https://arxiv.org/abs/2410.05020",
            },
        )
