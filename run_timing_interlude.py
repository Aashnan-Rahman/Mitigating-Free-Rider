"""Recoverable sequential timing interlude, then restore the interrupted queue."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import psutil
from atomic_io import atomic_write_json
from segment_timing import read_rows, write_rows
from std_dagmm_recovery import exclusive_lock

ROOT = Path(__file__).resolve().parent


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def done(output, rounds):
    report = read(output/'timing_summary.json')
    path = output/('round_timings.csv' if output.name == 'ours' else 'segment_timings.csv')
    return (report.get('state') == 'completed' and report.get('completed_rounds') == rounds
            and [int(r['round']) for r in read_rows(path)] == list(range(1, rounds+1)))


def publish(job, batch, current=None, state='running', error=None):
    entries = []
    for name, method, filename in [('ours','swtcp_v15_4','round_timings.csv'),
                                    ('std','std_dagmm_native_observational','segment_timings.csv')]:
        output = batch/name
        rows = read_rows(output/filename)
        last = rows[-1] if rows else {}
        complete = done(output, job['rounds'])
        status = read(output/'status.json')
        latest = read(output/'latest_results.json').get('latest_global_metrics', {})
        progress = dict(round=len(rows), total_rounds=job['rounds'],
            working_round=status.get('round', len(rows)+1),
            phase=last.get('phase') if name=='ours' else status.get('state','queued'),
            methodology_version=method, device='cpu', active_clients=last.get('active_clients',100),
            completed_clients=status.get('completed_clients',0),
            global_accuracy=last.get('global_accuracy'), round_time_seconds=last.get('observed_round_wall_seconds'),
            fit_seconds=last.get('fit_seconds'), inference_seconds=last.get('inference_seconds'),
            suspected_clients=latest.get('num_suspected_clients'), candidate_clients=latest.get('num_candidate_clients'))
        entries.append(dict(id=name, config=dict(dataset=job.get('dataset','mnist'), distribution='noniid', attack_type='FR3',
            free_rider_pct=.4, seed=job['seed'], num_rounds=job['rounds'], methodology_version=method),
            progress=progress, completed_rounds=len(rows),
            state='completed' if complete else (state if current==name else 'pending')))
    value = dict(batch_id=batch.name, state=state, total_experiments=2,
        completed_experiments=sum(e['state']=='completed' for e in entries), failed_experiments=int(bool(error) and state=='failed'),
        total_rounds=2*job['rounds'], completed_rounds=sum(e['completed_rounds'] for e in entries),
        current_experiment=current, experiments=entries, updated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
        estimated_remaining_seconds=None, error=error)
    atomic_write_json(batch/'experiment_status.json', value)


def report(batch, job=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    job = job or read(batch/'experiment_manifest.json').get('job',{})
    dataset = 'CIFAR-10' if job.get('dataset','mnist') == 'cifar10' else 'MNIST'
    horizon = job.get('rounds',100)
    seed = job.get('seed',42)
    methods = [('Ours',read_rows(batch/'ours/round_timings.csv')),
               ('STD-DAGMM',read_rows(batch/'std/segment_timings.csv'))]
    groups = {
        'Honest training':['honest_training_seconds'], 'Fabrication':['fabrication_seconds'],
        'Client evaluation':['client_evaluation_seconds'],
        'Traps + scheduling':['trap_generation_seconds','scheduling_seconds'],
        'Features + preparation':['feature_seconds','model_preparation_seconds','preparation_seconds'],
        'Detector fitting':['fit_seconds'], 'Decision / scoring':['decision_seconds','inference_seconds'],
        'Aggregation':['aggregation_seconds'], 'Global evaluation':['evaluation_seconds'],
        'Research logs + checkpoint':['reporting_seconds','checkpoint_seconds','response_bookkeeping_seconds'],
        'Unassigned / harness':['unassigned_seconds'],
    }
    summary = []
    fig, ax = plt.subplots(figsize=(11,5.5))
    offsets = [0.,0.]
    for label, keys in groups.items():
        values = []
        for name, rows in methods:
            total = sum(sum(float(r.get(k) or 0) for k in keys) for r in rows)
            mean = total/len(rows)
            summary.append(dict(method=name, segment=label, mean_seconds=mean, total_seconds=total, measured_rounds=len(rows)))
            values.append(mean)
        ax.barh([0,1], values, left=offsets, label=label)
        offsets = [a+b for a,b in zip(offsets,values)]
    ax.set_yticks([0,1], ['Our v15.4','STD-DAGMM reproduction'])
    ax.set_xlabel(f'Measured seconds per round, amortized over {horizon} rounds')
    ax.legend(bbox_to_anchor=(1.02,1), loc='upper left', frameon=False)
    ax.set_title(f'{dataset} non-IID · FR3 40% · seed {seed} · CPU / 6 threads')
    fig.tight_layout()
    fig.savefig(batch/'segment_comparison.png', dpi=180)
    fig.savefig(batch/'segment_comparison.pdf')
    plt.close(fig)
    write_rows(batch/'segment_comparison.csv', summary)
    phase_rows = []
    ours = methods[0][1]
    for phase in dict.fromkeys(r['phase'] for r in ours):
        subset = [r for r in ours if r['phase']==phase]
        for label,keys in groups.items():
            total = sum(sum(float(r.get(k) or 0) for k in keys) for r in subset)
            phase_rows.append(dict(phase=phase, measured_rounds=len(subset), segment=label,
                conditional_mean_seconds=total/len(subset), contribution_to_full_run_mean_seconds=total/len(ours)))
    write_rows(batch/'ours_phase_segments.csv',phase_rows)
    lines = [f'# Measured {dataset} segment timing comparison','',
        f'100 clients, {horizon} rounds, non-IID, FR3 40%, seed {seed}, CPU/6 threads, three local SGD epochs.',
        'No network communication is measured. Paired sequential workflows are not a detector-only controlled speedup test.',
        'Our active-client/trap workload changes; STD retains all clients and freshly fits five epochs per round.',
        'Five epochs/reset frequency are declared reproduction choices, not settings established by Lin et al.',
        'Checkpoint/logging and unassigned harness costs are included separately, without attributing them to detection.',
        'Instrumentation CSV publication is excluded and recorded in each timing_summary.json.', '',
        '| Segment | Ours s/round | STD-DAGMM s/round |','|---|---:|---:|']
    for label in groups:
        values = [r['mean_seconds'] for r in summary if r['segment']==label]
        lines.append(f'| {label} | {values[0]:.6f} | {values[1]:.6f} |')
    from atomic_io import atomic_write_text
    atomic_write_text(batch/'README.md', '\n'.join(lines)+'\n')


def restore(job, job_path):
    active_path = ROOT/'configs/active_experiment_schedule.json'
    selected = read(active_path)
    if selected.get('priority_job') != job_path.relative_to(ROOT).as_posix():
        raise RuntimeError('Active schedule changed externally; refusing to overwrite it')
    marker = ROOT/job['paused_batch']/'STOP_REQUESTED'
    if marker.is_file():
        if marker.read_text().strip() != job['pause_marker']:
            raise RuntimeError('Pause marker changed externally; refusing to clear it')
        marker.unlink()
    # If power fails after marker clearing but before this publication, priority
    # selection still prevents the original queue from starting ahead of us.
    atomic_write_json(active_path, job['resume_schedule'])


def run(job_path):
    job = read(job_path)
    if job.get('dataset','mnist') not in ('mnist','cifar10'):
        raise ValueError('Unsupported timing dataset')
    # Validate reporting availability before starting hours of computation.
    import matplotlib
    matplotlib.use('Agg')
    batch = ROOT/job['output']
    batch.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(batch/'.runtime/interlude.lock'):
        if (batch/'STOP_REQUESTED').exists():
            raise RuntimeError('Timing interlude intentionally stopped; original queue remains paused')
        manifest = dict(job=job, experiments=[dict(id='ours'),dict(id='std')])
        prior = read(batch/'experiment_manifest.json')
        if prior and prior != manifest:
            raise RuntimeError('Timing job changed; refusing mixed results')
        atomic_write_json(batch/'experiment_manifest.json', manifest)
        paused_protocol = ROOT/job['paused_protocol']
        if hashlib.sha256(paused_protocol.read_bytes()).hexdigest() != job['paused_protocol_sha256']:
            raise RuntimeError('Interrupted experiment protocol changed')
        for name, script in [('ours','run_v154_segment_timing.py'),('std','run_std_segment_timing.py')]:
            output = batch/name
            if done(output,job['rounds']):
                continue
            minimum = float(job.get('minimum_available_gib',{}).get(name,0))
            available = psutil.virtual_memory().available/2**30
            if available < minimum:
                raise MemoryError(f'Waiting for {minimum:g} GiB available RAM for {name}; currently {available:.2f} GiB. '
                                  'Close memory-heavy apps; the recovery task will retry. Original queue remains paused.')
            # Do not overlap a worker orphaned by a crashed parent/launcher.
            for process in psutil.process_iter(['pid','cmdline']):
                try:
                    cmd = ' '.join(process.info['cmdline'] or [])
                    if str(output).lower() in cmd.lower() and any(s in cmd for s in (script,'run_std_dagmm_long.py')):
                        raise RuntimeError(f'Existing timing worker PID {process.pid}; recovery will retry')
                except (psutil.AccessDenied,psutil.NoSuchProcess):
                    continue
            output.mkdir(exist_ok=True)
            publish(job,batch,name)
            command = timing_command(job,script,output)
            with (output/'console.log').open('a',encoding='utf-8') as log:
                child = subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                while child.poll() is None:
                    publish(job,batch,name)
                    if (batch/'STOP_REQUESTED').exists():
                        for descendant in psutil.Process(child.pid).children(recursive=True):
                            descendant.terminate()
                        child.terminate()
                        child.wait(timeout=30)
                        raise RuntimeError('Timing interlude stopped; original queue remains paused')
                    time.sleep(5)
            if child.returncode or not done(output,job['rounds']):
                message = f'{name} incomplete, exit {child.returncode}; see {output}/console.log'
                publish(job,batch,name,state='failed',error=message)
                raise RuntimeError(message)
        atomic_write_json(batch/'std/latest_results.json',dict(completed=True,latest_round=job['rounds']))
        report(batch,job)
        publish(job,batch,state='completed')
        restore(job,job_path)
        print('Timing comparison complete; original baseline queue restored for immediate resumption.',flush=True)


def timing_command(job, script, output):
    return [sys.executable,str(ROOT/script),'--output',str(output),'--rounds',str(job['rounds']),
            '--seed',str(job['seed']),'--dataset',job.get('dataset','mnist')]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.job.resolve())
    except Exception as error:
        job = read(args.job.resolve())
        if job.get('output') and (ROOT/job['output']).is_dir():
            batch = ROOT/job['output']
            current = read(batch/'experiment_status.json').get('current_experiment')
            publish(job,batch,current,state='recovering' if isinstance(error,MemoryError) else 'failed',error=str(error))
        raise
