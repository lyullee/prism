"""Campaign weights, failure coverage, source binding and expected-death F-N."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from lh2_tno.backend import BackendError
from lh2_tno.campaign import (
    PhysicalValidationEvidence,
    ProviderPacketEvidence,
    RiskCampaign,
    _matching_provider_packet_evidence,
    _provider_packet_evidence_matches,
    _provider_packet_identity,
)
from lh2_tno.contracts import Facility
from lh2_tno.equipment_boundary import ProviderMassBalance, ResolvedGasRelease, ResolvedGasStep
from lh2_tno.frequency import FrequencyPlan, generate_events
from lh2_tno.legacy_frequency_bridge import attach_precomputed_events, bridge_legacy_scenarios
from lh2_tno.pipeline import ResearchPipeline

ROOT=Path(__file__).parents[1]


def test_provider_packet_identity_keeps_digest_and_clock_without_flow_history():
    release = SimpleNamespace(
        provider_export_schema='prism.resolved_release.v1',
        event_id='scope/tank/G1',
        component_id='tank-01',
        port_id='tank-out',
        provider_source_digest='a' * 64,
        provider_result_digest='b' * 64,
        provider_boundary_reference='provider outlet',
        termination_basis='inventory_depletion',
        duration_s=0.25,
    )
    request = SimpleNamespace(
        resolved_release=release,
        resolved_liquid_release=None,
        resolved_release_set=None,
    )
    identity = _provider_packet_identity(request)
    assert identity == {
        'event_id': 'scope/tank/G1',
        'component_id': 'tank-01',
        'provider_export_schema': 'prism.resolved_release.v1',
        'port_ids': ['tank-out'],
        'provider_source_digests': ['a' * 64],
        'provider_result_digests': ['b' * 64],
        'provider_boundary_references': ['provider outlet'],
        'termination_bases': ['inventory_depletion'],
        'termination_provenances': [None],
        'event_kinds': [None],
        'input_origins': [None],
        'duration_s': [0.25],
        'available_mass_kg': [None],
        'cumulative_mass_out_kg': [None],
    }


def test_provider_packet_identity_keeps_optional_mass_balance_evidence():
    release = SimpleNamespace(
        provider_export_schema='prism.resolved_release.v1',
        event_id='scope/pipe/G1',
        component_id='pipe-01',
        port_id='pipe-out',
        provider_source_digest='a' * 64,
        provider_result_digest='b' * 64,
        provider_boundary_reference='provider outlet',
        termination_basis='reviewed_isolation_success',
        duration_s=0.25,
        provider_mass_balance=ProviderMassBalance(
            initial_mass_kg=2.0,
            cumulative_mass_out_kg=1.0,
            final_mass_kg=1.0,
            reported_residual_mass_kg=1.0,
            derived_accounting_residual_kg=0.0,
        ),
    )
    identity = _provider_packet_identity(SimpleNamespace(
        resolved_release=release,
        resolved_liquid_release=None,
        resolved_release_set=None,
    ))
    assert identity["provider_mass_balances"][0]["final_mass_kg"] == 1.0


def test_provider_packet_qualification_requires_exact_event_and_digest_identity():
    identity = {
        "event_id": "scope/tank/G1",
        "component_id": "tank-01",
        "port_ids": ["tank-out"],
        "provider_source_digests": ["a" * 64],
        "provider_result_digests": ["b" * 64],
    }
    evidence = ProviderPacketEvidence(
        event_id="scope/tank/G1",
        component_id="tank-01",
        port_ids=("tank-out",),
        provider_source_digests=("a" * 64,),
        provider_result_digests=("b" * 64,),
        evidence_id="lh2-actual-001",
    )
    assert _provider_packet_evidence_matches(identity, evidence)
    assert not _provider_packet_evidence_matches(
        {**identity, "provider_result_digests": ["c" * 64]}, evidence
    )


def test_conditional_branches_match_distinct_packet_evidence_without_cross_qualification():
    first = ProviderPacketEvidence(
        event_id="scope/tank/G1",
        component_id="tank-01",
        port_ids=("tank-out",),
        provider_source_digests=("a" * 64,),
        provider_result_digests=("b" * 64,),
        evidence_id="lh2-actual-success",
    )
    second = ProviderPacketEvidence(
        event_id="scope/tank/G1",
        component_id="tank-01",
        port_ids=("tank-out",),
        provider_source_digests=("c" * 64,),
        provider_result_digests=("d" * 64,),
        evidence_id="lh2-actual-failure",
    )
    rows = (first, second)
    assert _matching_provider_packet_evidence(
        rows,
        {
            "event_id": "scope/tank/G1",
            "component_id": "tank-01",
            "port_ids": ["tank-out"],
            "provider_source_digests": ["a" * 64],
            "provider_result_digests": ["b" * 64],
        },
    ) == first
    assert _matching_provider_packet_evidence(
        rows,
        {
            "event_id": "scope/tank/G1",
            "component_id": "tank-01",
            "port_ids": ["tank-out"],
            "provider_source_digests": ["e" * 64],
            "provider_result_digests": ["f" * 64],
        },
    ) is None


def test_campaign_evidence_allows_distinct_packet_identities_for_one_event():
    _, data = inputs()
    evidence = [
        {
            "event_id": "test/shell/G3",
            "component_id": "storage",
            "port_ids": ["tank-out"],
            "provider_source_digests": ["a" * 64],
            "provider_result_digests": ["b" * 64],
            "evidence_id": "lh2-actual-success",
        },
        {
            "event_id": "test/shell/G3",
            "component_id": "storage",
            "port_ids": ["tank-out"],
            "provider_source_digests": ["c" * 64],
            "provider_result_digests": ["d" * 64],
            "evidence_id": "lh2-actual-failure",
        },
    ]
    campaign = RiskCampaign.model_validate_json(
        json.dumps({**data, "provider_packet_evidence": evidence})
    )
    assert len(campaign.provider_packet_evidence) == 2
    with pytest.raises(ValueError, match="exact packet identity"):
        RiskCampaign.model_validate_json(
            json.dumps({**data, "provider_packet_evidence": evidence + [evidence[0]]})
        )


def test_provider_packet_evidence_can_be_built_from_promoted_export_result():
    release = SimpleNamespace(
        event_id="scope/tank/G1",
        component_id="tank-01",
        port_id="tank-out",
        provider_source_digest="a" * 64,
        provider_result_digest="b" * 64,
    )
    result = SimpleNamespace(
        provider_packet_promoted=True,
        release=release,
        provider_response={
            "provider_qualification": {
                "schema_version": "prism.provider_qualification_evidence.v1",
                "status": "qualified_actual",
                "provider_origin": "native_provider",
                "evidence_id": "lh2-actual-001",
                "provider_source_digest": "a" * 64,
            }
        },
    )
    evidence = ProviderPacketEvidence.from_export_result(result)
    assert evidence.evidence_id == "lh2-actual-001"
    assert evidence.provider_result_digests == ("b" * 64,)


def test_two_sided_provider_packet_evidence_requires_both_endpoint_digests():
    left = SimpleNamespace(
        port_id="tank-left-out",
        provider_source_digest="a" * 64,
        provider_result_digest="b" * 64,
    )
    right = SimpleNamespace(
        port_id="tank-right-out",
        provider_source_digest="c" * 64,
        provider_result_digest="d" * 64,
    )
    release = SimpleNamespace(
        event_id="scope/tank/G1",
        component_id="tank-01",
        releases=(left, right),
    )
    result = SimpleNamespace(
        provider_packet_promoted=True,
        release=release,
        provider_response={
            "provider_qualification": {
                "schema_version": "prism.provider_qualification_evidence.v1",
                "status": "qualified_actual",
                "provider_origin": "native_provider",
                "evidence_id": "lh2-two-sided-actual-001",
                "provider_source_digests": ["a" * 64, "c" * 64],
                "provider_result_digests": ["b" * 64, "d" * 64],
            }
        },
    )
    evidence = ProviderPacketEvidence.from_export_result(result)
    assert evidence.port_ids == ("tank-left-out", "tank-right-out")
    assert evidence.provider_source_digests == ("a" * 64, "c" * 64)

    result.provider_response["provider_qualification"]["provider_source_digests"] = [
        "a" * 64,
        "e" * 64,
    ]
    with pytest.raises(ValueError, match="source digest"):
        ProviderPacketEvidence.from_export_result(result)


def test_physical_validation_evidence_is_fail_closed():
    with pytest.raises(ValueError, match="independent physical validation"):
        PhysicalValidationEvidence(status="independent_validated")
    with pytest.raises(ValueError, match="unvalidated physical evidence"):
        PhysicalValidationEvidence(status="not_validated", evidence_id="review-1")


def inputs():
    f=Facility.model_validate_json((ROOT/'examples/consequence_facility.json').read_text(encoding='utf-8'))
    q=json.loads((ROOT/'examples/consequence_request.json').read_text(encoding='utf-8'))
    q.update(annual_frequency_per_year=None,annual_frequency_provenance=None,initiation_intensity_per_s=None)
    q['source_input']['nozzle']['diameter_m']=.01
    q['ignition'].update(direct_probability=.25,delayed_probability_given_no_direct=.5,explosion_probability_given_delayed=.4)
    q['release_termination']={'basis':'synthetic_diagnostic_horizon','time_s':.2,'provenance':'synthetic test only'}
    plan={'id':'test','assets':[{'id':'shell','model_component_id':'storage','profile':'TNO_PRESSURE_VESSEL',
        'classification_basis':'synthetic pressure-vessel classification','physical_scope_ids':['tank-1'],
        'vessel_external_impact_or_operating_error':False}],
        'excluded_model_components':{c.id:'explicitly outside this diagnostic scope' for c in f.components if c.id!='storage'}}
    ids=[r.id for r in f.receptors]
    pop=[{'receptor_id':rid,'persons':10.0 if i==0 else 20.0 if i==1 else 0.0,'presence_probability':.5,'provenance':'synthetic disjoint outdoor population'} for i,rid in enumerate(ids)]
    weather=copy.deepcopy(q['weather'])
    second={**weather,'wind_from_bearing_deg':180.0}
    campaign={'id':'test-campaign','frequency_plan':plan,'annual_conditions':[
        {'id':'D-west','annual_probability':.4,'weather':weather,'population':pop,'provenance':'synthetic joint condition'},
        {'id':'D-north','annual_probability':.6,'weather':second,'population':pop,'provenance':'synthetic joint condition'}],
        'event_routes':[{'event_id':'test/shell/'+loc,'branches':[{'id':'unsupported','probability_given_event':1.0,
            'provenance':'explicit missing release operator','uncomputed_reason':'full inventory operator not implemented'}]} for loc in ['G1','G2']],
        'scope_provenance':'synthetic orchestration test; not complete facility QRA'}
    campaign['event_routes'].append({'event_id':'test/shell/G3','branches':[
        {'id':'isolation-success','probability_given_event':.8,'provenance':'synthetic barrier sensitivity','request':copy.deepcopy(q)},
        {'id':'isolation-failure','probability_given_event':.2,'provenance':'synthetic barrier sensitivity','request':copy.deepcopy(q)}]})
    return f,campaign


def _scoped_provider_release():
    return ResolvedGasRelease(
        component_id='storage', port_id='storage.out', event_id='test/shell/G3',
        event_kind='accidental_leak', upstream_service='LH2',
        upstream_service_provenance='synthetic provider inventory history',
        enthalpy_convention='static_exit_enthalpy',
        property_basis={'fluid': 'Hydrogen', 'energy_reference': 'CoolProp-HEOS:Hydrogen:native'},
        provider_source_digest='a' * 64, provider_result_digest='b' * 64,
        provider_boundary_reference='synthetic provider inventory boundary', input_origin='synthetic',
        position_enu_m=(0.0, 0.0, 1.0), direction_enu=(1.0, 0.0, 0.0),
        ambient_pressure_pa_abs=101325.0, ambient_temperature_k=288.15,
        duration_s=0.2, available_mass_kg=1.0, cumulative_mass_out_kg=0.2,
        cumulative_static_enthalpy_out_j=200.0,
        steps=(ResolvedGasStep(
            time_s=0.0, mass_flow_kg_s=1.0, pressure_pa_abs=101325.0,
            specific_enthalpy_j_kg=1000.0, temperature_k=288.15, density_kg_m3=1.0,
            effective_area_m2=1.0, velocity_m_s=1.0,
            area_provenance='synthetic provider inventory area', velocity_origin='provider_resolved',
        ),),
        termination_provenance='synthetic provider inventory depletion',
        failure_opening_diameter_m=0.01,
    )


class Backend:
    def __init__(self,facility):
        self.facility=facility;self.requests=[];self.fault=None

    def run(self,operation,p):
        if operation=='facility_risk_aggregate':
            ir={rid:[sum(a['initiating_frequency_per_year']*a['conditional_weight']*a['receptor_harm_low_high'][rid][i] for a in p['atoms']) for i in range(2)] for rid in p['receptor_ids']}
            fn=[]
            for i in range(2):
                ns=sorted({a['expected_deaths_low_high'][i] for a in p['atoms'] if a['expected_deaths_low_high'][i]>=1.0})
                fn.append({'expected_deaths':ns,'cumulative_frequency_per_year':[sum(a['initiating_frequency_per_year']*a['conditional_weight'] for a in p['atoms'] if a['expected_deaths_low_high'][i]>=n) for n in ns]})
            return {'data':{'ir_low_high':ir,'fn_low_high':fn}}
        assert operation=='consequence_chain'
        self.requests.append(p)
        if self.fault=='backend':raise BackendError('synthetic deadline failure')
        factor=1.0 if p['weather']['wind_from_bearing_deg']==270.0 else .5
        probs={'direct_fire':.25,'delayed_flash_fire':.225,'delayed_explosion':.15,'no_ignition':.375}
        receptors=[]
        for i,r in enumerate(p['receptors']):
            k=factor/(i+1)
            h=[{'direct_fire':.2*k,'delayed_flash_fire':.4*k,'delayed_explosion':.6*k,'no_ignition':0.0},
               {'direct_fire':.4*k,'delayed_flash_fire':.6*k,'delayed_explosion':.8*k,'no_ignition':0.0}]
            receptors.append({'id':r['id'],'branch_harm_low_high':h,
                'harm_given_observed_release_low_high':[sum(probs[key]*x[key] for key in probs) for x in h]})
        if self.fault=='missing_receptor':receptors.pop()
        if self.fault=='ignition':probs['direct_fire']=.5
        if self.fault=='nan':receptors[0]['branch_harm_low_high'][0]['direct_fire']=float('nan')
        return {'data':{'status':'END_TO_END_DIAGNOSTIC_EXECUTED','full_chain_executed':True,
            'receptors':receptors,'ignition_branch_probabilities':probs,'explosion':{'domain_truncated':self.fault=='domain'}}}


def run(raw=None,fault=None):
    f,d=inputs();d=d if raw is None else raw
    b=Backend(f);b.fault=fault
    r=ResearchPipeline(f,b).facility_risk(RiskCampaign.model_validate_json(json.dumps(d)))
    return r,b


def test_frequency_weather_barrier_ignition_each_weighted_once():
    r,b=run()
    rid=b.facility.receptors[0].id
    assert r['known_contribution_annual_ir_low_high'][rid]==pytest.approx([1.61e-6,2.485e-6])
    assert len(b.requests)==4
    assert all(q['occupancy_probability']==1.0 for q in b.requests)
    assert all(q['weather']['wind_from_bearing_deg']==q['source_input']['ambient']['wind_from_bearing_deg'] for q in b.requests)
    assert r['total_facility_annual_ir_low_high'] is None
    assert r['provider_packet_case_count'] == 0
    assert r['qualified_provider_packet_case_count'] == 0
    assert r['provider_packet_promoted'] is False
    assert r['complete_facility_qra_claim'] is False
    assert r['declared_scope_annual_ir_low_high'] is None
    assert len(r['uncomputed_cases'])==4
    assert r['coverage']['fraction_of_generated_initiation_frequency']==pytest.approx(10/11)
    by_component={row['component_id']:row for row in r['coverage']['by_component']}
    assert by_component['storage']['scope_status']=='PARTIAL'
    assert by_component['storage']['generated_event_count']==3
    assert by_component['storage']['uncomputed_case_count']==4
    assert by_component['storage']['not_numerically_executed_case_count']==4
    assert by_component['storage']['qualified_evidence_withheld_case_count']==0
    assert by_component['storage']['numerically_executed_case_count']==4
    assert r['coverage']['not_numerically_executed_case_count']==4
    assert r['coverage']['qualified_evidence_withheld_case_count']==0
    assert r['coverage']['numerically_executed_case_count']==4
    assert r['coverage']['dynamic_state_closure_status_counts'] == {
        'NOT_DECLARED': 4,
        'NOT_EVALUATED': 4,
    }
    assert r['coverage']['dynamic_state_closure_ready_case_count'] == 0
    assert r['coverage']['dynamic_state_closure_blocked_case_count'] == 0
    assert by_component['isolation']['scope_status']=='EXCLUDED'
    assert by_component['isolation']['excluded_reason']
    assert all('scenario_families' in atom for atom in r['risk_atoms'])
    assert r['coverage']['scenario_family_event_counts']['vessel_hole'] == 1


def test_port_scoped_frequency_identity_survives_cases_and_risk_atoms():
    _, data = inputs()
    data['frequency_plan']['assets'][0]['port_ids'] = ['storage.out']
    release = _scoped_provider_release().model_dump(mode='json')
    for branch in data['event_routes'][-1]['branches']:
        request = branch['request']
        request.update(
            source_input=None, resolved_release=release, resolved_release_set=None,
            resolved_liquid_release=None, source_operator='equipment_inventory_depletion',
            available_mass_kg=1.0, source_position_enu_m=[0.0, 0.0, 1.0],
            release_termination={
                'basis': 'inventory_depletion', 'time_s': 0.2,
                'provenance': 'synthetic provider inventory depletion',
            },
        )
    result, _ = run(data)
    scoped_cases = [row for row in result['cases'] if row['event_id'] == 'test/shell/G3']
    scoped_atoms = [row for row in result['risk_atoms'] if row['event_id'] == 'test/shell/G3']
    assert scoped_cases
    assert scoped_atoms
    assert all(row['frequency_port_ids'] == ['storage.out'] for row in scoped_cases)
    assert all(row['frequency_port_ids'] == ['storage.out'] for row in scoped_atoms)


def test_societal_outcomes_remain_separate_before_fn_accumulation():
    r,_=run()
    lo=r['known_contribution_expected_death_fn_low_high'][0]
    assert lo['expected_deaths']==pytest.approx([1.,2.,3.,4.,6.])
    assert lo['cumulative_frequency_per_year'][0]==pytest.approx(6.25e-6)
    assert lo['cumulative_frequency_per_year'][-1]==pytest.approx(.4*.15*1e-5)
    assert all(a>=b for a,b in zip(lo['cumulative_frequency_per_year'],lo['cumulative_frequency_per_year'][1:]))


def test_campaign_timing_records_case_percentiles_without_claiming_repeated_run_latency():
    r, _ = run()
    timing = r['timing']
    assert timing['fresh_physics_cases'] == 4
    assert timing['case_min_ms'] <= timing['case_median_ms'] <= timing['case_p95_ms'] <= timing['case_p99_ms'] <= timing['case_max_ms']
    assert 'not repeated-run latency' in timing['distribution']


@pytest.mark.parametrize('fault',['backend','missing_receptor','ignition','nan'])
def test_failed_physics_or_invalid_result_never_becomes_zero_complete_risk(fault):
    r,_=run(fault=fault)
    assert r['status']=='PARTIAL_DECLARED_SCOPE'
    assert len([x for x in r['uncomputed_cases'] if x['status']=='FAILED'])==4
    assert r['declared_scope_annual_ir_low_high'] is None
    assert r['timing']['fresh_physics_cases']==4


def test_domain_truncation_retains_known_contribution_withholds_total():
    r,_=run(fault='domain')
    assert all(v[0]>0 for v in r['known_contribution_annual_ir_low_high'].values())
    assert len([x for x in r['uncomputed_cases'] if x['status']=='EXECUTED_DOMAIN_INCOMPLETE'])==4
    assert r['declared_scope_annual_ir_low_high'] is None


@pytest.mark.parametrize('fault',['missing_event','duplicate_event','weather_partition','barrier_partition','missing_population','duplicate_population','external_frequency','leak_size','budget','radiation'])
def test_invalid_campaign_rejected_before_backend_execution(fault):
    f,d=inputs();b=Backend(f)
    q=d['event_routes'][-1]['branches'][0]['request']
    if fault=='missing_event':d['event_routes'].pop(0)
    if fault=='duplicate_event':d['event_routes'].append(copy.deepcopy(d['event_routes'][0]))
    if fault=='weather_partition':d['annual_conditions'][0]['annual_probability']=.5
    if fault=='barrier_partition':d['event_routes'][-1]['branches'][0]['probability_given_event']=1.0
    if fault=='missing_population':d['annual_conditions'][0]['population'].pop()
    if fault=='duplicate_population':d['annual_conditions'][0]['population'].append(copy.deepcopy(d['annual_conditions'][0]['population'][0]))
    if fault=='external_frequency':q.update(annual_frequency_per_year=.001,annual_frequency_provenance='must be rejected')
    if fault=='leak_size':q['source_input']['nozzle']['diameter_m']=.02
    if fault=='budget':d['maximum_physics_cases']=1
    if fault=='radiation':q['radiative_fraction_range']=[.05,.1]
    with pytest.raises(ValueError):
        ResearchPipeline(f,b).facility_risk(RiskCampaign.model_validate_json(json.dumps(d)))
    assert b.requests==[]


def test_zero_weight_uncomputed_branches_are_explicit_and_not_executed():
    _,d=inputs()
    d['event_routes'][-1]['branches'][1].update(probability_given_event=0.0,request=None,uncomputed_reason='zero probability test')
    d['event_routes'][-1]['branches'][0]['probability_given_event']=1.0
    r,b=run(d)
    assert len(b.requests)==2
    assert len([x for x in r['cases'] if x['status']=='ZERO_WEIGHT'])==2


def test_all_hole_rows_computed_but_synthetic_and_excluded_scope_is_not_full_facility():
    f,d=inputs();asset=d['frequency_plan']['assets'][0]
    asset.update(profile='LH2_VESSEL',nominal_diameter_m=.1,vessel_external_impact_or_operating_error=None)
    events=generate_events(f,FrequencyPlan.model_validate_json(json.dumps(d['frequency_plan'])))
    template=d['event_routes'][-1]['branches'][0]['request'];routes=[]
    for e in events:
        q=copy.deepcopy(template);q['source_input']['nozzle']['diameter_m']=e.release.hole_diameter_m
        routes.append({'event_id':e.id,'branches':[{'id':'declared-release','probability_given_event':1.0,'provenance':'synthetic','request':q}]})
    d['event_routes']=routes
    r,_=run(d)
    assert r['declared_scope_numerically_complete'] is True
    assert r['declared_scope_annual_ir_low_high'] is not None
    assert r['total_facility_annual_ir_low_high'] is None
    assert r['physical_validation_claim'] is False


def test_inventory_loc_cannot_be_promoted_to_hole_by_campaign():
    f,d=inputs();q=copy.deepcopy(d['event_routes'][-1]['branches'][0]['request'])
    d['event_routes'][0]['branches']=[{'id':'bad-inventory-proxy','probability_given_event':1.0,'provenance':'must fail','request':q}]
    b=Backend(f)
    with pytest.raises(ValueError,match='different release operator'):
        ResearchPipeline(f,b).facility_risk(RiskCampaign.model_validate_json(json.dumps(d)))
    assert b.requests==[]


def test_campaign_executes_attached_external_event_catalogue_through_common_ir_fn_chain():
    f, d = inputs()
    events, _ = bridge_legacy_scenarios(
        [{
            'scenario_id': 'legacy-shell-G3', 'tag': 'TK-101',
            'primitive': 'VESSEL', 'service': 'LH2', 'bin_label': '1%',
            'hole_diameter_m': 0.01, 'frequency_per_year': 2.5e-4,
            'release_kind': 'CONTINUOUS', 'release_path': 'DIRECT',
            'physics_route': 'SLABX_LH2', 'grade': 'PUBLISHED_UNVALIDATED',
        }],
        {'legacy-shell-G3': 'storage'},
        source_sha256='a' * 64,
    )
    plan = FrequencyPlan.model_validate_json(json.dumps(d['frequency_plan']))
    d['frequency_plan'] = attach_precomputed_events(
        plan, events, provenance='legacy bridge campaign test'
    ).model_dump(mode='json')
    template = copy.deepcopy(d['event_routes'][-1]['branches'][0]['request'])
    d['event_routes'] = [{
        'event_id': events[0].id,
        'branches': [{
            'id': 'release', 'probability_given_event': 1.0,
            'provenance': 'external bridge campaign test', 'request': template,
        }],
    }]
    result, backend = run(d)
    assert result['event_catalog']['mode'] == 'precomputed_external_catalogue'
    assert result['event_catalog']['rate_arithmetic_owner'] == 'external_legacy_generator'
    assert result['event_catalog']['consequence_and_risk_owner'] == 'prism_campaign_evaluator'
    assert result['event_catalog']['scope_gap_component_ids'] == []
    assert len(backend.requests) == 2
    assert result['known_contribution_annual_ir_low_high']
