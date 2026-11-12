"""Block B attacks. Oracle scale is explicit extra adversarial information.

No truth labels or oracle scale are ever passed to a detector. Mixed strategies
are balanced across the simulator's attacker IDs, fixed for the whole run.
"""
from dataclasses import replace
from collections import Counter
import torch
from clients.attacks import FreeRiderAttacker, flatten_delta, add_flat_delta
from clients.review2_attacks import ReviewAttacker as PublishedAttacker
from server.aggregation import floating_keys

class BlockBAttacker(FreeRiderAttacker):
    def __init__(self, config, device, parameter_keys):
        super().__init__(config,device)
        self.kind=config.attack_type
        self.assignment={}
        self.oracle_target=None
        self.published=PublishedAttacker(config,device,parameter_keys)

    @staticmethod
    def spec(attack):
        if attack=='OracleNormMatchedFR4':
            return dict(name=attack,extra_information='previous-round median norm of honest updates; simulator oracle',
                        first_round='unchanged FR4 until scale available',scope='full floating response including buffers')
        if attack=='MixedFR':
            return dict(name=attack,assignment='balanced FR1/FR2/FR3/FR4 over sorted attacker IDs, fixed throughout')
        return PublishedAttacker.spec(attack)

    def set_attackers(self,ids):
        self.assignment={c:('FR1','FR2','FR3','FR4')[i%4] for i,c in enumerate(sorted(ids))}

    def state_dict(self):
        return {**super().state_dict(),'block_b_assignment':self.assignment,'oracle_target':self.oracle_target,
                'published':self.published.state_dict()}

    def load_state_dict(self,state):
        super().load_state_dict(state)
        self.assignment={int(k):v for k,v in state['block_b_assignment'].items()}
        self.oracle_target=state['oracle_target']
        self.published.load_state_dict(state['published'])

    def fabricate(self,client_id,received_state,round_idx,generator):
        kind=self.assignment[client_id] if self.kind=='MixedFR' else self.kind
        if kind in {'FraboniDecay','ZhuScaledDelta'}:
            return self.published.fabricate(client_id,received_state,round_idx,generator)
        result=getattr(self,'_'+('fr4' if kind=='OracleNormMatchedFR4' else kind.lower()))
        if kind=='FR1': return result(client_id,received_state)
        if kind=='FR2': return result(received_state,generator)
        if kind=='FR3': return result(client_id,received_state)
        returned=result(client_id,received_state,round_idx,generator)
        if kind=='OracleNormMatchedFR4' and self.oracle_target is not None:
            delta=flatten_delta(returned,received_state)
            norm=float(delta.norm())
            if norm>0:
                returned=add_flat_delta(received_state,delta*(self.oracle_target/norm),floating_keys(received_state))
        return returned
