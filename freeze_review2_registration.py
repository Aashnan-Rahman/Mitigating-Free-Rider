"""Freeze plans, held-out seeds and executable sources before seeing outcomes."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from run_review2_batch import ROOT, SOURCE_FILES


def freeze():
    output=ROOT/'configs/review2_registration.json'
    if output.exists():
        raise FileExistsError('Registration already exists; do not silently replace a preregistration')
    queue=json.loads((ROOT/'configs/review2_priority_queue.json').read_text())
    plans=[name for name in queue['plans'] if name.startswith('configs/review2_')]
    record=dict(created_utc=datetime.now(timezone.utc).isoformat(),primary_seed=42,
        heldout_seeds=queue['heldout_seeds'],
        nominal_mad_lower_tail_alpha=.01, detector_parameters='frozen v15.4 without retuning; audit-clock liveness correction only',
        plan_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in plans},
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_FILES},
        outcomes_available_at_registration='Existing v15.4 study only; no review2 training runs started')
    prior=ROOT/'.local_cleanup/review2_io_validation_20261105/registration_active_original.json'
    if prior.exists():
        record['maintenance_receipt']=dict(prior_registration_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
            change='Evidence publication before checkpoint, rollback of uncommitted removal rows; no training, screening or confirmation change',
            preserved_attempt='.local_cleanup/review2_io_validation_20261105/warmup_attempt',
            prior_phase='warmup only; no review screening outcomes obtained')
        record['outcomes_available_at_registration']='Published v15.4 study and separately archived warmup-only validation attempt; no new review screening outcomes'
    output.write_text(json.dumps(record,indent=2)+'\n')
    print(f'Frozen {len(plans)} plans and {len(SOURCE_FILES)} source files in {output}')


if __name__=='__main__':
    freeze()
