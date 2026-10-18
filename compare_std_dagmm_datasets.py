"""Save descriptive MNIST/CIFAR native-workflow timing comparison, not accuracy claims."""
import argparse
import csv
import hashlib
import io
import json
import statistics
from pathlib import Path

from atomic_io import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parent
MATCH_FIELDS = ('num_clients', 'num_rounds', 'distribution', 'seed', 'attack_type',
                'free_rider_pct', 'local_epochs', 'batch_size', 'learning_rate',
                'momentum', 'dirichlet_alpha', 'device')


def compare(mnist, cifar, output):
    reports = [json.loads((directory/'summary.json').read_text()) for directory in (mnist, cifar)]
    resources = []
    for directory, report, dataset in zip((mnist, cifar), reports, ('mnist', 'cifar10')):
        if report['state'] != 'completed' or report['protocol']['config']['dataset'] != dataset:
            raise ValueError('Both requested dataset runs must be complete')
        with (directory/'round_timings.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        if [int(row['round']) for row in rows] != list(range(1, report['completed_rounds']+1)):
            raise ValueError('Invalid round sequence')
        resources.append(dict(dataset=dataset,
            max_detector_worker_rss_mib=max(float(row['detector_peak_rss_mib']) for row in rows),
            max_training_parent_rss_mib=max(float(row['training_parent_peak_rss_mib']) for row in rows),
            minimum_system_available_mib=min(float(row['minimum_system_available_mib']) for row in rows)))
        for field in ('fit_seconds', 'inference_seconds', 'detector_seconds', 'round_compute_seconds'):
            if abs(statistics.mean(float(row[field]) for row in rows)-report['projection'][field]['mean']) > 1e-7:
                raise ValueError('Summary does not match raw timing records')
        for name, digest in report['protocol']['source_sha256'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Source changed: {name}')
    left, right = (report['protocol'] for report in reports)
    for field in MATCH_FIELDS:
        if left['config'][field] != right['config'][field]:
            raise ValueError(f'Unmatched training scenario: {field}')
    for field in ('detector_epochs', 'detector_batch', 'threads', 'flag_rule'):
        if left[field] != right[field]:
            raise ValueError(f'Unmatched detector setting: {field}')
    for source in ('benchmark_mnist_std_dagmm.py', 'comparison/std_dagmm.py'):
        if left['source_sha256'][source] != right['source_sha256'][source]:
            raise ValueError('Different detector implementation')
    output.mkdir(parents=True, exist_ok=True)
    records, lines = [], ['| Component | MNIST mean ± SD (s/round) | CIFAR-10 mean ± SD (s/round) | CIFAR/MNIST |',
                         '|---|---:|---:|---:|']
    for field in ('fit_seconds', 'inference_seconds', 'detector_seconds',
                  'baseline_compute_seconds', 'round_compute_seconds'):
        a, b = (report['projection'][field] for report in reports)
        ratio = b['mean']/a['mean']
        records.append(dict(component=field, mnist_mean_s=a['mean'], mnist_sd_s=a['sample_sd'],
            cifar10_mean_s=b['mean'], cifar10_sd_s=b['sample_sd'], cifar_to_mnist_ratio=ratio,
            mnist_projected_100_min=a['projected_100_round_seconds']/60,
            cifar10_projected_100_min=b['projected_100_round_seconds']/60))
        lines.append(f"| {field} | {a['mean']:.3f} ± {a['sample_sd']:.3f} | {b['mean']:.3f} ± {b['sample_sd']:.3f} | {ratio:.2f}× |")
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
    atomic_write_text(output/'timing_comparison.csv', stream.getvalue())
    atomic_write_json(output/'comparison.json', dict(inputs=[str(mnist), str(cifar)],
        matched_config_fields=list(MATCH_FIELDS), records=records, sampled_resources=resources,
        model_update_coordinates=dict(mnist=reports[0].get('update_dimensions',206922),
                                      cifar10=reports[1]['update_dimensions'])))
    text = '\n'.join(lines)
    atomic_write_text(output/'README.md', f'''# STD-DAGMM: MNIST versus CIFAR-10

Ten actual rounds per dataset, 100 participating clients throughout, non-IID,
seed 42, 40% FR3; 3 local epochs, 5 fresh detector epochs, CPU/6 threads.
Full update vectors, unchanged detector fitting/scoring implementation.

{text}

CSV also gives conditional 100-round projections (observed mean × 100), not
completed 100-round measurements. Fixed workload makes similar timing plausible,
not guaranteed: CPU load, RAM pressure, caches and paging may change.
MNIST and CIFAR use their respective study CNNs (206,922 versus 621,258 floating
update coordinates, including CIFAR batch-normalization buffers). This is a
dataset-plus-model workload comparison, not an isolated dataset-only effect.
Runs were sequential at different times, not randomized simultaneous controls.

Detector time includes preparation, fresh fitting/mixture finalization, scoring
and flag decisions. Combined compute adds local work, aggregation and evaluation;
it excludes process startup, matrix serialization and checkpoint writes.
Those harness costs remain separately recorded in per-round CSVs. No removals
or trap logic; all responses aggregate. Detection flags are not removal counts.
Minimum sampled system available RAM: MNIST {resources[0]['minimum_system_available_mib']:.1f} MiB;
CIFAR-10 {resources[1]['minimum_system_available_mib']:.1f} MiB. Maximum detector-worker
RSS: MNIST {resources[0]['max_detector_worker_rss_mib']:.1f} MiB; CIFAR-10
{resources[1]['max_detector_worker_rss_mib']:.1f} MiB. RSS sampling may miss peaks;
parent and worker independent peaks must not be added as simultaneous usage.
Very low available memory can cause paging and distort timing; paging itself was
not measured. These are observed workstation timings, not memory-isolated CPU costs.

Five epochs is a declared reproduction budget, not verified convergence or an
exact author-code replication. No cutoffs were retuned to either dataset.

Our method's workload can shrink after removal; compare actual full-horizon
trajectories separately, not its early-round mean × 100. No causal speedup claim
against our older runs is justified by these two timing samples alone.
''')
    print(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mnist', type=Path, default=ROOT/'analysis/std_dagmm_mnist_native_seed42_fr40_FR3_noniid')
    parser.add_argument('--cifar', type=Path, default=ROOT/'analysis/std_dagmm_cifar10_native_seed42_fr40_FR3_noniid')
    parser.add_argument('--output', type=Path, default=ROOT/'analysis/std_dagmm_dataset_timing_comparison')
    args = parser.parse_args()
    compare(args.mnist.resolve(), args.cifar.resolve(), args.output.resolve())
