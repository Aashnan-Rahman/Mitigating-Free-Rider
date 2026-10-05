"""Summarize the completed, matched-seed v12 40% experiments."""
import csv
import json
import statistics
from pathlib import Path

from analyze_cifar_results import read_csv, summarize_run, markdown_table


def main():
    batches = [
        Path('results/v12_cifar10_iid_fr40_seed42'),
        Path('results/v12_cifar10_noniid_fr40_seed42'),
        Path('results/v12_mnist_noniid_then_iid_fr40_seed42'),
    ]
    rows, false_removals = [], []
    for batch in batches:
        manifest = json.loads((batch / 'experiment_manifest.json').read_text())
        for experiment in manifest['experiments']:
            run = batch / experiment['id']
            config = json.loads((run / 'run_config.json').read_text())
            latest = json.loads((run / 'latest_results.json').read_text())
            assert latest['completed'], f'Incomplete run: {run}'
            assert config['seed'] == 42 and config['free_rider_pct'] == 0.4
            assert config['methodology_version'] == 'swtcp_v12'
            row = {'dataset': config['dataset'], **summarize_run(run)}
            assert row['rounds'] == 100
            removals = read_csv(run / 'removals.csv')
            assert len({r['client_id'] for r in removals}) == len(removals)
            assert sum(int(r['is_free_rider']) for r in removals) == row['removed_free_riders']
            assert sum(1-int(r['is_free_rider']) for r in removals) == row['removed_honest_clients']
            row['final_candidates'] = config.get('final_candidate_clients')
            row['final_suspected'] = config.get('final_suspected_clients')
            rows.append(row)
            for removal in removals:
                if removal['is_free_rider'] == '0':
                    false_removals.append(f"- {config['dataset']} {config['distribution']} {config['attack_type']}: client {removal['client_id']}, round {removal['round']}; {removal}.")
    assert len(rows) == 16
    output = Path('results/analytics_v12_fr40_seed42')
    output.mkdir(exist_ok=True)
    with (output / 'summary.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = ['# v12 40% results, seed 42', '',
              'All 16 runs completed 100 rounds with 100 clients, 40 free riders, and seed 42. Non-IID uses Dirichlet alpha 0.5. Removal counts were cross-checked against unique client IDs in the event logs.', '']
    for dataset in ('mnist', 'cifar10'):
        subset = sorted([r for r in rows if r['dataset'] == dataset], key=lambda r: (r['distribution'], r['attack']))
        report += [f'## {dataset.upper()}', '', markdown_table(subset), '']
        for distribution in ('iid', 'noniid'):
            group = [r for r in subset if r['distribution'] == distribution]
            report.append(f"- {distribution}: mean final accuracy {100*statistics.fmean(r['final_accuracy'] for r in group):.2f}%; mean removal F1 {100*statistics.fmean(r['f1'] for r in group):.2f}%; honest removals {sum(r['removed_honest_clients'] for r in group)}; summed round time {sum(r['metric_wall_hours'] for r in group):.2f} hours.")
        report += ['', 'Non-IID minus IID final accuracy (percentage points):', '']
        for attack in ('FR1', 'FR2', 'FR3', 'FR4'):
            pair = {r['distribution']: r for r in subset if r['attack'] == attack}
            report.append(f"- {attack}: {100*(pair['noniid']['final_accuracy']-pair['iid']['final_accuracy']):+.2f} pp.")
        report.append('')
    report += ['## False removals', '', *(false_removals or ['None.']), '',
               '## Interpretation', '',
               f"Across runs, {sum(r['removed_free_riders'] for r in rows)} free-rider instances were removed; {sum(r['missed_free_riders'] for r in rows)} were missed. These are repeated experiment instances, not distinct real users.", '',
               'Removal precision/recall do not measure temporary false flags or exclusion from aggregation. Final candidate and suspect counts are included in summary.csv. Single-seed results do not establish statistical robustness, and no no-attack baseline is included. Runtime sums use per-round timings and exclude setup overhead; device speed cannot be inferred from comparisons with different free-rider percentages.', '']
    (output / 'REPORT.md').write_text('\n'.join(report), encoding='utf-8')
    print('\n'.join(report))


if __name__ == '__main__':
    main()
