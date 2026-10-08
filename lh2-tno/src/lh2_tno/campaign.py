"""Auditable event/weather/barrier execution for declared outdoor LH2 scopes.

Expected-death F-N convention follows the existing legacy risk module. It is
not a sampled joint casualty distribution or an independently validated QRA.
"""
from __future__ import annotations
import json
import math
import time
from statistics import median
from pydantic import Field, model_validator
from .contracts import Contract, Name, Fraction, Nonnegative, canonical_digest
from .consequences import ConsequenceRequest, Weather
from .frequency import FrequencyPlan, bind_event, generate_events
from .backend import BackendError

IGNITION_KEYS = {'direct_fire', 'delayed_flash_fire', 'delayed_explosion', 'no_ignition'}


class PopulationCell(Contract):
    receptor_id: Name
    persons: Nonnegative
    presence_probability: Fraction
    provenance: Name


class AnnualCondition(Contract):
    id: Name
    annual_probability: Fraction
    weather: Weather
    population: tuple[PopulationCell, ...]
    provenance: Name

    @model_validator(mode='after')
    def unique_population(self):
        if len({x.receptor_id for x in self.population}) != len(self.population):
            raise ValueError('population cells cannot duplicate a receptor')
        return self


class ReleaseBranch(Contract):
    id: Name
    probability_given_event: Fraction
    provenance: Name
    request: ConsequenceRequest | None = None
    uncomputed_reason: Name | None = None

    @model_validator(mode='after')
    def explicit_route(self):
        if (self.request is None) == (self.uncomputed_reason is None):
            raise ValueError('choose a physical request or an explicit uncomputed reason')
        if self.request is not None:
            q = self.request
            if any(x is not None for x in (q.frequency_event, q.annual_frequency_per_year,
                                           q.annual_frequency_provenance, q.initiation_intensity_per_s)):
                raise ValueError('campaign templates must not already carry initiating frequency')
            if q.occupancy_probability != 1.0:
                raise ValueError('fixed-person IR uses unit occupancy; population presence belongs to annual conditions')
            if q.release_termination is None:
                raise ValueError('campaign release requires explicit duration/termination provenance')
        return self


class EventRoute(Contract):
    event_id: Name
    branches: tuple[ReleaseBranch, ...]

    @model_validator(mode='after')
    def partition(self):
        if not self.branches or len({x.id for x in self.branches}) != len(self.branches):
            raise ValueError('unique nonempty release/barrier branches required')
        if not math.isclose(sum(x.probability_given_event for x in self.branches), 1.0, rel_tol=0, abs_tol=1e-10):
            raise ValueError('release/barrier partition must close to one, including failed isolation')
        return self


class RiskCampaign(Contract):
    id: Name
    frequency_plan: FrequencyPlan
    annual_conditions: tuple[AnnualCondition, ...]
    event_routes: tuple[EventRoute, ...]
    scope_provenance: Name
    maximum_physics_cases: int = Field(default=200, ge=1, le=2000)

    @model_validator(mode='after')
    def partition(self):
        rows = self.annual_conditions
        if not rows or len({x.id for x in rows}) != len(rows):
            raise ValueError('nonempty unique annual joint weather/population conditions required')
        if not math.isclose(sum(x.annual_probability for x in rows), 1.0, rel_tol=0, abs_tol=1e-10):
            raise ValueError('annual joint weather/population partition must close to one')
        if not self.event_routes or len({x.event_id for x in self.event_routes}) != len(self.event_routes):
            raise ValueError('unique nonempty event routes required')
        return self


def prepared_request(template, event, condition):
    """Synchronize source wind and dispersion without changing outlet geometry."""
    d = template.model_dump(mode='json')
    d['weather'] = condition.weather.model_dump(mode='json')
    if d['source_input'] is not None:
        d['source_input']['ambient'].update(wind_speed_m_s=condition.weather.wind_speed_m_s,
            wind_from_bearing_deg=condition.weather.wind_from_bearing_deg)
    q = ConsequenceRequest.model_validate_json(json.dumps(d, allow_nan=False))
    return bind_event(q, event)


