"""CIFAR timing selection, report metadata and resource-wait recovery."""
from argparse import Namespace
import json
from pathlib import Path

import pytest

from atomic_io import atomic_write_json
from segment_timing import write_rows


@pytest.mark.parametrize('dataset',['mnist','cifar10'])
def test_both_methods_use_the_same_dataset_and_workload(tmp_path,dataset):
    from run_v154_segment_timing import timing_config
    from run_std_segment_timing import configure_args
    from run_timing_interlude import timing_command
    cfg=timing_config(dataset,tmp_path/'ours')
    cfg.validate()
    args=configure_args(Namespace(dataset=dataset,output=tmp_path/'std',rounds=100,seed=42))
    assert cfg.dataset==args.dataset==dataset
    assert cfg.distribution==args.distribution=='noniid'
    assert cfg.attack_type==args.attack=='FR3'
    assert cfg.free_rider_pct==args.free_rider_pct==.4
    assert cfg.num_clients==args.clients==100 and cfg.num_rounds==args.rounds==100
    assert cfg.local_epochs==args.local_epochs==3 and cfg.seed==args.seed==42
    assert cfg.device=='cpu' and args.threads==6 and args.detector_epochs==5
    for script in ('run_v154_segment_timing.py','run_std_segment_timing.py'):
        cmd=timing_command(dict(dataset=dataset,rounds=100,seed=42),script,tmp_path/'output')
        assert cmd[cmd.index('--dataset')+1]==dataset


def test_default_job_remains_mnist(tmp_path):
    from run_timing_interlude import timing_command
    cmd=timing_command(dict(rounds=100,seed=42),'runner.py',tmp_path)
    assert cmd[-2:]==['--dataset','mnist']


def test_cifar_watch_and_report_labels_are_not_mnist(tmp_path):
    from run_timing_interlude import publish, report
    batch=tmp_path/'cifar'
    batch.mkdir()
    (batch/'ours').mkdir()
    (batch/'std').mkdir()
    job=dict(dataset='cifar10',rounds=2,seed=42)
    for name,file in [('ours','round_timings.csv'),('std','segment_timings.csv')]:
        write_rows(batch/name/file,[dict(round=i,phase='warmup',honest_training_seconds=1.,
            observed_round_wall_seconds=1.,global_accuracy=.5) for i in (1,2)])
    publish(job,batch,'ours')
    state=json.loads((batch/'experiment_status.json').read_text())
    assert all(e['config']['dataset']=='cifar10' for e in state['experiments'])
    report(batch,job)
    text=(batch/'README.md').read_text()
    assert 'CIFAR-10' in text and '2 rounds' in text and 'MNIST' not in text
    assert (batch/'segment_comparison.pdf').stat().st_size>0
    assert (batch/'segment_comparison.csv').is_file()


def test_low_ram_waits_before_launch_and_keeps_original_pause(tmp_path,monkeypatch):
    import run_timing_interlude as controller
    import hashlib
    monkeypatch.setattr(controller,'ROOT',tmp_path)
    protocol=tmp_path/'paused/protocol.json'
    protocol.parent.mkdir()
    protocol.write_text('{}')
    marker=protocol.parent/'STOP_REQUESTED'
    marker.write_text('owned pause')
    job=dict(dataset='cifar10',output='results/timing',rounds=100,seed=42,
        paused_protocol='paused/protocol.json',paused_protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
        minimum_available_gib=dict(ours=2,std=5))
    job_path=tmp_path/'job.json'
    atomic_write_json(job_path,job)
    monkeypatch.setattr(controller.psutil,'virtual_memory',lambda:Namespace(available=1*2**30))
    monkeypatch.setattr(controller.subprocess,'Popen',lambda *a,**k:pytest.fail('Must not launch under memory pressure'))
    with pytest.raises(MemoryError,match='Waiting for 2 GiB'):
        controller.run(job_path)
    assert marker.read_text()=='owned pause'
