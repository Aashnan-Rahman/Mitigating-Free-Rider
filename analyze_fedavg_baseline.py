"""Validate unfiltered FedAvg baseline records and export all 16 outcomes."""
import csv
import hashlib
import io
import json
from pathlib import Path
from atomic_io import atomic_write_json,atomic_write_text

ROOT=Path(__file__).resolve().parent


def read_rows(path):
    with path.open(newline='',encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def analyze_batch(plan,batch):
    results=[]
    for entry in plan['experiments']:
        output=batch/entry['id']
        summary=json.loads((output/'summary.json').read_text())
        cfg=summary['protocol']['config']
        rounds,clients=cfg['num_rounds'],cfg['num_clients']
        if summary['state']!='completed' or summary['completed_rounds']!=rounds or summary['detection_enabled']:
            raise ValueError('Unfinished or detecting baseline cannot be published')
        for name,digest in summary['protocol']['source_sha256'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
                raise ValueError(f'Baseline source changed: {name}')
        timings=read_rows(output/'round_timings.csv')
        if [int(r['round']) for r in timings]!=list(range(1,rounds+1)):
            raise ValueError('Incomplete round sequence')
        for row in timings:
            if int(row['active_clients'])!=clients or int(row['num_aggregated'])!=clients:
                raise ValueError('Baseline filtered clients')
            if any(float(row[key])!=0 for key in ('num_trapped','permanent_removals','detector_seconds','fit_seconds','decision_seconds')):
                raise ValueError('Unexpected detection, traps or removal')
        local=read_rows(output/'client_metrics.csv')
        if len(local)!=rounds*clients or {(int(r['round']),int(r['client_id'])) for r in local}!={(r,c) for r in range(1,rounds+1) for c in range(clients)}:
            raise ValueError('Incomplete client grid')
        if any(int(row['was_aggregated'])!=1 or int(row['was_trapped'])!=0 for row in local):
            raise ValueError('Baseline excluded a contribution')
        if not (output/'final_model.pt').is_file():
            raise ValueError('Missing final model')
        record=dict(run=entry['id'],dataset=cfg['dataset'],distribution=cfg['distribution'],
            attack_type=cfg['attack_type'],free_rider_pct=cfg['free_rider_pct'],measured_rounds=rounds,
            final_accuracy=summary['final_accuracy'],final_loss=summary['final_loss'],
            mean_compute_seconds=summary['mean_compute_seconds'],
            total_compute_seconds=summary['measured_total_compute_seconds'],
            max_parent_rss_mib=max(float(r['training_parent_peak_rss_mib']) for r in timings))
        results.append(record)
        atomic_write_json(output/'analysis_checks.json',dict(validated_rounds=rounds,validated_client_rows=len(local),
            detection_enabled=False,all_responses_aggregated=True,
            final_model_sha256=hashlib.sha256((output/'final_model.pt').read_bytes()).hexdigest()))
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=list(results[0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(results)
    atomic_write_text(batch/'baseline_comparison.csv',stream.getvalue())
    atomic_write_json(batch/'baseline_comparison.json',dict(runs=results,all_measured=True,detection_enabled=False))
