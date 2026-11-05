"""Review variants, no-label screening, clock liveness and fixed queue order."""
import json
from pathlib import Path
import random
from dataclasses import replace

import pytest
import torch

from build_review2_plans import build, HOLDOUT_SEEDS
from config import ExperimentConfig
from clients.review2_attacks import ReviewAttacker
from review2_config import ReviewConfig
from server.v15_certificate_memory import CycleState
from train_review2 import audit_quiet_since
from test_scheduled_queue import recovery, run_queue, calls, write_json

ROOT = Path(__file__).resolve().parents[1]


def test_multiseed_is_last_and_all_primary_conditions_are_present(tmp_path):
    configs=tmp_path/'configs'; configs.mkdir()
    name='v15_4_mnist_seed43_fr30_fr40_plan.json'
    (configs/name).write_bytes((ROOT/'configs'/name).read_bytes())
    queue=build(tmp_path)
    plans=[json.loads((tmp_path/p).read_text()) if (tmp_path/p).exists() else None for p in queue['plans']]
    assert [len(p['experiments']) for p in plans[:5]] == [4,48,16,12,16]
    assert len(plans[-1]['experiments']) == 70
    assert {e['config']['seed'] for p in plans[:5] for e in p['experiments']} == {42}
    assert {e['config']['seed'] for e in plans[-1]['experiments']} == set(HOLDOUT_SEEDS)
    assert not set(HOLDOUT_SEEDS) & {42,43,73}
    assert all('multiseed' not in p for p in queue['plans'][:-1])
    assert len({p['batch_name'] for p in plans if p}) == 6


@pytest.mark.parametrize('cooldown',[1,2])
def test_cooldown_only_finding_does_not_disable_later_audits(cooldown):
    state=CycleState(range(3))
    state.records[0]['audit_cooldown']=cooldown
    state.escalate_audit({0})
    assert not state.monitored
    assert audit_quiet_since(state,70) == 70
    # Once eligible, identical audit evidence opens review, never removal.
    while state.records[0]['audit_cooldown']:
        state.escalate_audit({0})
    state.escalate_audit({0})
    assert state.monitored == {0}
    assert audit_quiet_since(state,90) is None
    assert state.records[0]['category'] != 'X'


def test_zhu_equation9_and_checkpoint_restore_without_global_side_channel():
    cfg=ReviewConfig(attack_type='ZhuScaledDelta')
    attacker=ReviewAttacker(cfg,torch.device('cpu'),{'w'})
    rng=torch.Generator().manual_seed(42)
    def received(value): return {'w':torch.tensor([value]),'buffer':torch.tensor([7.])}
    attacker.fabricate(4,received(1.),1,rng)
    assert attacker.fabricate(4,received(3.),2,rng)['w'].item() == 5.
    saved=attacker.state_dict()
    clone=ReviewAttacker(cfg,torch.device('cpu'),{'w'}); clone.load_state_dict(saved)
    result=clone.fabricate(4,received(4.),3,rng)
    assert result['w'].item() == 4.5  # delta=1, previous norm=2.
    assert result['buffer'].item() == 7.


def test_fraboni_sigma_is_frozen_and_does_not_use_client_data():
    cfg=ReviewConfig(attack_type='FraboniDecay')
    attacker=ReviewAttacker(cfg,torch.device('cpu'),{'w'})
    rng=torch.Generator().manual_seed(7)
    attacker.fabricate(0,{'w':torch.zeros(2)},1,rng)
    attacker.fabricate(0,{'w':torch.tensor([2.,-2.])},2,rng)
    assert attacker.review_history[0]['sigma'] == 2.
    attacker.fabricate(0,{'w':torch.tensor([200.,-200.])},3,rng)
    assert attacker.review_history[0]['sigma'] == 2.


