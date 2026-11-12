"""Prospective isolation, attack visibility, RAM policy and real resume tests."""
import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import pytest
import torch
from build_review3_plans import build
from review3_config import BlockBConfig
from review3_analysis import auc
from run_review3_batch import launch_requirement

ROOT=Path(__file__).resolve().parents[1]

def test_registration_preserves_original_sources_and_plans():
    reg=json.loads((ROOT/'configs/review2_registration.json').read_text())
    for field in ['source_sha256','plan_sha256']:
        for p,h in reg[field].items(): assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p

def test_queue_preserves_registered_cells_and_heldout_last(tmp_path):
    c=tmp_path/'configs';c.mkdir()
    for p in ['review2_03_passive_seed42.json','review2_priority_queue.json']:
        (c/p).write_bytes((ROOT/'configs'/p).read_bytes())
    paths=build(tmp_path)
    old=json.loads((c/'review2_priority_queue.json').read_text())['plans']
    new=json.loads((c/'review3_priority_queue.json').read_text())['plans']
    assert set(old)<=set(new) and new[:3]==old[:3] and new[-1]==old[-1]
    counts=[len(json.loads((tmp_path/p).read_text())['experiments']) for p in paths]
    assert counts==[1,2,16,64,8,12,32]
    sweep=json.loads((tmp_path/paths[-1]).read_text())
    assert {e['config']['trap_noise_scale'] for e in sweep['experiments']}=={0.,.005,.01,.02}

def test_auc_orientation_ties_and_degenerate_cases():
    assert auc([0,1],[0,1])==1
    assert auc([1,0],[0,1])==0
    assert auc([1,1],[0,1])==.5
    assert auc([1,2],[0,0]) is None
    with pytest.raises(ValueError): auc([float('nan'),0],[0,1])

def test_operational_headroom_is_lighter_and_dataset_specific():
    settings=json.loads((ROOT/'configs/review3_resources.json').read_text())
    assert launch_requirement('mnist',settings)==.75*2**30
    assert launch_requirement('cifar10',settings)==2**30
    assert launch_requirement('other',settings)==2**30

def test_oracle_norm_matching_and_mixed_assignment_checkpoint():
    from clients.review3_attacks import BlockBAttacker
    cfg=BlockBConfig(attack_type='OracleNormMatchedFR4')
    a=BlockBAttacker(cfg,torch.device('cpu'),{'w'}); a.set_attackers(range(8))
    a.oracle_target=3.
    rng=torch.Generator().manual_seed(42)
    received={'w':torch.zeros(12)}
    response=a.fabricate(0,received,1,rng)
    assert float(response['w'].norm())==pytest.approx(3.,rel=1e-5)
    b=BlockBAttacker(cfg,torch.device('cpu'),{'w'});b.load_state_dict(a.state_dict())
    assert b.oracle_target==3. and b.assignment==a.assignment
    mixed=BlockBAttacker(replace(cfg,attack_type='MixedFR'),torch.device('cpu'),{'w'})
    mixed.set_attackers(range(8))
    assert list(mixed.assignment.values()).count('FR4')==2

def test_disabled_nomination_views_and_no_memory_state():
    from server import review3_ablation as ab
    from server import v15_strict_norm as strict
    rows=[dict(client_id=0,trap_id=t,norm_z=9.,profile_z=8.,delta_norm=2.,profile_distance=4.,exact_sendback=1,exact_zero_delta=1) for t in (0,1)]
    ab.configure('norm_only');views=ab._views(rows)
    assert all(v['profile_z']==v['profile_distance']==v['exact_sendback']==0 for v in views)
    ab.configure('profile_only');views=ab._views(rows)
    assert all(v['norm_z']==v['delta_norm']==v['exact_sendback']==0 for v in views)
    ab.configure('sendback_only');d,_=ab.screen(rows,20)
    assert d[0]['strong_channels']=='exact_sendback'
    ab.configure('no_memory');assert ab.CycleState is strict.CycleState
    ab.configure('combined')

