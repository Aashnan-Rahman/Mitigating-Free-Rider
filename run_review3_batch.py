"""Operational supervisor for frozen review2 and separately registered Block B.

Original manifests and worker source hashes are preserved byte-for-byte. The
relaxed launch guard is separate from scientific registration/checkpoints.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import time
import psutil
import run_review2_batch as frozen
from atomic_io import atomic_write_json
from std_dagmm_recovery import exclusive_lock

ROOT=Path(__file__).resolve().parent

def is_block_b(path):
    return path.relative_to(ROOT).as_posix() in frozen.read(ROOT/'configs/review3_registration.json',{}).get('plan_sha256',{})

def check_registration(path):
    if not is_block_b(path):
        frozen.check_registration(path)
        return
    reg=frozen.read(ROOT/'configs/review3_registration.json')
    for name,digest in {**reg['plan_sha256'],**reg['source_sha256']}.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Block B registration changed: '+name)
    # Block B may not silently alter the historical engine either.
    old=frozen.read(ROOT/'configs/review2_registration.json')
    for name,digest in old['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen review2 source changed: '+name)

def validate(path,plan):
    if not is_block_b(path):
        frozen.validate_plan(plan)
    elif plan.get('analysis_job'):
        if len(plan['experiments'])!=1: raise ValueError('Analysis job requires one entry')
    elif plan.get('lin_validation'):
        if len(plan['experiments'])!=2 or any(e['config']['global_eta'] not in {.3,1.} for e in plan['experiments']):
            raise ValueError('Unexpected Lin validation grid')
    else:
        from review3_config import BlockBConfig
        ids=[e['id'] for e in plan['experiments']]
        if len(set(ids))!=len(ids) or any(Path(i).name!=i or i in {'.','..'} for i in ids):
            raise ValueError('Unsafe/duplicate run names')
        for e in plan['experiments']:
            if e['variant']!='paired': raise ValueError('Block B uses declared paired arms')
            BlockBConfig(**{**plan['defaults'],**e['config']}).validate()
    check_registration(path)

def launch_requirement(dataset,settings):
    value=float(settings['minimum_available_gib'].get(dataset,1.0))
    if not .25<=value<=8: raise ValueError('Operational headroom outside .25..8 GiB')
    return int(value*2**30)

def worker(path,plan,batch,entry):
    check_registration(path)
    if not is_block_b(path): return frozen.worker(plan,batch,entry)
    output=batch/entry['id']; output.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(output/'.runtime/worker.lock'):
        if plan.get('analysis_job'):
            from review3_analysis import run
            return run(plan,output)
        if plan.get('lin_validation'):
            from run_lin_std_validation import run
            return run(plan,output,entry)
        from review3_config import BlockBConfig
        from train_review3 import run_experiment
        cfg=BlockBConfig(**{**plan['defaults'],**entry['config'],'output_dir':str(batch),'run_name':entry['id']})
        if frozen.complete(output,cfg.num_rounds): return
        if (output/'latest_checkpoint.pt').exists(): cfg.resume_checkpoint=str(output/'latest_checkpoint.pt')
        return run_experiment(cfg,variant=entry['variant'])

def run(path):
    plan=frozen.read(path);validate(path,plan)
    batch=ROOT/plan.get('results_root','results')/plan['batch_name'];batch.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(batch/'.runtime/batch.lock'):
        expected=frozen.snapshot(plan)
        if is_block_b(path):
            reg=frozen.read(ROOT/'configs/review3_registration.json')
            expected['block_b_source_sha256']=reg['source_sha256']
        manifest=batch/'experiment_manifest.json'
        if manifest.exists() and frozen.read(manifest)!=expected:
            raise ValueError('Manifest mismatch; refusing mixed evidence')
        atomic_write_json(manifest,expected)
        for entry in plan['experiments']:
            horizon={**plan['defaults'],**entry['config']}['num_rounds']
            output=batch/entry['id']
            if frozen.complete(output,horizon): continue
            if (batch/'STOP_REQUESTED').exists():
                frozen.publish(plan,batch,state='stopped');return
            settings=frozen.read(ROOT/'configs/review3_resources.json')
            requirement=launch_requirement({**plan['defaults'],**entry['config']}['dataset'],settings)
            while psutil.virtual_memory().available<requirement:
                frozen.publish(plan,batch,entry['id'],state='waiting_resources',
                               error=f'Waiting for {requirement/2**30:g} GiB available RAM before launch')
                if (batch/'STOP_REQUESTED').exists():
                    frozen.publish(plan,batch,state='stopped');return
                time.sleep(settings['poll_seconds'])
            output.mkdir(parents=True,exist_ok=True)
            with (output/'console.log').open('a',encoding='utf-8') as log:
                child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--plan',str(path),'--worker',entry['id']],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                while child.poll() is None:
                    frozen.publish(plan,batch,entry['id']);time.sleep(settings['poll_seconds'])
            if child.returncode or not frozen.complete(output,horizon):
                frozen.publish(plan,batch,entry['id'],state='recovering',error=f'Worker exit {child.returncode}; retry checkpoint, successors blocked')
                raise RuntimeError('Incomplete run '+entry['id'])
        if not plan.get('analysis_job') and not plan.get('lin_validation'):
            from analyze_review2_results import analyze
            analyze(batch)
        frozen.publish(plan,batch,state='completed')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--worker');p.add_argument('--validate-only',action='store_true');args=p.parse_args()
    path=args.plan.resolve();plan=frozen.read(path);validate(path,plan)
    if args.validate_only: print(plan['batch_name'],len(plan['experiments']),'validated')
    elif args.worker: worker(path,plan,ROOT/plan.get('results_root','results')/plan['batch_name'],next(e for e in plan['experiments'] if e['id']==args.worker))
    else: run(path)