def _checked_harm(data, receptor_ids, probabilities):
    rows = data['receptors']
    if len(rows) != len(receptor_ids) or {r['id'] for r in rows} != set(receptor_ids):
        raise ValueError('consequence result must include every facility receptor exactly once')
    reported = data['ignition_branch_probabilities']
    if set(reported) != IGNITION_KEYS or any(not math.isclose(reported[k], probabilities[k], rel_tol=0, abs_tol=1e-10) for k in IGNITION_KEYS):
        raise ValueError('consequence ignition probabilities disagree with the requested partition')
    harms = {}
    for row in rows:
        h = row['branch_harm_low_high']
        if len(h) != 2 or any(set(x) != IGNITION_KEYS for x in h):
            raise ValueError('two radiation endpoints and all ignition branches required')
        if any(not math.isfinite(v) or not 0 <= v <= 1 for x in h for v in x.values()):
            raise ValueError('finite branch harm probabilities required')
        if any(h[0][k] > h[1][k] + 1e-12 for k in IGNITION_KEYS) or any(x['no_ignition'] != 0 for x in h):
            raise ValueError('ordered radiation sensitivity endpoints and zero unignited fire harm required')
        combined = row['harm_given_observed_release_low_high']
        if len(combined) != 2 or any(not math.isclose(combined[i], sum(probabilities[k]*h[i][k] for k in IGNITION_KEYS), rel_tol=1e-9, abs_tol=1e-12) for i in range(2)):
            raise ValueError('branch-weighted receptor harm does not close')
        harms[row['id']] = h
    return harms