def test_original_manifest_not_rewritten_by_operational_supervisor():
    import run_review2_batch as frozen
    import run_review3_batch as supervisor
    path=ROOT/'configs/review2_02_low_share_seed42.json'
    assert not supervisor.is_block_b(path)
    plan=frozen.read(path)
    stored=frozen.read(ROOT/'results/review2_02_low_share_seed42/experiment_manifest.json')
    assert stored==frozen.snapshot(plan)
    supervisor.validate(path,plan)

def test_timing_reanalysis_uses_server_core_not_client_training():
    from review3_analysis import timing_reanalysis
    for report in timing_reanalysis():
        assert .8<report['checking_fraction_of_checking_plus_aggregation']<.95
        assert report['honest_training_seconds_ours']>0

def test_lin_attempt_recovers_final_checkpoint_boundary(monkeypatch,tmp_path):
    import run_lin_std_validation as lin
    from torch.utils.data import TensorDataset
    torch.set_num_threads(1)
    monkeypatch.setattr(lin.torch,'set_num_threads',lambda n:None)
    data=TensorDataset(torch.zeros(200,1,28,28),torch.arange(200)%10)
    monkeypatch.setattr(lin.shared,'get_datasets',lambda config:(data,data))
    monkeypatch.setattr(lin.shared,'partition_dataset',lambda dataset,config:[[2*c,2*c+1] for c in range(100)])
    monkeypatch.setattr(lin,'fit_std',lambda x,*args:(None,None,dict(fake=True)))
    monkeypatch.setattr(lin,'score_std',lambda a,b,x,c:x.std(dim=1))
    plan=dict(defaults={});entry=dict(config=dict(global_eta=.3,num_rounds=10))
    lin.run(plan,tmp_path,entry)
    original=(tmp_path/'global_metrics.csv').read_bytes()
    (tmp_path/'latest_results.json').write_text('{}')
    lin.run(plan,tmp_path,entry)
    assert (tmp_path/'global_metrics.csv').read_bytes()==original
    assert json.loads((tmp_path/'latest_results.json').read_text())['completed']

@pytest.mark.parametrize('arm,attack',[('combined','OracleNormMatchedFR4'),('combined','MixedFR'),('norm_only','FR1'),('profile_only','FR1'),('sendback_only','FR1'),('no_memory','FR1')])
def test_block_b_actual_training_and_interrupted_resume(monkeypatch,tmp_path,arm,attack):
    import train
    import train_review3 as engine
    from torch.utils.data import TensorDataset
    torch.set_num_threads(1)
    data=TensorDataset(torch.arange(16,dtype=torch.float32).reshape(8,2)/16,torch.arange(8)%2)
    monkeypatch.setattr(train,'get_datasets',lambda config:(data,data))
    monkeypatch.setattr(train,'partition_dataset',lambda dataset,config:[[2*c,2*c+1] for c in range(4)])
    monkeypatch.setattr(train,'get_model',lambda dataset:torch.nn.Linear(2,10))
    monkeypatch.setattr(train,'delete_successful_checkpoints',lambda path:None)
    cfg=BlockBConfig(methodology_version='swtcp_v15_4',num_clients=4,num_rounds=30,free_rider_pct=.5,
        attack_type=attack,detector_arm=arm,local_epochs=1,num_workers=0,device='cpu',pin_memory=False,
        output_dir=str(tmp_path),run_name='full')
    engine.run_experiment(cfg)
    interrupted=replace(cfg,run_name='resumed')
    def crash(progress):
        if progress['round']==13: raise RuntimeError('power loss')
    with pytest.raises(RuntimeError,match='power loss'): engine.run_experiment(interrupted,crash)
    path=tmp_path/'resumed/latest_checkpoint.pt'
    engine.run_experiment(replace(interrupted,resume_checkpoint=str(path)))
    full=torch.load(tmp_path/'full/latest_checkpoint.pt',weights_only=False)
    resumed=torch.load(path,weights_only=False)
    assert full['state']==resumed['state']
    assert all(torch.equal(v,resumed['global_state'][k]) for k,v in full['global_state'].items())
    for name in ['cycle_signals.csv','cycle_decisions.csv','client_metrics.csv','removals.csv']:
        assert (tmp_path/'full'/name).read_bytes()==(tmp_path/'resumed'/name).read_bytes()
