import json
from argparse import Namespace
from pathlib import Path
import pytest
import torch
from torch.utils.data import TensorDataset


def test_baseline_plan_is_complete_sixteen_case_grid():
    root=Path(__file__).resolve().parents[1]
    plan=json.loads((root/'configs/fedavg_cifar10_baseline_seed42_fr30_fr40.json').read_text())
    actual={(e['distribution'],e['attack'],e['free_rider_pct']) for e in plan['experiments']}
    expected={(d,a,p) for d in ('iid','noniid') for a in ('FR1','FR2','FR3','FR4') for p in (.3,.4)}
    assert actual==expected and len(plan['experiments'])==16
    assert plan['workflow']=='fedavg_no_detection'
    assert plan['defaults']['rounds']==100 and plan['defaults']['clients']==100
    from run_std_dagmm_batch import command_for
    command=command_for(plan,plan['experiments'][0],root/'test-output')
    assert command[1].endswith('run_fedavg_baseline.py')
    assert '--detector-epochs' not in command


def test_baseline_aggregates_every_response_without_detector_calls(monkeypatch,tmp_path):
    import train
    import benchmark_mnist_std_dagmm as benchmark
    import run_fedavg_baseline as baseline
    dataset=TensorDataset(torch.arange(16,dtype=torch.float32).reshape(8,2)/16,torch.arange(8)%2)
    monkeypatch.setattr(train,'get_datasets',lambda cfg:(dataset,dataset))
    monkeypatch.setattr(train,'partition_dataset',lambda data,cfg:[[2*c,2*c+1] for c in range(4)])
    monkeypatch.setattr(train,'get_model',lambda name:torch.nn.Linear(2,10))
    def forbidden(*args,**kwargs):
        raise AssertionError('Detection/profiling must not execute in a no-detection baseline')
    monkeypatch.setattr(benchmark,'fit_std',forbidden)
    monkeypatch.setattr(train,'build_layer_profile',forbidden)
    args=Namespace(dataset='mnist',distribution='iid',attack='FR1',free_rider_pct=.5,clients=4,
        rounds=2,local_epochs=1,threads=1,seed=42,output=tmp_path,resume=False)
    baseline.run(args)
    report=json.loads((tmp_path/'summary.json').read_text())
    assert report['completed_rounds']==2 and not report['detection_enabled']
    assert not report['trap_generation_enabled'] and report['removals']==0
    import csv
    with (tmp_path/'round_timings.csv').open(newline='') as handle:
        rows=list(csv.DictReader(handle))
    assert all(int(r['num_aggregated'])==4 and int(r['active_clients'])==4 and float(r['detector_seconds'])==0 for r in rows)
    assert (tmp_path/'final_model.pt').is_file()
    assert not (tmp_path/'client_flags.csv').exists()


def test_baseline_monitor_does_not_show_suspicion(capsys):
    from monitor import render
    render(dict(batch_id='baseline',current_experiment='run',experiments=[dict(id='run',
        config=dict(methodology_version='fedavg_no_detection'),progress=dict(phase='client_training'))]))
    output=capsys.readouterr().out
    assert 'no detector/traps/filtering/removal' in output
    assert 'Suspected:' not in output and 'Flagged this round:' not in output
