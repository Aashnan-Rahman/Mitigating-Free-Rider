"""Isolated single-channel nomination and retained-memory ablations.

No labels, attack type or known prevalence enter this module. Disabled score
views are neutralized before nomination, not merely filtered after nomination.
"""
from server import v15_certificate_memory as frozen
from server import v15_strict_norm as strict

REVISION = 'review3_preregistered_channel_ablation_v1'
measurements, build_schedule = frozen.measurements, frozen.build_schedule
_arm = 'combined'
CycleState = frozen.CycleState

def configure(arm):
    global _arm, CycleState
    if arm not in {'combined','norm_only','profile_only','sendback_only','no_memory'}:
        raise ValueError(arm)
    _arm = arm
    # Remove retained, nonconsecutive memory while preserving two-cycle evidence.
    CycleState = strict.CycleState if arm == 'no_memory' else frozen.CycleState

def policy():
    return {**frozen.policy(), 'revision':REVISION, 'ablation_arm':_arm,
            'single_channel_nomination':'other statistical view neutralized to zero; exact disabled',
            'no_memory':'same component must recur in adjacent complete cycles'}

def _views(rows):
    public = [{k:r.get(k) for k in strict.PUBLIC_FIELDS} for r in rows]
    if _arm in {'norm_only','profile_only'}:
        for r in public:
            r['exact_zero_delta']=r['exact_sendback']=0
            r['profile_z' if _arm=='norm_only' else 'norm_z']=0.
            r['profile_distance' if _arm=='norm_only' else 'delta_norm']=0.
    return public

def screen(rows, round_index):
    public = _views(rows)
    if _arm=='sendback_only':
        pairs={}
        for r in public: pairs.setdefault(r['client_id'],{})[r['trap_id']]=r
        decisions=[]
        for client,p in pairs.items():
            exact=set(p)=={0,1} and all(p[t]['exact_sendback'] for t in (0,1))
            decisions.append(dict(client_id=client,round=round_index,state='S' if exact else 'R',
                screen_state='S' if exact else 'R',strong_channels='exact_sendback' if exact else '',
                evidence_strength='strong' if exact else 'none',reason='ablation_sendback_only'))
        return decisions,dict(ablation_arm=_arm,no_strong_evidence=not any(d['strong_channels'] for d in decisions))
    decisions, metadata = frozen.screen(public, round_index)
    if _arm in {'combined','no_memory'}:
        return decisions, metadata
    allowed = {'norm_only':'norm_low','profile_only':'profile_high','sendback_only':'exact_sendback'}[_arm]
    by_client={}
    for r in public: by_client.setdefault(r['client_id'],{})[r['trap_id']]=r
    for d in decisions:
        channels=set(filter(None,d['strong_channels'].split(','))) & {allowed}
        if _arm=='sendback_only':
            p=by_client[d['client_id']]
            channels={'exact_sendback'} if set(p)=={0,1} and all(p[t]['exact_sendback'] for t in (0,1)) else set()
        state='S' if channels else ('R' if _arm=='sendback_only' or d['screen_state']=='R' else 'C')
        d.update(strong_channels=','.join(sorted(channels)),state=state,
                 evidence_strength='strong' if channels else 'weak' if state=='C' else 'none',
                 reason='ablation_'+_arm,screen_state=state)
    metadata.update(ablation_arm=_arm,no_strong_evidence=not any(d['strong_channels'] for d in decisions))
    return decisions,metadata

def audit_anomalies(rows):
    public=_views(rows)
    if _arm=='sendback_only':
        return {r['client_id'] for r in public if r['exact_sendback']},'exact_only_audit'
    # Reuse the same statistical gates, disabling other channels through views.
    return frozen.audit_anomalies(public)