def evaluate_campaign(pipeline, campaign: RiskCampaign) -> dict:
    started = time.perf_counter()
    f = pipeline.facility
    if f.environment != 'outdoor' or not f.receptors:
        raise ValueError('outdoor facility and explicit receptors required')
    events = {x.id: x for x in generate_events(f, campaign.frequency_plan)}
    routes = {x.event_id: x for x in campaign.event_routes}
    if set(events) != set(routes):
        raise ValueError('every generated LOC needs exactly one route or explicit uncomputed branch')
    receptor_ids = [r.id for r in f.receptors]
    for c in campaign.annual_conditions:
        if set(x.receptor_id for x in c.population) != set(receptor_ids):
            raise ValueError('every annual condition must declare population at every receptor, including zero')
    # Validate all mapped requests before executing any physical case. Invalid
    # templates are configuration errors, never treated as harmless outcomes.
    prepared = {}
    for e in events.values():
        for b in routes[e.id].branches:
            if b.request is None:
                continue
            for c in campaign.annual_conditions:
                prepared[(e.id, b.id, c.id)] = prepared_request(b.request, e, c)
    if len(prepared) > campaign.maximum_physics_cases:
        raise ValueError('campaign physics-case budget exceeded before execution')
    if len({q.radiative_fraction_range for q in prepared.values()}) > 1:
        raise ValueError('campaign radiation endpoints must represent the same declared sensitivity across cases')
    cases, atoms, missing = [], [], []
    exposures = set()
    synthetic = False
    for e in events.values():
        for b in routes[e.id].branches:
            for c in campaign.annual_conditions:
                row = {'event_id': e.id, 'asset_id': e.asset_id, 'release_branch_id': b.id,
                    'annual_condition_id': c.id, 'initiating_frequency_per_year': e.annual_frequency_per_year,
                    'release_branch_probability': b.probability_given_event,
                    'annual_condition_probability': c.annual_probability}
                if e.annual_frequency_per_year*b.probability_given_event*c.annual_probability == 0:
                    row.update(status='ZERO_WEIGHT', elapsed_ms=0.0)
                    cases.append(row)
                    continue
                if b.request is None:
                    row.update(status='UNCOMPUTED', reason=b.uncomputed_reason, elapsed_ms=0.0)
                    missing.append(row.copy()); cases.append(row)
                    continue
                q = prepared[(e.id, b.id, c.id)]
                synthetic |= q.release_termination.basis == 'synthetic_diagnostic_horizon'
                exposures.add(q.radiative_fraction_range)
                begin = time.perf_counter()
                try:
                    result = pipeline.consequences(q)
                    data = result['data']
                    if data['status'] != 'END_TO_END_DIAGNOSTIC_EXECUTED' or data['full_chain_executed'] is not True:
                        raise ValueError('incomplete physical chain')
                    probabilities = q.ignition.probabilities()
                    harms = _checked_harm(data, receptor_ids, probabilities)
                except (BackendError, ValueError, KeyError, TypeError) as error:
                    row.update(status='FAILED', reason=f'{type(error).__name__}: {error}', elapsed_ms=(time.perf_counter()-begin)*1000)
                    missing.append(row.copy()); cases.append(row)
                    continue
                row.update(status='EXECUTED', elapsed_ms=(time.perf_counter()-begin)*1000,
                    request_digest=q.digest(), result_digest=canonical_digest(result),
                    backend_config_digest=result.get('backend_config_digest'),
                    adapter_source_digest=result.get('adapter_source_digest'),
                    stage_elapsed_ms=data.get('stage_elapsed_ms', {}),
                    mass_ledger=data.get('mass_ledger'),
                    termination=q.release_termination.model_dump(mode='json'))
                if data.get('explosion', {}).get('domain_truncated') is not False:
                    row['status'] = 'EXECUTED_DOMAIN_INCOMPLETE'
                    row['reason'] = 'outside-domain flammable mass unresolved or domain-completeness flag absent'
                    missing.append(row.copy())
                if data.get('operator_limited') is True:
                    row['status'] = 'EXECUTED_OPERATOR_LIMITED'
                    row['reason'] = 'source operator has declared constant-state or open physical closure limitations'
                    missing.append(row.copy())
                cases.append(row)
                population = {p.receptor_id: p.persons*p.presence_probability for p in c.population}
                for key in sorted(IGNITION_KEYS):
                    weight = c.annual_probability*b.probability_given_event*probabilities[key]
                    if weight == 0:
                        continue
                    atoms.append({'event_id': e.id, 'asset_id': e.asset_id,
                        'annual_condition_id': c.id, 'release_branch_id': b.id, 'ignition_branch': key,
                        'initiating_frequency_per_year': e.annual_frequency_per_year,
                        'conditional_weight': weight,
                        'receptor_harm_low_high': {rid: [harms[rid][i][key] for i in range(2)] for rid in receptor_ids},
                        'expected_deaths_low_high': [sum(population[rid]*harms[rid][i][key] for rid in receptor_ids) for i in range(2)]})
    if len(exposures) > 1:
        raise ValueError('campaign radiation endpoints must represent the same declared sensitivity across cases')
    aggregated = pipeline.backend.run('facility_risk_aggregate', {'receptor_ids': receptor_ids, 'atoms': atoms})
    known = aggregated['data']
    scope_complete = not missing
    excluded = campaign.frequency_plan.excluded_model_components
    full_facility_complete = scope_complete and not excluded and not synthetic
    times = [r['elapsed_ms'] for r in cases if r['status'].startswith('EXECUTED') or r['status']=='FAILED']
    generated_frequency=sum(e.annual_frequency_per_year for e in events.values())
    evaluated_frequency=sum(r['initiating_frequency_per_year']*r['release_branch_probability']*r['annual_condition_probability'] for r in cases if r['status']=='EXECUTED')
    # Keep a component-level accounting alongside the event-level ledger.  A
    # facility review should be able to answer which physical equipment is
    # covered without inferring it from event IDs or from a single aggregate
    # percentage.  Operator-limited and domain-incomplete cases remain
    # partial even when a numerical result exists.
    event_component={event.id:event.model_component_id for event in events.values()}
    component_coverage=[]
    for component in f.components:
        component_events=[event for event in events.values() if event.model_component_id==component.id]
        component_cases=[case for case in cases if event_component.get(case['event_id'])==component.id]
        excluded_reason=excluded.get(component.id)
        if excluded_reason is not None:
            scope_status='EXCLUDED'
        elif not component_events:
            scope_status='NO_EVENT_GENERATED'
        elif any(case['status'] in {'UNCOMPUTED','FAILED','EXECUTED_DOMAIN_INCOMPLETE','EXECUTED_OPERATOR_LIMITED'} for case in component_cases):
            scope_status='PARTIAL'
        else:
            scope_status='EXECUTED'
        component_coverage.append({
            'component_id': component.id,
            'kind': component.kind,
            'scope_status': scope_status,
            'excluded_reason': excluded_reason,
            'generated_event_count': len(component_events),
            'generated_initiation_frequency_per_year': sum(event.annual_frequency_per_year for event in component_events),
            'campaign_case_count': len(component_cases),
            'executed_case_count': sum(case['status']=='EXECUTED' for case in component_cases),
            'uncomputed_case_count': sum(case['status'] in {'UNCOMPUTED','FAILED','EXECUTED_DOMAIN_INCOMPLETE','EXECUTED_OPERATOR_LIMITED'} for case in component_cases),
            'uncomputed_reasons': sorted({case.get('reason') for case in component_cases if case['status'] != 'EXECUTED' and case.get('reason')}),
        })
    return {'status':'DECLARED_SCOPE_EXECUTED' if scope_complete else 'PARTIAL_DECLARED_SCOPE',
        'facility_id': f.id, 'facility_digest': f.digest(), 'campaign_digest': campaign.digest(),
        'scope_provenance': campaign.scope_provenance, 'events':[e.model_dump(mode='json') for e in events.values()],
        'annual_conditions':[c.model_dump(mode='json') for c in campaign.annual_conditions],
        'cases': cases, 'uncomputed_cases': missing, 'excluded_model_components': excluded,
        'coverage':{'generated_initiation_frequency_per_year':generated_frequency,
            'fully_executed_case_weighted_frequency_per_year':evaluated_frequency,
            'fraction_of_generated_initiation_frequency':evaluated_frequency/generated_frequency if generated_frequency else None,
            'meaning':'frequency coverage only; not fraction of risk captured, not physical validation',
            'by_component':component_coverage},
        'declared_scope_numerically_complete': scope_complete, 'synthetic_release_horizon_present': synthetic,
        'declared_scope_annual_ir_low_high': known['ir_low_high'] if scope_complete else None,
        'known_contribution_annual_ir_low_high': known['ir_low_high'],
        'declared_scope_expected_death_fn_low_high': known['fn_low_high'] if scope_complete else None,
        'known_contribution_expected_death_fn_low_high': known['fn_low_high'],
        'total_facility_annual_ir_low_high': known['ir_low_high'] if full_facility_complete else None,
        'total_facility_expected_death_fn_low_high': known['fn_low_high'] if full_facility_complete else None,
        'risk_atoms': atoms, 'aggregation_provenance': {k:v for k,v in aggregated.items() if k!='data'},
        'timing': {'fresh_physics_cases':len(times), 'case_min_ms':min(times) if times else None,
            'case_median_ms':median(times) if times else None, 'case_max_ms':max(times) if times else None,
            'campaign_elapsed_ms':(time.perf_counter()-started)*1000, 'distribution':'across cases; not repeated-run latency qualification'},
        'semantics': {'individual_risk':'fixed person at each receptor; no population occupancy multiplier',
            'societal_risk':'native legacy F-N of expected deaths per event/weather/barrier/ignition outcome; not a joint casualty distribution',
            'weighting':'initiating frequency times annual joint condition times release/barrier branch times ignition; each once',
            'endpoints':'two declared radiation sensitivities and within-branch harm union bounds; not frequency credible intervals',
            'population':'disjoint outdoor groups at representative receptors; temporal presence in annual conditions'},
        'physical_validation_claim':False, 'complete_facility_qra_claim':False,
        'one_hz_fresh_physics_demonstrated':False}
