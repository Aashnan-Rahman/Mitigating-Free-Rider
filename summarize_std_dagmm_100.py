"""Validate/export actual 100-round STD-DAGMM outcomes; preserve older pilots."""
import csv
import hashlib
import io
import json
from pathlib import Path
import torch
from atomic_io import atomic_write_json,atomic_write_text
from analyze_std_dagmm_native import analyze

ROOT=Path(__file__).resolve().parent


def build():
    batch=ROOT/'results/std_dagmm_100_seed42_fr40'
    records=[]
    for dataset in ('mnist','cifar10'):
        output=batch/f'std_dagmm_{dataset}_noniid_FR3_seed42'
        analyze(output)
        report=json.loads((output/'summary.json').read_text())
        checks=json.loads((output/'analysis_checks.json').read_text())
        with (output/'round_timings.csv').open(newline='') as handle:
            rows=list(csv.DictReader(handle))
        if len(rows)!=100:
            raise ValueError('Only complete 100-round records can be published')
        record=dict(dataset=dataset,rounds=100,mean_fit_s=report['projection']['fit_seconds']['mean'],
            mean_scoring_s=report['projection']['inference_seconds']['mean'],
            mean_detector_s=report['projection']['detector_seconds']['mean'],
            mean_round_compute_s=report['projection']['round_compute_seconds']['mean'],
            actual_compute_minutes=report['projection']['round_compute_seconds']['measured_total_seconds']/60,
            final_accuracy=float(rows[-1]['global_accuracy']),ever_flagged_free_riders=checks['ever_flagged_free_riders'],
            ever_flagged_honest=checks['ever_flagged_honest'],permanent_removals=0,
            detector_peak_rss_mib=checks['max_detector_worker_rss_mib'],
            minimum_system_available_mib=checks['minimum_system_available_mib'])
        records.append(record)
        # Retain only the small final global model for publication; full recovery
        # histories/checkpoints remain local and ignored rather than deleted.
        checkpoint=torch.load(output/'latest_checkpoint.pt',map_location='cpu',weights_only=False)
        if checkpoint['round']!=100 or checkpoint['protocol']!=report['protocol']:
            raise ValueError('Final checkpoint does not match completed evidence')
        torch.save(dict(round=100,global_state=checkpoint['global_state'],protocol=report['protocol']),output/'final_model.pt')
        atomic_write_json(output/'final_model_provenance.json',dict(round=100,
            sha256=hashlib.sha256((output/'final_model.pt').read_bytes()).hexdigest(),
            origin='global model from validated completed round-100 recovery checkpoint; attacker histories excluded'))
        del checkpoint
    folder=ROOT/'analysis/std_dagmm_100_round_summary'
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=list(records[0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(records)
    atomic_write_text(folder/'results.csv',stream.getvalue())
    atomic_write_json(folder/'results.json',dict(measured=True,rounds_per_dataset=100,runs=records))
    lines=['# Actual 100-round STD-DAGMM results','',
        '| Dataset | Fit s/round | Score s/round | Detector s/round | All compute s/round | Actual compute min | Final accuracy | Ever flagged FR / honest |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in records:
        lines.append(f"| {r['dataset']} | {r['mean_fit_s']:.3f} | {r['mean_scoring_s']:.3f} | {r['mean_detector_s']:.3f} | {r['mean_round_compute_s']:.3f} | {r['actual_compute_minutes']:.2f} | {100*r['final_accuracy']:.2f}% | {r['ever_flagged_free_riders']}/40 / {r['ever_flagged_honest']}/60 |")
    lines += ['', 'All totals are measured over 100 actual rounds, not extrapolated. Same non-IID FR3, seed 42, 40% setup; 100 clients remain throughout.',
        'Flags are roundwise observations, not permanent removals. All responses aggregate. Five fresh detector epochs per round are an explicit reproduction budget, not verified author-code fidelity or convergence.',
        'No FR was ever flagged and every honest client was flagged at least once in both runs. This is a limitation of this selected implementation/scenario, not a universal claim about STD-DAGMM.',
        'CIFAR encountered near-zero available RAM; paging can confound timings and was not itself measured. Compute excludes worker startup, serialization and checkpoint publication; full per-round wall timings remain in source CSVs.',
        'Earlier ten-round pilots are preserved separately. Small final models and their hashes are retained; large latest/previous recovery histories stay local and are excluded from Git.']
    atomic_write_text(folder/'README.md','\n'.join(lines)+'\n')
    print(stream.getvalue())


if __name__=='__main__':
    build()
