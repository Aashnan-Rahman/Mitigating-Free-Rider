from train import delete_successful_checkpoints


def test_success_cleanup_deletes_only_recovery_checkpoints(tmp_path) -> None:
    numbered = tmp_path / "checkpoint_round_0099.pt"
    latest = tmp_path / "latest_checkpoint.pt"
    result = tmp_path / "run_config.json"
    similarly_named = tmp_path / "checkpoint_notes.txt"
    for path in (numbered, latest, result, similarly_named):
        path.write_text("test", encoding="utf-8")

    deleted = delete_successful_checkpoints(tmp_path)

    assert set(deleted) == {numbered.name, latest.name}
    assert not numbered.exists()
    assert not latest.exists()
    assert result.exists()
    assert similarly_named.exists()
