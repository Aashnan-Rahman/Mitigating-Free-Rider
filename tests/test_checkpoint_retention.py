import torch

from train import save_rolling_checkpoint


def test_rolling_checkpoint_keeps_only_the_five_newest(tmp_path) -> None:
    for round_idx in range(1, 8):
        save_rolling_checkpoint(
            {"round": round_idx},
            tmp_path,
            round_idx,
            keep_last=5,
        )

    numbered = sorted(path.name for path in tmp_path.glob("checkpoint_round_*.pt"))

    assert numbered == [
        "checkpoint_round_0003.pt",
        "checkpoint_round_0004.pt",
        "checkpoint_round_0005.pt",
        "checkpoint_round_0006.pt",
        "checkpoint_round_0007.pt",
    ]
    assert torch.load(
        tmp_path / "latest_checkpoint.pt", weights_only=False
    )["round"] == 7


def test_rolling_checkpoint_honors_a_smaller_retention_window(tmp_path) -> None:
    for round_idx in range(1, 4):
        save_rolling_checkpoint(
            {"round": round_idx},
            tmp_path,
            round_idx,
            keep_last=1,
        )

    numbered = list(tmp_path.glob("checkpoint_round_*.pt"))

    assert [path.name for path in numbered] == ["checkpoint_round_0003.pt"]
