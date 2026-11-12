"""Validate completed records and an explicitly oracle feature-level stress test.

No live training file, detector parameter, queue or checkpoint is changed.
Norm matching rescales a nonzero fabricated delta to the honest median norm.
The layer-share profile is invariant under this positive scaling. This is a
single-cycle feature diagnostic with extra attacker information, not a new
end-to-end attack evaluation or a permanent-removal result.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))


def rows(path):
    with path.open(newline='',encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, values):
    if not values:
        return
    with path.open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(values[0]))
        writer.writeheader(); writer.writerows(values)


def file_record(path):
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def selected_at(directory, decision_round):
    selected={}; truth=set()
    signal=rows(directory/'cycle_signals.csv')
    expected=[r for r in signal if int(r['round'])==decision_round]
    # The recorded signal carries the selected observation round separately.
    lookup={(int(r['client_id']),int(r['trap_id'])):int(r['observation_round']) for r in expected}
    for r in rows(directory/'cycle_probes.csv'):
        client,trap,t=int(r['client_id']),int(r['trap_id']),int(r['round'])
        if lookup.get((client,trap)) != t:
            continue
        selected.setdefault(client,{})[trap]=dict(norm=float(r['delta_norm']),
            profile=json.loads(r['layer_profile']),round=t,sendback=bool(int(r['exact_sendback'])))
        if int(r['is_free_rider']): truth.add(client)
    if len(expected) != 2*len(selected) or any(set(pair)!={0,1} for pair in selected.values()):
        raise ValueError(f'Incomplete selected pair at {directory}:{decision_round}')
    return selected,truth,expected


def main():
    import torch
    from server.v15_certificate_memory import measurements, screen
    torch.set_num_threads(1)
    output=HERE/'generated/revision'; output.mkdir(parents=True,exist_ok=True)
    provenance=[]; completed=[]; progress=[]
    queue=json.loads((ROOT/'configs/review2_priority_queue.json').read_text())
    for name in queue['plans']:
        plan=json.loads((ROOT/name).read_text())
        batch=ROOT/plan.get('results_root','results')/plan['batch_name']
        status_path=batch/'experiment_status.json'
        if not status_path.exists():
            progress.append(dict(batch=plan['batch_name'],state='queued',completed=0,total=len(plan['experiments'])))
            continue
        status=json.loads(status_path.read_text())
        progress.append(dict(batch=plan['batch_name'],state=status['state'],
            completed=status['completed_experiments'],total=status['total_experiments'],
            current=status.get('current_experiment'),error=status.get('error'),updated=status.get('updated_at')))
        if plan.get('workflow')!='review2': continue
        for entry in status['experiments']:
            directory=batch/entry['id']; latest=directory/'latest_results.json'
            if not latest.exists() or not json.loads(latest.read_text()).get('completed'): continue
            run=json.loads((directory/'run_config.json').read_text())
            metrics=rows(directory/'global_metrics.csv')
            if run['completed_rounds']!=100 or [int(r['round']) for r in metrics]!=list(range(1,101)):
                raise ValueError(f'Incomplete completed record: {directory}')
            completed.append(dict(batch=plan['batch_name'],run=entry['id'],dataset=run['dataset'],
                split=run['distribution'],share=round(100*run['free_rider_pct']),attack=run['attack_type'],
                seed=run['seed'],tp=run['removed_free_riders'],fp=run['removed_honest_clients'],
                fn=run['missed_free_riders'],accuracy=run['final_global_accuracy']))
            provenance.extend(file_record(directory/n) for n in ['run_config.json','global_metrics.csv','removals.csv','protocol.json'])
    write_csv(output/'completed_review_runs.csv',completed)
    (output/'queue_snapshot.json').write_text(json.dumps(progress,indent=2))

    # Replay every existing FR2--FR4 initial pair, then alter only norms.
    cases=[]
    study=rows(HERE/'generated/multiseed/per_run.csv')
    for run in study:
        if run['attack']=='FR1': continue  # Zero vectors cannot be positively rescaled.
        directory=ROOT/run['source']
        selected,truth,_=selected_at(directory,20)
        active=sorted(selected)
        original=measurements(selected,active,20)
        decisions,_=screen(original,20)
        recorded={int(r['client_id']):r['strong_channels'] for r in rows(directory/'cycle_decisions.csv') if int(r['round'])==20}
        if {d['client_id']:d['strong_channels'] for d in decisions} != recorded:
            raise ValueError(f'Original paired screening does not replay exactly: {directory}')
        # Evaluation labels construct an oracle attack; they never reach screen.
        matched={c:{t:dict(value) for t,value in pair.items()} for c,pair in selected.items()}
        targets={t:median(selected[c][t]['norm'] for c in active if c not in truth) for t in (0,1)}
        for c in truth:
            for t in (0,1):
                if selected[c][t]['norm']<=0 or targets[t]<=0:
                    raise ValueError('Norm matching requires nonzero deltas')
                if not math.isclose(sum(selected[c][t]['profile']),1.,abs_tol=2e-6):
                    raise ValueError('Profile is not in the scale-invariant regime')
                matched[c][t].update(norm=targets[t],sendback=False)
        stressed,_=screen(measurements(matched,active,20),20)
        for view,results in [('stored',decisions),('norm_matched',stressed)]:
            for channel in ['norm_low','profile_high','either']:
                flagged={d['client_id'] for d in results if
                    (bool(set(filter(None,d['strong_channels'].split(','))) & {'norm_low','profile_high'}) if channel=='either'
                     else channel in d['strong_channels'].split(','))}
                cases.append(dict(dataset=run['dataset'],split=run['split'],share=int(run['share']),
                    attack=run['attack'],seed=int(run['seed']),view=view,channel=channel,
                    tp=len(flagged & truth),fp=len(flagged-truth),fn=len(truth-flagged),
                    attackers=len(truth),honest=len(active)-len(truth)))
        provenance.extend(file_record(directory/n) for n in ['cycle_probes.csv','cycle_signals.csv','cycle_decisions.csv'])
    write_csv(output/'norm_matching_cases.csv',cases)
    aggregate=[]
    for attack in ['FR2','FR3','FR4']:
        row=dict(attack=attack,cases=24)
        for view in ['stored','norm_matched']:
            for channel in ['norm_low','profile_high','either']:
                group=[r for r in cases if r['attack']==attack and r['view']==view and r['channel']==channel]
                if len(group)!=24: raise ValueError('Incomplete norm-matching grid')
                row[f'{view}_{channel}_recall']=sum(r['tp'] for r in group)/sum(r['attackers'] for r in group)
                row[f'{view}_{channel}_honest_certificates']=sum(r['fp'] for r in group)
        aggregate.append(row)
    write_csv(output/'norm_matching_summary.csv',aggregate)

    # Error case chosen by observed honest removal, not visual class separation.
    error=next(r for r in study if r['dataset']=='mnist' and r['split']=='noniid' and r['share']=='40' and r['attack']=='FR3' and r['seed']=='43')
    directory=ROOT/error['source']
    removed={int(r['client_id']) for r in rows(directory/'removals.csv') if int(r['is_free_rider'])==0}
    for round_index in [20,30]:
        _,truth,signals=selected_at(directory,round_index)
        pairs={}
        for r in signals: pairs.setdefault(int(r['client_id']),[]).append(r)
        points=[]
        for c,pair in pairs.items():
            points.append(dict(client_id=c,x=math.asinh(mean(float(r['norm_z']) for r in pair)),
                y=math.asinh(mean(float(r['profile_z']) for r in pair)),
                free_rider=int(c in truth),honest_removed=int(c in removed)))
        write_csv(output/f'honest_error_round{round_index}.csv',points)
    provenance.extend(file_record(directory/n) for n in ['cycle_signals.csv','removals.csv'])
    # v7.1's ordinary geometry panels are all seed-42 illustrations.
    honest=[r for r in completed if r['share']==0]
    summary=dict(date='2026-11-11',primary_runs=len(study),honest_only_completed=len(honest),
        honest_only_removals=sum(r['fp'] for r in honest),completed_review_runs=len(completed),
        low_share_completed=len([r for r in completed if r['share']>0]),
        norm_matching_cases=72,norm_matching=aggregate,
        endpoint='paired statistical certificates at round 20, not permanent removal',
        stress_scope='oracle feature-level positive rescaling; no full-model construction or training rerun',
        queue=progress)
    (output/'summary.json').write_text(json.dumps(summary,indent=2))
    (output/'provenance.json').write_text(json.dumps(dict(inputs=provenance,
        analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        detector_sources=json.loads((ROOT/'configs/review2_registration.json').read_text())['source_sha256']),indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k not in {'queue','norm_matching'}},indent=2))
    print(json.dumps(aggregate,indent=2))


if __name__=='__main__': main()
