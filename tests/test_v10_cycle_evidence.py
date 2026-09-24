import torch

import train
from config import ExperimentConfig
from server.detection import DetectionResult


def _result(flagged: bool = False) -> DetectionResult:
    return DetectionResult(
        flagged=flagged,
        penalty=0,
        cosine_similarity=None,
        delta_norm=1.0,
        norm_z_score=4.0 if flagged else 0.0,
        norm_median=1.0,
        norm_mad=0.1,
        loss_z_score=None,
        loss_median=None,
        loss_mad=None,
        reason="norm_outlier" if flagged else None,
        magnitude_flag=flagged,
    )


def test_reference_outlier_from_either_trap_is_removed_from_both_final_baselines(
    monkeypatch,
) -> None:
    reference_calls: list[set[int]] = []

    def fake_evaluate_updates(
        deltas, profiles, reference, trapped_clients, config, reference_ids=None
    ):
        del profiles, reference, trapped_clients, config
        reference_calls.append(set(reference_ids or set()))
        provisional_trap_a = len(reference_calls) == 1
        return {
            client_id: _result(provisional_trap_a and client_id == 0)
            for client_id in deltas
        }

    monkeypatch.setattr(train, "evaluate_updates", fake_evaluate_updates)
    config = ExperimentConfig(
        methodology_version="swtcp_v10", cycle_min_reference_clients=2
    )
    client_ids = {0, 1, 2}
    deltas = {
        client_id: [torch.tensor([1.0]), torch.tensor([1.0])]
        for client_id in client_ids
    }
    profiles = {
        client_id: [torch.tensor([1.0]), torch.tensor([1.0])]
        for client_id in client_ids
    }

    evidence = train.evaluate_completed_cycle(
        coverage_deltas=deltas,
        coverage_profiles=profiles,
        coverage_trap_ids={client_id: [0, 1] for client_id in client_ids},
        coverage_observation_rounds={client_id: [11, 12] for client_id in client_ids},
        active_clients=client_ids,
        checks=2,
        config=config,
        trusted_reference_clients=client_ids,
    )

    assert evidence["reference_valid"]
    assert evidence["reference_outliers"] == {0}
    assert reference_calls[:2] == [client_ids, client_ids]
    assert reference_calls[2:] == [{1, 2}, {1, 2}]
