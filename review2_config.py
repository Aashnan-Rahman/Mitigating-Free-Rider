"""Review-only attack names without modifying checkpoint-hashed configuration."""
from config import ExperimentConfig

PUBLISHED_ATTACKS = {"FraboniDecay", "ZhuScaledDelta"}


class ReviewConfig(ExperimentConfig):
    def validate(self):
        values = self.to_dict()
        if values["attack_type"] in PUBLISHED_ATTACKS:
            values["attack_type"] = "FR4"
        ExperimentConfig(**values).validate()
