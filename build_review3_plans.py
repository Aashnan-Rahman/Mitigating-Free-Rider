"""Construct all prospective Block B cells without reading experiment outcomes."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
def dump(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def build(root=ROOT):
    config=root/'configs'
    defaults=json.loads((config/'review2_03_passive_seed42.json').read_text())['defaults']
    defaults={**defaults,'detector_arm':'combined','unperturbed_challenges':False}
    splits=[(d,s) for d in ['mnist','cifar10'] for s in ['noniid','iid']]
    plans=[]
    def entry(d,s,a='FR3',arm='combined',share=40,**extra):
        cfg=dict(dataset=d,distribution=s,attack_type=a,detector_arm=arm,free_rider_pct=share/100,seed=42,**extra)
        suffix='_'.join(f'{k}{v}' for k,v in extra.items()).replace('.','p')
        return dict(id=f'{d}_{s}_{a}_{arm}_fr{share}'+('_'+suffix if suffix else ''),variant='paired',config=cfg)
    def phase(name,entries,description,**extra):
        path=config/(name+'.json')
        dump(path,dict(workflow='review2',batch_name=name,results_root='results',defaults=defaults,
                       description=description,experiments=entries,**extra))
        plans.append(path.relative_to(root).as_posix())
        return plans[-1]
    analysis=phase('review3_00_analysis_seed42',[dict(id='metrics_scaling_and_std_checks',variant='paired',config=dict(dataset='analysis',distribution='synthetic',attack_type='analysis',free_rider_pct=0.,num_rounds=1))],
          'Isolated synthetic detector scaling, round-20 passive/active AUROC and nominal-alpha MAD diagnostics; numerical STD-DAGMM smoke check, not author-setting replication.',analysis_job=True)
    lin=phase('review3_00b_lin_validation_seed42',[
        dict(id=f'lin_mnist_iid_dwa_eta{str(eta).replace(".","p")}',variant='paired',config=dict(dataset='mnist',distribution='iid',attack_type='LinDWA',free_rider_pct=.01,num_clients=100,local_epochs=1,num_rounds=10,global_eta=eta))
        for eta in [.3,1.]],'Lin-setting validation attempts: MNIST, 100 clients, one DWA, 2-layer FC. Declare unspecified hidden width/SGD/AE epochs; report every outcome, do not assume detector success.',lin_validation=True)
    controls=phase('review3_01_perturbation_control_seed42',[
        entry(d,s,a,trap_noise_scale=0.,unperturbed_challenges=True) for d,s in splits for a in ['FR1','FR2','FR3','FR4']],
        '100-round frozen-but-unperturbed challenges; retain trap withholding and schedules. Separate from passive ordinary-round arm.')
    components=phase('review3_02_components_seed42',[
        entry(d,s,a,arm) for arm in ['norm_only','profile_only','sendback_only','no_memory'] for d,s in splits for a in ['FR1','FR2','FR3','FR4']],
        'Independent reruns. Norm/profile arms neutralize the other nomination view and disable exact sendback. No-memory requires adjacent same-component certificates; never single-cycle removal.')
    attacks=phase('review3_03_attacks_seed42',[
        entry(d,s,a) for a in ['OracleNormMatchedFR4','MixedFR'] for d,s in splits],
        'Full-model attacks. Oracle norm matching receives previous-round honest median scale as explicit extra adversarial information. Mixed fixed balanced FR1-4 assignments. No labels enter detector.')
    hetero=phase('review3_04_heterogeneity_seed42',[
        entry(d,'noniid',a,share=p,dirichlet_alpha=alpha) for d in ['mnist','cifar10'] for alpha in [.1,1.]
        for a,p in [('FR3',0),('FR3',40),('FR4',40)]],
        'Honest-only and FR3/FR4 at alpha .1/1.0. Existing alpha .5 paired results remain the prespecified reference.')
    sweep=phase('review3_05_gamma_sweep_seed42',[
        entry(d,s,a,trap_noise_scale=gamma,num_rounds=30,unperturbed_challenges=(gamma==0))
        for gamma in [0.,.005,.01,.02] for d,s in splits for a in ['FR3','FR4']],
        'Exploratory fixed full gamma grid 0/.005/.01/.02, 30 rounds. Default .01 unchanged. Report all 32 cells; no best-gamma replacement of main result.')
    old=json.loads((config/'review2_priority_queue.json').read_text())
    q=old['plans']
    ordered=q[:3]+[analysis,lin,controls,components,q[4],attacks,hetero,sweep,q[3]]+q[5:]
    dump(config/'review3_priority_queue.json',dict(description='12 November amendment; unchanged low-share/passive first; separate Block B; held-out block intact and last.',
          plans=ordered,primary_seed=42,heldout_seeds=old['heldout_seeds'],freeze='Original registered sources/plans unchanged; Block B has separate hashes. Optional WEF reproductions not scheduled.'))
    return plans

def freeze(root=ROOT):
    plans=build(root)
    old=json.loads((root/'configs/review2_registration.json').read_text())
    added=['review3_config.py','train_review3.py','clients/review3_attacks.py','server/review3_ablation.py',
           'run_review3_batch.py','review3_analysis.py','build_review3_plans.py','run_lin_std_validation.py']
    sources=list(old['source_sha256'])+added+['comparison/std_dagmm.py','benchmark_mnist_std_dagmm.py','train_v15_4.py','configs/review3_priority_queue.json']
    digest=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
    dump(root/'configs/review3_registration.json',dict(date='2026-11-12',
        source_commit_parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        purpose='Prospective Block B; commit and tag this manifest with sources before launch. Existing review2 registration is not rewritten.',
        source_sha256={p:digest(p) for p in sources},plan_sha256={p:digest(p) for p in plans},
        metrics=dict(primary='per-run removal TP/FP/FN and first complete-removal round; report failures',
            separation='round 20, mean over selected A/B of -norm_z and +profile_z; positive class free rider; tie-aware AUROC; no tuned combined score',
            incomplete='not zero; preserve as incomplete and block successor on worker failure',
            mad='observational ordinary-response lower tail, nominal alpha .01 from original registration; not a guaranteed error rate',
            sweep='every gamma 0/.005/.01/.02 cell; exploratory, .01 remains main',
            scaling='synthetic all-honest continuous features, seed42, L=8; N100/500/1000; one warmup plus three measured repeats; torch threads1; no training in parallel',
            std_check='synthetic numerical pipeline and score-direction diagnostic, NOT proof of author-setting replication or a successful real detection baseline')))

if __name__=='__main__': freeze()
