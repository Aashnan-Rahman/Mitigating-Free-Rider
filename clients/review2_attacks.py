"""Paper-guided attacks using only each client's received-model history.

Fraboni et al., AISTATS 2021, section 3.2: received + sigma*t^-gamma*Z;
sigma estimated once from first received-model difference, gamma=1.
Zhu et al., NFFL 2021, equation (9): norm(d_t)/norm(d_previous)*d_t.
The first missing-history response is sendback; with one delta Zhu uses
unscaled delta. Zero denominator gives zero update, without fitted clipping.
On CIFAR, these parameter attacks leave non-parameter buffers unchanged.
This is a declared adaptation to the study architecture, not author code.
"""
import torch
from clients.attacks import FreeRiderAttacker
from server.aggregation import clone_state


class ReviewAttacker(FreeRiderAttacker):
    def __init__(self, config, device, parameter_keys):
        super().__init__(config, device)
        self.parameter_keys = sorted(parameter_keys)
        self.review_history = {}

    @staticmethod
    def spec(attack):
        if attack == "FraboniDecay":
            return dict(name=attack, gamma=1., noise_multiplier=1.,
                sigma="RMS of first nonzero-time received parameter delta; fixed thereafter",
                source="https://proceedings.mlr.press/v130/fraboni21a/fraboni21a.pdf#page=8")
        if attack == "ZhuScaledDelta":
            return dict(name=attack, equation=9, ratio="norm(current delta)/norm(previous delta)",
                source="https://neurips2021workshopfl.github.io/NFFL-2021/papers/2021/Zhu2021.pdf#page=4")
        return dict(name=attack, implementation="unchanged clients.attacks.FreeRiderAttacker")

    def state_dict(self):
        return {**super().state_dict(), "review_history": self.review_history}

    def load_state_dict(self, state):
        super().load_state_dict(state)
        self.review_history = state.get("review_history", {})

    def fabricate(self, client_id, received_state, round_idx, generator):
        if self.config.attack_type not in {"FraboniDecay", "ZhuScaledDelta"}:
            return super().fabricate(client_id, received_state, round_idx, generator)
        current = torch.cat([received_state[k].detach().reshape(-1) for k in self.parameter_keys])
        history = self.review_history.setdefault(client_id, {})
        result = clone_state(received_state)
        if "previous" not in history:
            history["previous"] = current.clone()
            return result
        delta = current - history["previous"]
        if self.config.attack_type == "FraboniDecay":
            if "sigma" not in history:
                history["sigma"] = float(delta.square().mean().sqrt())
            update = torch.randn(current.shape, device=current.device, dtype=current.dtype,
                generator=generator) * (history["sigma"] / max(1, round_idx - 1))
        else:
            previous_norm = history.get("delta_norm")
            scale = 1. if previous_norm is None else (float(delta.norm()) / previous_norm if previous_norm > 0 else 0.)
            update = delta * scale
        offset = 0
        for key in self.parameter_keys:
            count = result[key].numel()
            result[key] = result[key] + update[offset:offset+count].reshape_as(result[key])
            offset += count
        history.update(previous=current.clone(), delta_norm=float(delta.norm()))
        return result
