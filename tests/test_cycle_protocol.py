from config import ExperimentConfig
from server.cycle_protocol import transition_cycle_state


def _transition(**overrides):
    values = {
        "role": "R",
        "failed_probes": 0,
        "checks": 2,
        "score": 0.0,
        "clean_cycles": 0,
        "strong_cycles": 0,
        "trusted_strong_cycles": 0,
        "initial_cycle": False,
        "trusted_cycle": True,
        "config": ExperimentConfig(methodology_version="swtcp_v10"),
    }
    values.update(overrides)
    return transition_cycle_state(**values)


def test_initial_cycle_assigns_r_c_and_s_from_failed_probe_count() -> None:
    assert _transition(initial_cycle=True, failed_probes=0).role == "R"
    assert _transition(initial_cycle=True, failed_probes=1).role == "C"
    suspicious = _transition(initial_cycle=True, failed_probes=2)
    assert suspicious.role == "S"
    assert suspicious.score == -2.0
    assert suspicious.strong_cycles == 1
    assert suspicious.trusted_strong_cycles == 0


def test_initial_and_trusted_strong_cycles_remove_at_minus_four() -> None:
    confirmed = _transition(
        role="S",
        failed_probes=2,
        score=-2.0,
        strong_cycles=1,
        trusted_strong_cycles=0,
    )
    assert confirmed.score == -4.0
    assert confirmed.remove


def test_existing_r_enters_c_before_s_even_after_two_failures() -> None:
    result = _transition(role="R", failed_probes=2)
    assert result.role == "C"
    assert result.strong_cycles == 1


def test_clean_reward_is_capped_at_zero_and_rehabilitation_is_slow() -> None:
    first = _transition(role="C", score=-1.0, failed_probes=0)
    assert first.role == "C"
    assert first.score == -0.5
    second = _transition(
        role="C",
        score=first.score,
        clean_cycles=first.clean_cycles,
        failed_probes=0,
    )
    assert second.role == "R"
    assert second.score == 0.0
    assert second.rehabilitated

    clean_r = _transition(role="R", score=0.0, failed_probes=0)
    assert clean_r.score == 0.0


def test_s_requires_two_clean_cycles_to_reach_c_and_two_more_to_reach_r() -> None:
    state = _transition(role="S", score=-4.0, failed_probes=0)
    assert state.role == "S"
    state = _transition(
        role=state.role,
        score=state.score,
        clean_cycles=state.clean_cycles,
        failed_probes=0,
    )
    assert state.role == "C"
    assert not state.rehabilitated

    state = _transition(
        role=state.role,
        score=state.score,
        clean_cycles=state.clean_cycles,
        failed_probes=0,
    )
    assert state.role == "C"
    state = _transition(
        role=state.role,
        score=state.score,
        clean_cycles=state.clean_cycles,
        failed_probes=0,
    )
    assert state.role == "R"
    assert state.rehabilitated


def test_v11_weak_or_anomaly_quarantines_without_score_or_strong_evidence() -> None:
    config = ExperimentConfig(methodology_version="swtcp_v11")
    result = transition_cycle_state(
        role="R",
        failed_probes=2,
        checks=2,
        score=0.0,
        clean_cycles=0,
        strong_cycles=0,
        trusted_strong_cycles=0,
        initial_cycle=False,
        trusted_cycle=True,
        config=config,
        coherent_strong=False,
    )

    assert result.role == "C"
    assert result.score == 0.0
    assert result.strong_cycles == 0
    assert not result.remove


def test_v11_coherent_anomaly_retains_strong_confirmation_gate() -> None:
    config = ExperimentConfig(methodology_version="swtcp_v11")
    result = transition_cycle_state(
        role="C",
        failed_probes=2,
        checks=2,
        score=-2.0,
        clean_cycles=0,
        strong_cycles=1,
        trusted_strong_cycles=0,
        initial_cycle=False,
        trusted_cycle=True,
        config=config,
        coherent_strong=True,
    )

    assert result.role == "S"
    assert result.score == -4.0
    assert result.strong_cycles == 2
    assert result.trusted_strong_cycles == 1
    assert result.remove