@pytest.mark.parametrize('variant,share',[('paired',.5),('paired',0.),('passive',.5),('oracle',.5)])
def test_tiny_training_has_expected_actual_traps_and_oracle_population(monkeypatch,tmp_path,variant,share):
    import train
    import train_review2 as engine
    from torch.utils.data import TensorDataset
    data=TensorDataset(torch.arange(16,dtype=torch.float32).reshape(8,2)/16,torch.arange(8)%2)
    monkeypatch.setattr(train,'get_datasets',lambda config:(data,data))
    monkeypatch.setattr(train,'partition_dataset',lambda dataset,config:[[2*c,2*c+1] for c in range(4)])
    monkeypatch.setattr(train,'get_model',lambda dataset:torch.nn.Linear(2,10))
    cfg=ReviewConfig(methodology_version='swtcp_v15_4',num_clients=4,num_rounds=30,
        free_rider_pct=share,attack_type='FR1',local_epochs=1,num_workers=0,
        device='cpu',pin_memory=False,output_dir=str(tmp_path),run_name=variant)
    engine.run_experiment(cfg,variant=variant)
    import csv
    with (tmp_path/variant/'client_metrics.csv').open(newline='') as handle:
        rows=list(csv.DictReader(handle))
    if variant=='paired':
        assert any(int(r['was_trapped']) for r in rows)
    else:
        assert not any(int(r['was_trapped']) for r in rows)
    if variant=='passive':
        # At the cycle decision, fresh quarantine can exclude responses in
        # either variant. Prior to that, passive sampling withholds nothing.
        assert all(int(r['was_aggregated']) for r in rows if int(r['round'])<20)
    if variant=='oracle':
        assert len({r['client_id'] for r in rows}) == 2
        assert all(int(r['was_aggregated']) and not int(r['is_free_rider']) for r in rows)
    assert json.loads((tmp_path/variant/'latest_results.json').read_text())['completed']


def test_review_checkpoint_replays_identical_final_weights(monkeypatch,tmp_path):
    import train
    import train_review2 as engine
    from torch.utils.data import TensorDataset
    data=TensorDataset(torch.arange(16,dtype=torch.float32).reshape(8,2)/16,torch.arange(8)%2)
    monkeypatch.setattr(train,'get_datasets',lambda config:(data,data))
    monkeypatch.setattr(train,'partition_dataset',lambda dataset,config:[[2*c,2*c+1] for c in range(4)])
    monkeypatch.setattr(train,'get_model',lambda dataset:torch.nn.Linear(2,10))
    monkeypatch.setattr(train,'delete_successful_checkpoints',lambda path:None)
    cfg=ReviewConfig(methodology_version='swtcp_v15_4',num_clients=4,num_rounds=30,
        free_rider_pct=.5,attack_type='FR1',local_epochs=1,num_workers=0,
        device='cpu',pin_memory=False,output_dir=str(tmp_path),run_name='full')
    engine.run_experiment(cfg)
    interrupted=replace(cfg,run_name='resume')
    def crash(progress):
        if progress['round']==13:
            raise RuntimeError('simulated crash')
    with pytest.raises(RuntimeError,match='simulated crash'):
        engine.run_experiment(interrupted,crash)
    checkpoint=tmp_path/'resume/latest_checkpoint.pt'
    engine.run_experiment(replace(interrupted,resume_checkpoint=str(checkpoint)))
    original=torch.load(tmp_path/'full/latest_checkpoint.pt',weights_only=False)
    resumed=torch.load(checkpoint,weights_only=False)
    assert all(torch.equal(value,resumed['global_state'][key]) for key,value in original['global_state'].items())
    assert original['state'] == resumed['state']


def test_mad_baseline_has_no_label_input_and_a_fixed_nominal_tail():
    from analyze_review2_results import mad_flags
    assert mad_flags({i:1. for i in range(100)}) == set()
    norms={i:float(i) for i in range(100)}
    norms[99]=-1000.
    assert mad_flags(norms) == {99}


