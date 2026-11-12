"""Prospective Block B settings; never accepted by the frozen review2 runner."""
from dataclasses import dataclass
from review2_config import ReviewConfig

ARMS = {'combined', 'norm_only', 'profile_only', 'sendback_only', 'no_memory'}

@dataclass
class BlockBConfig(ReviewConfig):
    detector_arm: str = 'combined'
    unperturbed_challenges: bool = False

    def validate(self):
        values = self.to_dict()
        arm = values.pop('detector_arm')
        values.pop('unperturbed_challenges')
        if arm not in ARMS:
            raise ValueError('Unknown preregistered detector arm')
        if self.unperturbed_challenges and self.trap_noise_scale != 0:
            raise ValueError('Unperturbed challenges require exactly zero perturbation')
        if values['attack_type'] in {'MixedFR', 'OracleNormMatchedFR4'}:
            values['attack_type'] = 'FR4'
        ReviewConfig(**values).validate()
