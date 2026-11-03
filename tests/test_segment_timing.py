import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
import torch
from torch.utils.data import TensorDataset

from config import ExperimentConfig
from segment_timing import RoundTimer, SEGMENTS, instrumented_engine, read_rows, write_rows


def test_nested_timing_is_exclusive_and_sums_to_wall(tmp_path):
    clock = [0.]
    timer = RoundTimer(tmp_path/'times.csv', clock=lambda: clock[0])
    timer.begin(1)
    with timer.segment('scheduling_seconds'):
        clock[0] += 2
        with timer.segment('trap_generation_seconds'):
            clock[0] += 3
        clock[0] += 1
    clock[0] += 2
    timer.finish(dict(mode='test',active_start=[0],truth=set(),trapped=set(),aggregated={0},metrics=dict(accuracy=1.)))
    row = timer.rows[0]
    assert row['scheduling_seconds'] == row['trap_generation_seconds'] == 3
    assert row['unassigned_seconds'] == 2
    assert sum(row[k] for k in SEGMENTS) + row['unassigned_seconds'] == row['observed_round_wall_seconds'] == 8


def test_instrumentation_preserves_scientific_results_and_weights(monkeypatch,tmp_path):
    import train as shared
    import train_v15_4 as engine
    torch.set_num_threads(1)
    data = TensorDataset(torch.arange(160,dtype=torch.float32).reshape(40,4)/160,torch.arange(40)%10)
    monkeypatch.setattr(shared,'get_datasets',lambda cfg:(data,data))
    monkeypatch.setattr(shared,'partition_dataset',lambda data,cfg:[[2*c,2*c+1] for c in range(20)])
    monkeypatch.setattr(shared,'get_model',lambda name:torch.nn.Linear(4,10))
    weights=[]
    original = engine.fedavg_delta
    def collect(*args,**kwargs):
        result=original(*args,**kwargs)
        weights.append({k:v.clone() for k,v in result.items()})
        return result
    monkeypatch.setattr(engine,'fedavg_delta',collect)
    cfg=ExperimentConfig(methodology_version='swtcp_v15_4',dataset='mnist',distribution='noniid',
        num_clients=20,num_rounds=30,local_epochs=1,batch_size=2,attack_type='FR3',free_rider_pct=.4,
        seed=42,device='cpu',save_checkpoints=False,output_dir=str(tmp_path),run_name='reference')
    engine.run_experiment(cfg)
    reference=list(weights)
    weights.clear()
    timer=RoundTimer(tmp_path/'instrumented/round_timings.csv')
    instrumented,provenance=instrumented_engine(timer)
    instrumented(replace(cfg,run_name='instrumented'))
    assert len(weights)==len(reference)==30
    assert all(torch.equal(a[k],b[k]) for a,b in zip(reference,weights) for k in a)
    for name in ('client_metrics.csv','cycle_signals.csv','cycle_decisions.csv','removals.csv','detection_summary.csv'):
        assert (tmp_path/'reference'/name).read_bytes()==(tmp_path/'instrumented'/name).read_bytes()
    assert (tmp_path/'reference/protocol.json').read_bytes()==(tmp_path/'instrumented/protocol.json').read_bytes()
    rows=read_rows(timer.path)
    assert len(rows)==30
    assert sum(float(r['trap_generation_seconds']) for r in rows)>0
    assert sum(float(r['decision_seconds']) for r in rows)>0
    assert all(float(r['checkpoint_seconds'])==0 for r in rows)
    assert all(abs(sum(float(r[k]) for k in SEGMENTS)+float(r['unassigned_seconds'])-
                   float(r['observed_round_wall_seconds']))<1e-6 for r in rows)


def test_std_transform_includes_checkpoint_and_keeps_original_worker_path(tmp_path):
    from run_std_segment_timing import StdTimer, instrumented_std
    import run_std_dagmm_long as core
    function,provenance=instrumented_std(StdTimer(tmp_path/'std.csv'))
    assert function.__globals__['__file__']==core.__file__
    assert provenance['canonical_source_sha256']==hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest()
    assert function.__globals__['_segment_timer'].path==tmp_path/'std.csv'