@pytest.mark.parametrize('boundary',['before_final_checkpoint','after_final_checkpoint'])
def test_final_round_io_boundaries_preserve_all_client_and_removal_records(monkeypatch,tmp_path,boundary):
    import csv
    import train
    import train_review2 as engine
    from torch.utils.data import TensorDataset
    data=TensorDataset(torch.arange(16,dtype=torch.float32).reshape(8,2)/16,torch.arange(8)%2)
    monkeypatch.setattr(train,'get_datasets',lambda config:(data,data))
    monkeypatch.setattr(train,'partition_dataset',lambda dataset,config:[[2*c,2*c+1] for c in range(4)])
    monkeypatch.setattr(train,'get_model',lambda dataset:torch.nn.Linear(2,10))
    monkeypatch.setattr(train,'delete_successful_checkpoints',lambda path:None)
    cfg=ReviewConfig(methodology_version='swtcp_v15_4',num_clients=4,num_rounds=30,
        free_rider_pct=.5,attack_type='FR1',local_epochs=1,num_workers=0,
        device='cpu',pin_memory=False,output_dir=str(tmp_path),run_name='uninterrupted')
    engine.run_experiment(cfg)
    original_save=train.save_rolling_checkpoint
    def interrupted_save(payload,*args):
        if payload['round']==30 and boundary=='before_final_checkpoint':
            raise RuntimeError('power loss at final boundary')
        original_save(payload,*args)
        if payload['round']==30:
            raise RuntimeError('power loss at final boundary')
    monkeypatch.setattr(train,'save_rolling_checkpoint',interrupted_save)
    interrupted=replace(cfg,run_name='interrupted')
    with pytest.raises(RuntimeError,match='power loss'):
        engine.run_experiment(interrupted)
    monkeypatch.setattr(train,'save_rolling_checkpoint',original_save)
    engine.run_experiment(replace(interrupted,resume_checkpoint=str(tmp_path/'interrupted/latest_checkpoint.pt')))
    for name in ['client_metrics.csv','removals.csv','cycle_decisions.csv']:
        def rows(run):
            with (tmp_path/run/name).open(newline='') as handle:
                return list(csv.DictReader(handle))
        assert rows('uninterrupted') == rows('interrupted')
    assert json.loads((tmp_path/'interrupted/latest_results.json').read_text())['completed']


def test_registration_rejects_plan_or_source_changes(monkeypatch,tmp_path):
    import hashlib
    import run_review2_batch as runner
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    plan=tmp_path/'configs/plan.json'; plan.parent.mkdir()
    plan.write_text('{}')
    source=tmp_path/'engine.py'; source.write_text('frozen engine')
    write_json(tmp_path/'configs/review2_registration.json',dict(
        plan_sha256={'configs/plan.json':hashlib.sha256(plan.read_bytes()).hexdigest()},
        source_sha256={'engine.py':hashlib.sha256(source.read_bytes()).hexdigest()}))
    runner.check_registration(plan)
    source.write_text('outcome-dependent change')
    with pytest.raises(ValueError,match='Registered source changed'):
        runner.check_registration(plan)


@pytest.mark.parametrize('marker_case',['none','owned','user_changed'])
def test_review_recovery_handoff_and_order(recovery,marker_case):
    for name in ['priority','last']:
        write_json(recovery/f'configs/{name}.json',dict(workflow='review2',batch_name=name,
            results_root='results',experiments=[dict(id='run')]))
    selection=dict(auto_resume=True,workflow='v15_detection',plan='configs/priority.json',
        queue='configs/review_queue.json',auto_update_paper=False,
        priority_handoff=dict(marker_path='results/paused/STOP_REQUESTED',marker_content='owned pause'))
    write_json(recovery/'configs/active_experiment_schedule.json',selection)
    write_json(recovery/'configs/review_queue.json',dict(plans=['configs/priority.json','configs/last.json']))
    marker=recovery/'results/paused/STOP_REQUESTED'
    if marker_case!='none':
        marker.parent.mkdir(parents=True)
        marker.write_text('owned pause' if marker_case=='owned' else 'user stop')
    result=run_queue(recovery)
    if marker_case=='user_changed':
        assert result.returncode != 0
        assert marker.read_text() == 'user stop'
        assert not calls(recovery)
    else:
        assert result.returncode == 0, result.stdout+result.stderr
        assert calls(recovery) == ['--plan:priority','--plan:last']
        assert not marker.exists()
        assert run_queue(recovery).returncode == 0
        assert calls(recovery) == ['--plan:priority','--plan:last']
