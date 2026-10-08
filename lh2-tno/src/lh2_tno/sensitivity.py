"""Frequency-only sensitivity of saved physical risk atoms; no new physics.

Multipliers are declared scenarios, not fitted distributions or confidence
intervals. Partial campaign coverage is preserved under every multiplier.
"""
from __future__ import annotations
import math
import json
from pydantic import model_validator
from .contracts import Contract, Name, Positive, canonical_digest
from .frequency import FrequencyEvent


class FrequencySensitivity(Contract):
    id: Name
    asset_multipliers: dict[str, Positive]
    provenance: Name

    @model_validator(mode='after')
    def explicit(self):
        if not self.asset_multipliers or any(not k.strip() for k in self.asset_multipliers):
            raise ValueError('explicit asset multipliers required')
        return self


def frequency_sensitivity(result: dict, scenarios: tuple[FrequencySensitivity, ...]) -> dict:
    if not scenarios or len({s.id for s in scenarios})!=len(scenarios):
        raise ValueError('nonempty unique sensitivity scenarios required')
    events={e['id']:FrequencyEvent.model_validate_json(json.dumps(e)) for e in result['events']}
    assets={e.asset_id for e in events.values()}
    if any(set(s.asset_multipliers)!=assets for s in scenarios):
        raise ValueError('each scenario must explicitly address every frequency asset, including multiplier one')
    atoms=result['risk_atoms']
    ids=set(result['known_contribution_annual_ir_low_high'])
    for a in atoms:
        e=events[a['event_id']]
        if a['asset_id']!=e.asset_id or a['initiating_frequency_per_year']!=e.annual_frequency_per_year:
            raise ValueError('risk atom does not match its originating event frequency')
        if not math.isfinite(a['conditional_weight']) or not 0<=a['conditional_weight']<=1:
            raise ValueError('finite conditional weights required')
        if set(a['receptor_harm_low_high'])!=ids:
            raise ValueError('risk atom receptor set mismatch')
        values=[v for pair in a['receptor_harm_low_high'].values() for v in pair]
        if any(not math.isfinite(v) or not 0<=v<=1 for v in values):
            raise ValueError('finite receptor harm required')
        if any(len(pair)!=2 for pair in a['receptor_harm_low_high'].values()):
            raise ValueError('two radiation endpoint harms required')
        n=a['expected_deaths_low_high']
        if len(n)!=2 or any(not math.isfinite(v) or v<0 for v in n):
            raise ValueError('finite two-endpoint expected fatalities required')
    outputs=[]
    computed_assets={a['asset_id'] for a in atoms}
    for s in scenarios:
        ir={rid:[0.,0.] for rid in sorted(ids)}
        contribution={asset:[0.,0.] for asset in sorted(assets)}
        outcomes=[[],[]]
        for a in atoms:
            frequency=a['initiating_frequency_per_year']*s.asset_multipliers[a['asset_id']]*a['conditional_weight']
            for i in range(2):
                for rid in ir:
                    ir[rid][i]+=frequency*a['receptor_harm_low_high'][rid][i]
                contribution[a['asset_id']][i]+=frequency*a['expected_deaths_low_high'][i]
                outcomes[i].append((a['expected_deaths_low_high'][i],frequency))
        fn=[]
        for values in outcomes:
            ns=sorted({n for n,_ in values if n>=1})
            fn.append({'expected_deaths':ns,'cumulative_frequency_per_year':[sum(f for deaths,f in values if deaths>=n) for n in ns]})
        ranked=[]
        for i in range(2):
            # Competition ranking: ties share rank, never arbitrary ID order.
            ranked.append({asset:None if asset not in computed_assets else 1+sum(v[i]>value[i] and not math.isclose(v[i],value[i],rel_tol=1e-12,abs_tol=0) for key,v in contribution.items() if key in computed_assets) for asset,value in contribution.items()})
        outputs.append({'scenario':s.model_dump(mode='json'),'known_annual_ir_low_high':ir,
            'known_expected_death_fn_low_high':fn,'asset_known_annual_expected_fatalities_low_high':contribution,
            'asset_rank_by_known_expected_fatalities_low_high':ranked,
            'uncomputed_cases':result['uncomputed_cases'],
            'declared_scope_annual_ir_low_high':ir if result['declared_scope_numerically_complete'] else None,
            'total_facility_annual_ir_low_high':ir if result['total_facility_annual_ir_low_high'] is not None else None})
    return {'campaign_digest':result['campaign_digest'],'physical_risk_atoms_digest':canonical_digest(atoms),
        'scenarios':outputs,'fresh_physics_executed':False,'statistical_confidence_interval':False,
        'semantics':'declared deterministic literature-frequency multipliers, fixed physics/weather/barriers/population; ranks only within computed scope',
        'physical_validation_claim':False}
