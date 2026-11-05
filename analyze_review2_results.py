"""Report completed review results; missing runs are never imputed.

MAD screening is observational on round-20 ordinary responses of the passive
ablation, before any permanent removal. Its nominal lower-tail alpha=.01 is
preregistered, not selected from outcomes. Gaussian consistency is a scale
convention, not a guarantee of false-positive control on federated updates.
"""
import argparse
import csv
import json
import math
from pathlib import Path
from statistics import median, NormalDist

from atomic_io import atomic_write_json, atomic_write_text


def mad_flags(norms, alpha=.01):
    center=median(norms.values())
    mad=median(abs(v-center) for v in norms.values())
    scale=mad/NormalDist().inv_cdf(.75)
    if scale == 0:
        return set()
    cutoff=NormalDist().inv_cdf(alpha)
    return {client for client,value in norms.items() if (value-center)/scale < cutoff}


def analyze(batch):
    manifest=json.loads((batch/'experiment_manifest.json').read_text())
    rows=[]; diagnostics=[]
    for entry in manifest['experiments']:
        output=batch/entry['id']
        latest_path=output/'latest_results.json'
        if not latest_path.exists() or not json.loads(latest_path.read_text()).get('completed'):
            continue
        run=json.loads((output/'run_config.json').read_text())
        rows.append(dict(id=entry['id'], variant=entry['variant'],
            dataset=run['dataset'], distribution=run['distribution'],
            attack=run['attack_type'], share=run['free_rider_pct'], seed=run['seed'],
            completed_rounds=run['completed_rounds'],
            removed_free_riders=run.get('removed_free_riders'),
            removed_honest_clients=run.get('removed_honest_clients'),
            missed_free_riders=run.get('missed_free_riders'),
            final_accuracy=run['final_global_accuracy'],
            interpretation='label-aware utility reference, not detector performance' if entry['variant']=='oracle' else 'permanent-removal outcome'))
        if entry['variant'] == 'passive':
            with (output/'client_metrics.csv').open(newline='') as handle:
                selected=[r for r in csv.DictReader(handle) if int(r['round'])==20]
            if len(selected) != run['num_clients'] or any(int(r['was_trapped']) for r in selected):
                raise ValueError('Round-20 MAD baseline requires the complete ordinary-response population')
            norms={int(r['client_id']):float(r['delta_norm']) for r in selected}
            flags=mad_flags(norms)  # No labels reach screening.
            truth={int(r['client_id']) for r in selected if int(r['is_free_rider'])}
            tp=len(flags & truth); fp=len(flags-truth); fn=len(truth-flags)
            diagnostics.append(dict(id=entry['id'], round=20, nominal_lower_tail_alpha=.01,
                tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,
                recall=tp/len(truth) if truth else None,
                endpoint='round-20 observational flags, not confirmed permanent removals'))
    atomic_write_json(batch/'review_summary.json',dict(completed=len(rows),
        planned=len(manifest['experiments']), outcomes=rows, mad_diagnostics=diagnostics,
        caveat='Never pool oracle exclusions with detections; flags and permanent removals have different endpoints.'))
    return rows,diagnostics


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch',type=Path)
    args=parser.parse_args()
    rows,diagnostics=analyze(args.batch)
    print(f'{len(rows)} completed runs; {len(diagnostics)} MAD diagnostics')