def test_std_measures_real_worker_and_checkpoint_without_overlapping(monkeypatch,tmp_path):
    from argparse import Namespace
    import train as shared
    from run_std_segment_timing import StdTimer, instrumented_std
    data=TensorDataset(torch.arange(32,dtype=torch.float32).reshape(8,4)/32,torch.arange(8)%10)
    monkeypatch.setattr(shared,'get_datasets',lambda cfg:(data,data))
    monkeypatch.setattr(shared,'partition_dataset',lambda data,cfg:[[2*c,2*c+1] for c in range(4)])
    monkeypatch.setattr(shared,'get_model',lambda name:torch.nn.Linear(4,10))
    output=tmp_path/'std'
    output.mkdir()
    timer=StdTimer(output/'segment_timings.csv')
    function,_=instrumented_std(timer)
    args=Namespace(output=output,resume=False,dataset='mnist',distribution='iid',seed=42,
        clients=4,rounds=2,attack='FR3',free_rider_pct=.5,local_epochs=1,threads=1,
        detector_epochs=2,detector_batch=4)
    function(args)
    rows=read_rows(timer.path)
    assert len(rows)==2
    for row in rows:
        total=sum(float(row[k]) for k in ('round_compute_seconds','checkpoint_seconds','reporting_seconds','unassigned_seconds'))
        assert abs(total-float(row['observed_round_wall_seconds']))<1e-5
        assert float(row['fit_seconds'])>0 and float(row['checkpoint_seconds'])>0
        assert float(row['joint_training_seconds'])>0 and int(row['detector_epochs'])==2
    assert (output/'latest_checkpoint.pt').is_file()


@pytest.mark.parametrize('case',['success','already_cleared','selector_changed','marker_changed'])
def test_restoration_clears_only_owned_pause_and_restores_original_queue(tmp_path,monkeypatch,case):
    import run_timing_interlude as controller
    monkeypatch.setattr(controller,'ROOT',tmp_path)
    job_path=tmp_path/'configs/job.json'
    job_path.parent.mkdir()
    active=job_path.parent/'active_experiment_schedule.json'
    selected=dict(auto_resume=True,priority_job='configs/job.json')
    if case=='selector_changed':
        selected['priority_job']='configs/user_changed.json'
    active.write_text(json.dumps(selected))
    batch=tmp_path/'results/paused'
    batch.mkdir(parents=True)
    marker=batch/'STOP_REQUESTED'
    if case!='already_cleared':
        marker.write_text('user stop' if case=='marker_changed' else 'owned pause')
    original=dict(auto_resume=True,workflow='v15_detection',plan='original.json')
    job=dict(paused_batch='results/paused',pause_marker='owned pause',resume_schedule=original)
    if case in ('selector_changed','marker_changed'):
        with pytest.raises(RuntimeError):
            controller.restore(job,job_path)
        assert marker.exists() and json.loads(active.read_text())==selected
    else:
        controller.restore(job,job_path)
        assert not marker.exists() and json.loads(active.read_text())==original


def test_done_requires_measured_complete_round_sequence(tmp_path):
    from atomic_io import atomic_write_json
    from run_timing_interlude import done
    output=tmp_path/'ours'
    output.mkdir()
    atomic_write_json(output/'timing_summary.json',dict(state='completed',completed_rounds=2))
    write_rows(output/'round_timings.csv',[dict(round=1),dict(round=1)])
    assert not done(output,2)
    write_rows(output/'round_timings.csv',[dict(round=1),dict(round=2)])
    assert done(output,2)


def test_timer_replays_only_rows_covered_by_recovery_checkpoint(tmp_path):
    path=tmp_path/'timings.csv'
    write_rows(path,[dict(round=1),dict(round=2),dict(round=3)])
    timer=RoundTimer(path,completed=2)
    assert [int(r['round']) for r in timer.rows]==[1,2]


def test_watch_prioritizes_interlude_before_paused_original_queue(tmp_path,monkeypatch):
    import monitor
    from atomic_io import atomic_write_json
    monkeypatch.chdir(tmp_path)
    (tmp_path/'configs').mkdir()
    atomic_write_json(tmp_path/'configs/active_experiment_schedule.json',dict(
        auto_resume=True,workflow='v15_detection',plan='configs/original.json',
        priority_job='configs/job.json',priority_status='results/timing/experiment_status.json'))
    atomic_write_json(tmp_path/'configs/original.json',dict(batch_name='paused',results_root='results'))
    assert monitor.resolve_status_path(None)==Path('results/timing/experiment_status.json')
