"""Validate and summarize independent dataset timing samples, no Torch allocation."""
import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

from atomic_io import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parent


def csv_rows(path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def analyze(out):
    summary = json.loads((out/'summary.json').read_text())
    status = json.loads((out/'status.json').read_text())
    protocol = summary['protocol']
    count, clients = protocol['config']['num_rounds'], protocol['config']['num_clients']
    measured_horizon = count == 100
    recoverable = 'run_std_dagmm_long.py' in protocol['source_sha256']
    if summary['state'] != 'completed' or status['state'] != 'completed':
        raise ValueError('Cannot report an unfinished run as complete')
    for name, expected in protocol['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Recorded implementation changed: {name}')
    rows = csv_rows(out/'round_timings.csv')
    flags = csv_rows(out/'client_flags.csv')
    if [int(r['round']) for r in rows] != list(range(1,count+1)):
        raise ValueError('Incomplete or duplicate timing rounds')
    for row in rows:
        current = [r for r in flags if r['round'] == row['round']]
        if len(current) != clients or {int(r['client_id']) for r in current} != set(range(clients)):
            raise ValueError('Incomplete client flags')
        values = [float(r['energy']) for r in current]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Nonfinite scores')
        mean = statistics.mean(values)
        threshold = mean+statistics.pstdev(values)
        for r in current:
            if not math.isclose(float(r['threshold']), threshold, rel_tol=1e-8, abs_tol=1e-8):
                raise ValueError('Flag threshold differs from the recorded fixed rule')
            if int(r['flagged']) != int(float(r['energy']) > float(r['threshold'])):
                raise ValueError('Flags differ from energy scores')
        for flag, key in ((1,'flagged_free_riders'),(0,'flagged_honest')):
            if sum(int(r['flagged']) for r in current if int(r['is_free_rider']) == flag) != int(row[key]):
                raise ValueError('Evaluation counts differ from client flags')
    projection = summary['projection']
    fields = [('preparation_seconds','Update preparation'), ('fit_seconds','Detector fit + mixture finalization'),
        ('inference_seconds','Scoring'), ('decision_seconds','Flag decision'),
        ('detector_seconds','All detector work'), ('baseline_compute_seconds','Other measured simulator compute'),
        ('round_compute_seconds','Combined measured compute')]
    total_label = 'Measured 100 rounds (min)' if measured_horizon else 'Estimated 100 rounds (min)'
    table = [f'| Component | Mean s/round | Sample SD | Range (s) | CV | {total_label} |',
             '|---|---:|---:|---:|---:|---:|']
    for field, title in fields:
        item = projection[field]
        if measured_horizon and not math.isclose(sum(float(r[field]) for r in rows),item['measured_total_seconds'],rel_tol=1e-9):
            raise ValueError('Measured total does not match all 100 actual rounds')
        total = item['measured_total_seconds'] if measured_horizon else item['projected_100_round_seconds']
        table.append(f"| {title} | {item['mean']:.4f} | {item['sample_sd']:.4f} | "
            f"{item['minimum']:.4f}–{item['maximum']:.4f} | {100*item['coefficient_of_variation']:.1f}% | "
            f"{total/60:.2f} |")
    ever_fr = {int(r['client_id']) for r in flags if int(r['flagged']) and int(r['is_free_rider'])}
    ever_h = {int(r['client_id']) for r in flags if int(r['flagged']) and not int(r['is_free_rider'])}
    audit = dict(validated_rounds=count, clients_per_round=clients,
        ever_flagged_free_riders=len(ever_fr), ever_flagged_honest=len(ever_h),
        last_round_flagged_free_riders=int(rows[-1]['flagged_free_riders']),
        last_round_flagged_honest=int(rows[-1]['flagged_honest']),
        max_detector_worker_rss_mib=max(float(r['detector_peak_rss_mib']) for r in rows),
        max_simulator_parent_rss_mib=max(float(r['training_parent_peak_rss_mib']) for r in rows),
        minimum_system_available_mib=min(float(r['minimum_system_available_mib']) for r in rows),
        first3_fit_mean=statistics.mean(float(r['fit_seconds']) for r in rows[:3]),
        last3_fit_mean=statistics.mean(float(r['fit_seconds']) for r in rows[-3:]))
    cfg = protocol['config']
    # This is context from a completed native workflow, not a timed paired arm.
    dataset = cfg['dataset']
    dimensions = summary.get('update_dimensions', 206922 if dataset == 'mnist' else None)
    if dimensions is None:
        raise ValueError('Missing full-update dimensions')
    historical = ROOT/f"results/v15_4_{dataset}_seed{cfg['seed']}_fr{round(100*cfg['free_rider_pct'])}/v15_4_{dataset}_{cfg['distribution']}_{cfg['attack_type']}_seed{cfg['seed']}"
    context = 'No matching completed historical v15.4 execution was available.'
    if (historical/'latest_results.json').is_file() and json.loads((historical/'latest_results.json').read_text()).get('completed'):
        metrics = csv_rows(historical/'global_metrics.csv')
        old = json.loads((historical/'run_config.json').read_text())
        elapsed = sum(float(r['round_time_seconds']) for r in metrics)
        context = (f"Historical v15.4, same dataset/partition/seed/attacker share/type: {len(metrics)} actual rounds, "
            f"mean logged full-round time {elapsed/len(metrics):.2f} s, summed logged rounds {elapsed/60:.2f} min. "
            f"It removed {old['removed_free_riders']} free riders and {old['removed_honest_clients']} honest clients by its full horizon. "
            "These are older, separately executed native runs, NOT an isolated detector-overhead control. "
            "Our protocol changes probing/aggregation/client count, while this baseline keeps 100 clients; "
            "host load, memory pressure and logged timer boundaries also differ. Do not interpret their ratio as a causal speedup. "
            "Roundwise flags and permanent removals remain different outcomes, even at an equal horizon.")
        audit['historical_ours_context'] = dict(mean_logged_round_s=elapsed/len(metrics),
            summed_logged_round_s=elapsed, measured_rounds=len(metrics))
    horizon_note = ("The 100-round totals are sums of **100 actually executed rounds**, not extrapolations. "
                    "Mean seconds per round is that measured total divided by 100."
                    if measured_horizon else
                    "The 100-round estimate is **100 times the observed per-round mean**, conditional on "
                    "unchanged client count/model/epochs/device/load. It is NOT a completed 100-round run.")
    recovery_note = ("This run is part of the persistent startup/logon/watchdog queue. An interrupted "
                     "round replays from the last completed checkpoint; a previous-checkpoint fallback is retained."
                     if recoverable else
                     "This one-off benchmark is NOT registered with the Windows startup scheduler.")
    runner_name = 'run_std_dagmm_long.py' if recoverable else 'run_std_dagmm_native.py'
    text = f"""# Independent STD-DAGMM {dataset.upper()} timing sample

Completed **{count} real federated rounds**: {dataset.upper()} {cfg['distribution']}, seed {cfg['seed']},
{clients} clients, {100*cfg['free_rider_pct']:.0f}% {cfg['attack_type']} free riders, CPU,
{protocol['threads']} PyTorch threads. Each honest client performs {cfg['local_epochs']} local SGD epochs;
the detector is freshly fitted for {protocol['detector_epochs']} epochs each round.

## Measured timing and explicitly projected cost

{chr(10).join(table)}

Added detector work / other measured same-trajectory compute:
**{projection['added_detector_time_percent_of_same_trajectory_baseline']:.2f}%**.
Detector fraction of their combined measured compute:
**{projection['detector_fraction_of_instrumented_compute_percent']:.2f}%**.
These are different denominators. The baseline component is the sum of measured
client work, fabrication, aggregation and evaluation in this trajectory, NOT a
separate no-detector control run. Observed wall time additionally includes worker
startup, matrix serialization and other instrumentation; those costs are retained
per round but excluded from the computational projection. Checkpoint publication
happens after that round timer and is not included in compute totals/projections.

{horizon_note}
Neither measured totals nor projections constitute a confidence interval,
proof of converged-model detection, or a guarantee of constant late-round cost.
Ranges/SD/CV expose observed variation. Mean fitting time in the first three
rounds was {audit['first3_fit_mean']:.2f} s; in the last three it was {audit['last3_fit_mean']:.2f} s.

## Memory and flags

- Maximum sampled detector-worker RSS: **{audit['max_detector_worker_rss_mib']:.1f} MiB**.
- Maximum sampled simulator-parent RSS: **{audit['max_simulator_parent_rss_mib']:.1f} MiB**.
- Minimum system available memory in recorded samples: **{audit['minimum_system_available_mib']:.1f} MiB**.
- Distinct clients ever flagged: **{len(ever_fr)} free riders**, **{len(ever_h)} honest**.
- Last-round flags: **{audit['last_round_flagged_free_riders']} free riders**, **{audit['last_round_flagged_honest']} honest**.
- Permanent removals: **none**, by design. Flags do not become an invented removal rule.

RSS is sampled every 20 ms, not exact allocator accounting; short peaks can be
missed. Parent/worker peak values must NOT simply be added as though their peaks
occurred simultaneously. No paging or energy-consumption measurements were made.

## Native detection workflow and fidelity limits

Ordinary global model -> local client training/fabrication -> flattened updates ->
STD-DAGMM fitting -> energy flags -> ordinary unfiltered FedAvg. **No traps,
warmup, paired comparisons, our z/profile nomination, quarantine or confirmation**
are applied. Reusing shared model/data/SGD/seed utilities does not run our detector.
The worker receives only the full update matrix and fitting settings. Evaluation
labels are joined after flags are final, never used for thresholds or fitting.
The one-sided flag rule is energy > population mean + one population SD; it
does not use known attacker prevalence or a quota.

This is a **paper-guided reproduction**, not original author code or a claimed
exact published experiment. The underlying external {dataset.upper()}/SGD/{cfg['attack_type']} scenario is
matched to our study, not substituted with a paper's different dataset/model.
Widths 128/64/32, K=3 and loss weights .1/.005 follow FRIDA's STD-DAGMM description.
Fresh initialization, five detector epochs, Adam .001, batch size 20, clipping 5,
covariance ridge 1e-6, float64 small-mixture math and the symmetric decoder are
declared choices where the full original recipe is not verified. Inputs are full
{dimensions:,}-coordinate float32 updates; there is no few-scalar proxy or projection.
Five epochs is a budget, NOT proof of convergence. Poor flags here must not be
generalized to every STD-DAGMM implementation or horizon. No thresholds were
retuned to these results. Per-round reconstruction/energy losses remain in the
detector JSON/logs for review.

References: [STD-DAGMM](https://arxiv.org/pdf/1911.12560),
[FRIDA baseline description](https://arxiv.org/html/2410.05020v2).

## Context for comparison with our native method

{context}

## Evidence and reproducibility

`protocol.json` records settings, independent seed streams and executed source
hashes. `round_timings.csv` and `client_flags.csv` retain every round/client;
`detector_round_XX.json`/`.log` retain detailed fitting/score measurements.
`summary.json` retains measured totals (100-round runs) or explicit projections
(short samples); `analysis_checks.json` records
independent verification of all rounds, flags and source hashes. Existing FL
results and our detector implementation are unchanged. Protocol checks validate
the round/client grid, score-based flags and frozen source hashes.

Reproduce with a NEW output directory:

```powershell
.\\.venv\\Scripts\\python.exe {runner_name} --dataset {dataset} --rounds {count} --clients {clients} --distribution {cfg['distribution']} --attack {cfg['attack_type']} --free-rider-pct {cfg['free_rider_pct']} --seed {cfg['seed']} --threads {protocol['threads']} --detector-epochs {protocol['detector_epochs']} --detector-batch {protocol['detector_batch']} --local-epochs {cfg['local_epochs']} --output analysis/std_dagmm_{dataset}_native_repeat
```

Interrupted runs can be continued by repeating the exact original command with
`--resume`; checkpointed client-loader/attack RNGs and history are restored.
{recovery_note}
The ignored checkpoint and transient matrix are runtime state, not final evidence.
"""
    atomic_write_text(out/'README.md', text)
    atomic_write_json(out/'analysis_checks.json', audit)
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    analyze(parser.parse_args().output.resolve())
