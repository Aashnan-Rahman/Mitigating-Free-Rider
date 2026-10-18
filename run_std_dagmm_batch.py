"""Sequential, checkpoint-aware STD-DAGMM queue with standard watch status."""
from __future__ import annotations
import argparse
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

import psutil
from atomic_io import atomic_write_json, atomic_write_text
from std_dagmm_recovery import exclusive_lock

ROOT=Path(__file__).resolve().parent


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):
        return default


def command_for(plan,experiment,output,root=ROOT):
    args={**plan['defaults'],**{k:v for k,v in experiment.items() if k!='id'}}
    script='run_fedavg_baseline.py' if plan.get('workflow')=='fedavg_no_detection' else 'run_std_dagmm_long.py'
    command=[sys.executable,str(root/script)]
    for name,value in args.items():
        command.extend(['--'+name.replace('_','-'),str(value)])
    command.extend(['--output',str(output)])
    if (output/'protocol.json').is_file():
        command.append('--resume')
    return command


def is_complete(output,horizon):
    report=read_json(output/'summary.json',{})
    status=read_json(output/'status.json',{})
    if report.get('state')!='completed' or report.get('completed_rounds')!=horizon or status.get('state')!='completed':
        return False
    try:
        with (output/'round_timings.csv').open(newline='',encoding='utf-8') as handle:
            values=list(csv.DictReader(handle))
        return [int(r['round']) for r in values]==list(range(1,horizon+1))
    except (OSError,ValueError,KeyError):
        return False


def active_runner(batch):
    # Also wait for an orphan detector worker after its parent crashes. Otherwise
    # it might publish stale .runtime output during the recovery attempt.
    for process in psutil.process_iter(['pid','cmdline']):
        try:
            command=' '.join(process.info['cmdline'] or [])
            if any(name in command for name in ('run_std_dagmm_long.py','run_fedavg_baseline.py')) and str(batch).lower() in command.lower():
                return process.info['pid']
        except (psutil.NoSuchProcess,psutil.AccessDenied):
            continue
    return None


def make_status(plan,batch,prior=None):
    experiments=[]
    methodology='fedavg_no_detection' if plan.get('workflow')=='fedavg_no_detection' else 'std_dagmm_native_observational'
    prior=prior or {}
    for entry in plan['experiments']:
        values={**plan['defaults'],**entry}
        output=batch/entry['id']
        current=read_json(output/'status.json',{})
        last=current.get('latest_round',{})
        # The last durable CSV supplies timing context during the next round.
        if not last and (output/'round_timings.csv').is_file():
            with (output/'round_timings.csv').open(newline='',encoding='utf-8') as handle:
                samples=list(csv.DictReader(handle))
            if samples:
                last=samples[-1]
        complete=is_complete(output,values['rounds'])
        done=values['rounds'] if complete else int(current.get('completed_rounds',0))
        phase=current.get('state','queued')
        progress=dict(round=done,total_rounds=values['rounds'],working_round=current.get('round'),
            phase=phase,device='cpu',active_clients=values['clients'],
            completed_clients=current.get('completed_clients',0),
            methodology_version=methodology,
            round_time_seconds=last.get('round_compute_seconds'),
            detector_time_seconds=last.get('detector_seconds'),fit_seconds=last.get('fit_seconds'),
            inference_seconds=last.get('inference_seconds'),global_accuracy=last.get('global_accuracy'),
            flagged_clients=(int(last.get('flagged_free_riders',0))+int(last.get('flagged_honest',0))),
            process_rss_mb=last.get('training_parent_peak_rss_mib'))
        experiments.append(dict(id=entry['id'],config=dict(dataset=values['dataset'],
            distribution=values['distribution'],attack_type=values['attack'],seed=values['seed'],
            free_rider_pct=values['free_rider_pct'],num_clients=values['clients'],num_rounds=values['rounds'],
            methodology_version=methodology),completed_rounds=done,
            state='completed' if complete else 'pending',progress=progress))
    elapsed=0.
    for entry in plan['experiments']:
        path=batch/entry['id']/'round_timings.csv'
        if path.is_file():
            with path.open(newline='',encoding='utf-8') as handle:
                elapsed+=sum(float(r['observed_round_wall_seconds']) for r in csv.DictReader(handle))
    done=sum(e['completed_rounds'] for e in experiments)
    total=sum(e['config']['num_rounds'] for e in experiments)
    return dict(batch_id=plan['batch_name'],state='running',total_experiments=len(experiments),
        completed_experiments=sum(e['state']=='completed' for e in experiments),failed_experiments=0,
        completed_rounds=done,total_rounds=total,experiments=experiments,current_experiment=None,
        started_at=prior.get('started_at',datetime.now(timezone.utc).isoformat()),
        updated_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=elapsed,
        elapsed_basis='sum of recorded round wall timers, excluding downtime and checkpoint publication',
        estimated_remaining_seconds=None)


