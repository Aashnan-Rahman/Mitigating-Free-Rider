import json
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from std_dagmm_recovery import checkpoint,load_checkpoint,exclusive_lock
from run_std_dagmm_batch import command_for,is_complete,make_status

ROOT=Path(__file__).resolve().parents[1]


def saved(round_index,protocol):
    return dict(round=round_index,protocol=protocol,rows=[dict(round=r) for r in range(1,round_index+1)],
                global_state=dict(weight=torch.tensor([round_index],dtype=torch.float32)))


def test_checkpoint_rotation_and_fallback_repair(tmp_path):
    path=tmp_path/'latest_checkpoint.pt'
    protocol=dict(source='frozen')
    checkpoint(path,saved(1,protocol))
    checkpoint(path,saved(2,protocol))
    assert load_checkpoint(path,protocol)['round']==2
    path.write_bytes(b'power-loss-corruption')
    assert load_checkpoint(path,protocol)['round']==1
    # Fallback must repair latest before publishing again; otherwise a later
    # outage could replace the good backup with the corrupt latest.
    checkpoint(path,saved(2,protocol))
    path.write_bytes(b'another-outage')
    assert load_checkpoint(path,protocol)['round']==1


def test_changed_protocol_is_not_silently_accepted(tmp_path):
    path=tmp_path/'latest_checkpoint.pt'
    checkpoint(path,saved(1,dict(source='old')))
    with pytest.raises(ValueError,match='mismatch'):
        load_checkpoint(path,dict(source='new'))


def test_missing_checkpoint_can_restart_round_zero_but_corrupt_files_cannot(tmp_path):
    path=tmp_path/'latest_checkpoint.pt'
    assert load_checkpoint(path,{}) is None
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='No readable checkpoint'):
        load_checkpoint(path,{})


def test_lock_prevents_cross_process_duplicate(tmp_path):
    path=tmp_path/'lock'
    command=[sys.executable,'-c',
        'from pathlib import Path; from std_dagmm_recovery import exclusive_lock; '
        'lock=exclusive_lock(Path(__import__("sys").argv[1])); lock.__enter__()',str(path)]
    with exclusive_lock(path):
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        assert result.returncode!=0
        assert 'BlockingIOError' in result.stderr
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0


def test_queue_has_exactly_two_actual_hundred_round_runs_and_resume_flag(tmp_path):
    plan=json.loads((ROOT/'configs/std_dagmm_100_queue.json').read_text())
    assert [e['dataset'] for e in plan['experiments']]==['mnist','cifar10']
    assert plan['defaults']['rounds']==100
    command=command_for(plan,plan['experiments'][0],tmp_path)
    assert command[command.index('--rounds')+1]=='100'
    assert '--resume' not in command
    (tmp_path/'protocol.json').write_text('{}')
    assert '--resume' in command_for(plan,plan['experiments'][0],tmp_path)


def test_incomplete_run_not_completed_by_status_alone(tmp_path):
    (tmp_path/'status.json').write_text(json.dumps(dict(state='completed')))
    (tmp_path/'summary.json').write_text(json.dumps(dict(state='completed',completed_rounds=100)))
    assert not is_complete(tmp_path,100)
    (tmp_path/'round_timings.csv').write_text('round\n'+'\n'.join(map(str,range(1,101)))+'\n')
    assert is_complete(tmp_path,100)


def test_new_queue_status_is_watch_compatible_and_does_not_invent_eta(tmp_path):
    plan=json.loads((ROOT/'configs/std_dagmm_100_queue.json').read_text())
    state=make_status(plan,tmp_path)
    assert state['total_rounds']==200 and state['completed_rounds']==0
    assert state['total_experiments']==2
    assert state['estimated_remaining_seconds'] is None
    assert state['experiments'][0]['config']['methodology_version']=='std_dagmm_native_observational'


def test_native_monitor_reports_flags_not_suspicion(capsys,tmp_path):
    from monitor import render
    plan=json.loads((ROOT/'configs/std_dagmm_100_queue.json').read_text())
    state=make_status(plan,tmp_path)
    state['current_experiment']=state['experiments'][0]['id']
    render(state)
    result=capsys.readouterr().out
    assert 'flags only, no removals' in result
    assert 'Working round:' in result
    assert 'Suspected:' not in result and 'Candidate:' not in result


def test_interrupted_toy_training_replays_same_models_and_input_hashes(monkeypatch,tmp_path):
    """Exercise the real run/checkpoint path and real fresh-fit subprocesses.

    Tiny local test data/model only; this is not research evidence or a reboot.
    """
    from argparse import Namespace
    import train
    import run_std_dagmm_long as runner
    from torch.utils.data import TensorDataset
    data=TensorDataset(torch.arange(16,dtype=torch.float32).reshape(8,2)/16,
                       torch.arange(8)%2)
    monkeypatch.setattr(train,'get_datasets',lambda config:(data,data))
    monkeypatch.setattr(train,'partition_dataset',lambda dataset,config:[[2*c,2*c+1] for c in range(4)])
    monkeypatch.setattr(train,'get_model',lambda dataset:torch.nn.Linear(2,10))
    original=train.train_local_model
    def args(output,resume=False):
        output.mkdir(exist_ok=True)
        return Namespace(dataset='mnist',rounds=2,clients=4,local_epochs=1,detector_epochs=1,
            detector_batch=4,distribution='iid',attack='FR3',free_rider_pct=.5,seed=42,
            threads=1,resume=resume,output=output)
    baseline=tmp_path/'baseline'
    interrupted=tmp_path/'interrupted'
    runner.run(args(baseline))
    calls=0
    def fail_during_round_two(*values,**kwargs):
        nonlocal calls
        calls+=1
        if calls==3:
            raise RuntimeError('simulated interruption during round two')
        return original(*values,**kwargs)
    monkeypatch.setattr(train,'train_local_model',fail_during_round_two)
    with pytest.raises(RuntimeError,match='simulated interruption'):
        runner.run(args(interrupted))
    assert torch.load(interrupted/'latest_checkpoint.pt',weights_only=False)['round']==1
    monkeypatch.setattr(train,'train_local_model',original)
    runner.run(args(interrupted,resume=True))
    before=torch.load(baseline/'latest_checkpoint.pt',weights_only=False)
    after=torch.load(interrupted/'latest_checkpoint.pt',weights_only=False)
    assert after['round']==2
    assert [r['input_sha256'] for r in before['rows']]==[r['input_sha256'] for r in after['rows']]
    assert all(torch.equal(before['global_state'][key],after['global_state'][key]) for key in before['global_state'])


def test_failed_first_run_never_starts_second(monkeypatch,tmp_path):
    import run_std_dagmm_batch as batch
    plan=json.loads((ROOT/'configs/std_dagmm_100_queue.json').read_text())
    plan['results_root']=str(tmp_path/'results')
    plan_path=tmp_path/'plan.json'
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(batch,'active_runner',lambda path:None)
    calls=[]
    class FailedChild:
        returncode=7
        def __init__(self,command,**kwargs):
            calls.append(command)
        def poll(self):
            return 7
    monkeypatch.setattr(batch.subprocess,'Popen',FailedChild)
    with pytest.raises(RuntimeError,match='incomplete'):
        batch.run(plan_path)
    assert len(calls)==1
    assert 'mnist' in ' '.join(calls[0])
    assert 'cifar10' not in ' '.join(calls[0])
    status=json.loads((tmp_path/'results'/plan['batch_name']/'experiment_status.json').read_text())
    assert status['state']=='recovering'
    assert status['experiments'][1]['state']=='pending'
