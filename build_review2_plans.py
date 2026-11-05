"""Predeclare the review experiment order; no outcomes enter plan construction."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOLDOUT_SEEDS = [101, 103, 107, 109, 113]


def build(root=ROOT):
    configs = root/'configs'
    previous = json.loads((configs/'v15_4_mnist_seed43_fr30_fr40_plan.json').read_text())
    defaults = {**previous['defaults'], 'seed': 42, 'device': 'cpu', 'num_rounds': 100,
        'num_workers': 0, 'local_epochs': 3, 'download_data': False}
    splits = [('mnist','noniid'), ('cifar10','noniid'), ('mnist','iid'), ('cifar10','iid')]
    phases = []

    def phase(number, name, entries, note):
        batch = f'review2_{number:02d}_{name}'
        plan = dict(workflow='review2', batch_name=batch, results_root='results',
            description=note, defaults=defaults, experiments=entries)
        path = configs/f'{batch}.json'
        path.write_text(json.dumps(plan, indent=2)+'\n', encoding='utf-8')
        phases.append(path.relative_to(root).as_posix())

    def entry(dataset, split, share, attack='FR3', seed=42, variant='paired'):
        return dict(id=f'{variant}_{dataset}_{split}_{attack}_fr{share}_seed{seed}',
            variant=variant, config=dict(dataset=dataset, distribution=split,
                free_rider_pct=share/100, attack_type=attack, seed=seed))

    phase(1, 'honest_seed42', [entry(d,s,0) for d,s in splits],
        'Highest priority: honest-only false removals/quarantine with frozen settings. Attack selector is inactive at 0%.')
    phase(2, 'low_share_seed42', [entry(d,s,p,a) for d,s in splits for p in [5,10,20] for a in ['FR3','FR4','FR2','FR1']],
        'Single seed first. Test the population-derived support gate without reducing it to achieve recall. Preserve misses.')
    phase(3, 'passive_seed42', [entry(d,s,40,a,variant='passive') for d,s in splits for a in ['FR3','FR4','FR2','FR1']],
        'Controlled ordinary-model ablation: same norm/profile pipeline, selected slots and confirmation. No challenge model or trap withholding. Compare with existing seed-42 paired 40% records; clock-only differences are audited separately.')
    phase(4, 'oracle_seed42', [entry(d,s,p,variant='oracle') for d,s in splits for p in [0,30,40]],
        'Label-aware utility reference only. Preserve the 100-client data partition, initial model and exact honest identities; exclude designated free riders before training, with no auditing. Never score these as detector successes.')
    phase(5, 'published_attacks_seed42', [entry(d,s,p,a) for d,s in splits for p in [30,40] for a in ['FraboniDecay','ZhuScaledDelta']],
        'Paper-guided parameter attacks, not author implementations. Fraboni gamma=1 and initial-delta RMS sigma; Zhu equation 9 with no fitted scale clipping. Client-visible history only; no trap identity or server global-model side channel.')
    primary = list(phases)
    phase(6, 'heldout_multiseed_last', [entry(d,'noniid',p,a,seed) for seed in HOLDOUT_SEEDS
        for d in ['mnist','cifar10'] for p in [0,5,10,20]
        for a in (['FR3'] if p == 0 else ['FR3','FR4'])],
        'LAST: five prespecified unseen seeds, non-IID honest-only and FR3/FR4 at 5/10/20%. No retuning after earlier results; report every seed.')
    # Existing baseline replications are intentionally late, never discarded.
    late_baselines = ['configs/fedavg_mnist_baseline_seed73_fr30_fr40.json',
        'configs/fedavg_mnist_baseline_seed43_fr30_fr40.json']
    queue = dict(description='Review priorities first on one seed; existing matched MNIST replications and all additional multi-seed work last.',
        plans=primary+late_baselines+[phases[-1]], primary_seed=42,
        heldout_seeds=HOLDOUT_SEEDS, freeze='No attack-specific detector changes or outcome-dependent thresholds.')
    path = configs/'review2_priority_queue.json'
    path.write_text(json.dumps(queue, indent=2)+'\n', encoding='utf-8')
    return queue


if __name__ == '__main__':
    queue = build()
    for name in queue['plans']:
        plan = json.loads((ROOT/name).read_text())
        print(f'{plan["batch_name"]}: {len(plan["experiments"])} runs')