def publish(plan,batch,current_id=None,state='running',error=None):
    status=make_status(plan,batch,read_json(batch/'experiment_status.json',{}))
    status['state']=state
    status['current_experiment']=current_id
    for entry in status['experiments']:
        if entry['id']==current_id and entry['state']!='completed':
            entry['state']='running' if state=='running' else state
    if error:
        status['error']=error
    # Dataset-specific average speeds avoid using MNIST's speed for CIFAR's ETA.
    remaining=[]
    for entry in status['experiments']:
        if entry['state']=='completed':
            continue
        speed=entry['progress'].get('round_time_seconds')
        if speed in (None,''):
            remaining=None
            break
        remaining.append((entry['config']['num_rounds']-entry['completed_rounds'])*float(speed))
    status['estimated_remaining_seconds']=sum(remaining) if remaining is not None else None
    atomic_write_json(batch/'experiment_status.json',status)
    atomic_write_json(batch.parent/'experiment_status.json',status)
    return status


def finish_reports(plan,batch):
    # Read/validate final evidence, do not alter the old ten-round samples/paper.
    if plan.get('workflow')=='fedavg_no_detection':
        from analyze_fedavg_baseline import analyze_batch
        analyze_batch(plan,batch)
        return
    from analyze_std_dagmm_native import analyze
    values=[]
    for entry in plan['experiments']:
        output=batch/entry['id']
        analyze(output)
        report=read_json(output/'summary.json')
        values.append(dict(dataset=entry['dataset'],measured_rounds=report['completed_rounds'],
            mean_fit_s=report['projection']['fit_seconds']['mean'],
            mean_inference_s=report['projection']['inference_seconds']['mean'],
            mean_detector_s=report['projection']['detector_seconds']['mean'],
            mean_compute_s=report['projection']['round_compute_seconds']['mean'],
            actual_compute_total_s=report['projection']['round_compute_seconds']['measured_total_seconds']))
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=list(values[0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(values)
    atomic_write_text(batch/'actual_100_round_comparison.csv',stream.getvalue())
    atomic_write_json(batch/'actual_100_round_comparison.json',dict(measured=True,runs=values))


def run(plan_path,poll_seconds=5):
    plan=read_json(plan_path)
    if not plan or len({e['id'] for e in plan['experiments']})!=len(plan['experiments']):
        raise ValueError('A valid queue with unique run IDs is required')
    results=Path(plan['results_root'])
    if not results.is_absolute():
        results=ROOT/results
    batch=results/plan['batch_name']
    batch.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(batch/'.runtime/batch.lock'):
        if (batch/'STOP_REQUESTED').exists():
            publish(plan,batch,state='stopped')
            return
        manifest={k:v for k,v in plan.items() if k!='auto_resume'}
        existing=read_json(batch/'experiment_manifest.json')
        if existing is not None and existing!=manifest:
            raise ValueError('Frozen batch manifest changed; refusing a mixed run')
        atomic_write_json(batch/'experiment_manifest.json',manifest)
        orphan=active_runner(batch.resolve())
        if orphan:
            print(f'Existing native parent/worker PID {orphan}; no duplicate started',flush=True)
            return
        if all(is_complete(batch/e['id'],plan['defaults']['rounds']) for e in plan['experiments']):
            report_name='baseline_comparison.csv' if plan.get('workflow')=='fedavg_no_detection' else 'actual_100_round_comparison.csv'
            if not (batch/report_name).exists():
                finish_reports(plan,batch)
            publish(plan,batch,state='completed')
            return
        for entry in plan['experiments']:
            output=batch/entry['id']
            if is_complete(output,plan['defaults']['rounds']):
                continue
            if (batch/'STOP_REQUESTED').exists():
                publish(plan,batch,state='stopped')
                return
            output.mkdir(exist_ok=True)
            publish(plan,batch,entry['id'])
            command=command_for(plan,entry,output)
            print('Starting/resuming '+entry['id'],flush=True)
            with (output/'console.log').open('a',encoding='utf-8') as log:
                child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                try:
                    while child.poll() is None:
                        publish(plan,batch,entry['id'])
                        if (batch/'STOP_REQUESTED').exists():
                            # Stop the detector worker as well as its parent.
                            parent=psutil.Process(child.pid)
                            for descendant in parent.children(recursive=True):
                                descendant.terminate()
                            child.terminate()
                            child.wait(timeout=30)
                            publish(plan,batch,state='stopped')
                            return
                        time.sleep(poll_seconds)
                except BaseException:
                    # A live orphan is detected on the next recovery invocation.
                    publish(plan,batch,entry['id'],state='recovering')
                    raise
            if child.returncode or not is_complete(output,plan['defaults']['rounds']):
                publish(plan,batch,entry['id'],state='recovering',error=f'Runner exit {child.returncode}; watchdog will retry; see {output}/console.log')
                raise RuntimeError('Current run incomplete; later runs will not start')
            publish(plan,batch)
        finish_reports(plan,batch)
        publish(plan,batch,state='completed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=ROOT/'configs/std_dagmm_100_queue.json')
    parser.add_argument('--poll-seconds',type=float,default=5)
    args=parser.parse_args()
    try:
        run(args.plan.resolve(),max(.2,args.poll_seconds))
    except BlockingIOError:
        print('Recovery launcher already active; duplicate skipped',flush=True)
