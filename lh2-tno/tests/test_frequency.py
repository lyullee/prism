"""Frequency units, event partitions, missing coverage and physical binding."""
import copy
import json
import math
from pathlib import Path
import pytest
from lh2_tno.contracts import Facility
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.frequency import (FrequencyAsset, FrequencyPlan, FrequencyEvent, generate_events,
    bind_event, catalogue, DemandFailure, EventBranch, branch_frequencies,
    GammaRatePrior, ConfirmedLeakExperience, updated_rate, forecast_initiation_probability)
from lh2_tno.pipeline import ResearchPipeline

ROOT = Path(__file__).parents[1]


def facility():
    return Facility.model_validate_json((ROOT/'examples/consequence_facility.json').read_text(encoding='utf-8'))


def asset(**kw):
    data=dict(id='tank-shell', model_component_id='storage', profile='TNO_PRESSURE_VESSEL',
        classification_basis='synthetic reviewed pressurised vessel example, no field claim',
        physical_scope_ids=('tank-1',), vessel_external_impact_or_operating_error=False)
    data.update(kw)
    return FrequencyAsset(**data)


def plan(a=None):
    a=asset() if a is None else a
    excluded={x.id:'outside the selected diagnostic scope' for x in facility().components if x.id!=a.model_component_id}
    return FrequencyPlan(id='diagnostic', assets=(a,), excluded_model_components=excluded)


def events(a=None):return generate_events(facility(), plan(a))


def template():
    data=json.loads((ROOT/'examples/consequence_request.json').read_text(encoding='utf-8'))
    data.update(annual_frequency_per_year=None, annual_frequency_provenance=None, initiation_intensity_per_s=None)
    data['source_input']['nozzle']['diameter_m']=.01
    data['release_termination']={'basis':'synthetic_diagnostic_horizon','time_s':.2,
                                'provenance':'short pulse diagnostic; not validated full Purple G3 duration'}
    return ConsequenceRequest.model_validate_json(json.dumps(data))


def test_pressure_vessel_preserves_loc_partition_and_book_dimensions():
    rows=events()
    assert [x.annual_frequency_per_year for x in rows]==[5e-7,5e-7,1e-5]
    assert [x.release.mode for x in rows]==['instantaneous_inventory','inventory_over_600s','hole']
    assert rows[2].release.hole_diameter_m==.01
    assert all(x.marginal_p05_per_year is None for x in rows)


def test_external_impact_is_added_to_two_inventory_locs_only():
    rows=events(asset(vessel_external_impact_or_operating_error=True))
    assert [x.annual_frequency_per_year for x in rows]==pytest.approx([5.5e-6,5.5e-6,1e-5])


@pytest.mark.parametrize('diameter,rates',[(.0749,(1e-6,5e-6)),(.075,(3e-7,2e-6)),(.15,(3e-7,2e-6)),(.1501,(1e-7,5e-7))])
def test_pipe_thresholds_and_minimum_10m_include_flange_exposure(diameter,rates):
    rows=events(asset(profile='TNO_PIPE', vessel_external_impact_or_operating_error=None,
        nominal_diameter_m=diameter, length_per_item_m=2., pipe_conditions='default_conditions', pipe_correction_factor=1.))
    assert [x.annual_frequency_per_year for x in rows]==pytest.approx([r*10 for r in rates])
    assert rows[0].release.mode=='two_sided_rupture'


def test_pipe_two_sided_event_can_bind_one_reviewed_location_with_explicit_weight():
    rows=events(asset(profile='TNO_PIPE', vessel_external_impact_or_operating_error=None,
        nominal_diameter_m=.025, length_per_item_m=10., pipe_conditions='default_conditions',
        pipe_correction_factor=1., location_weight=.1,
        location_weight_provenance='synthetic reviewed rupture segment allocation'))
    assert rows[0].exposure_multiplier==pytest.approx(1.)
    assert rows[0].annual_frequency_per_year==pytest.approx(1e-6*10*.1)
    assert 'location_weight' in ' '.join(rows[0].limitations)


def test_pipe_correction_and_count_apply_once_and_hole_is_capped():
    rows=events(asset(profile='TNO_PIPE', vessel_external_impact_or_operating_error=None,
        count=2, physical_scope_ids=('pipe-a','pipe-b'), nominal_diameter_m=.8, length_per_item_m=30.,
        pipe_conditions='increased_failure_potential',pipe_correction_factor=3.,correction_provenance='synthetic thermal cycling review'))
    assert rows[0].annual_frequency_per_year==pytest.approx(1e-7*30*2*3)
    assert rows[1].release.hole_diameter_m==.05


def test_lh2_pipe_uses_actual_metres_not_purple_minimum_or_object_count():
    rows=events(asset(profile='LH2_PIPE', vessel_external_impact_or_operating_error=None,
        nominal_diameter_m=.025,length_per_item_m=2.))
    assert rows[0].annual_frequency_per_year==pytest.approx(3.4e-6*2)
    assert rows[2].release.hole_diameter_m==pytest.approx(.0025)
    assert rows[0].marginal_p05_per_year<rows[0].annual_frequency_per_year<rows[0].marginal_p95_per_year


@pytest.mark.parametrize('profile,rate',[('TNO_PUMP_STANDARD',1e-4),('TNO_PUMP_STEEL_CONTAINMENT',5e-5),('TNO_PUMP_CANNED',1e-5)])
def test_pump_uses_largest_connecting_pipeline_not_unsourced_lh2_factor(profile,rate):
    rows=events(asset(profile=profile,vessel_external_impact_or_operating_error=None,nominal_diameter_m=.05))
    assert rows[0].annual_frequency_per_year==rate
    assert rows[1].release.hole_diameter_m==pytest.approx(.005)


def test_relief_discharge_is_not_pfd_or_normal_vent_count():
    row=events(asset(profile='TNO_RELIEF_DEVICE',vessel_external_impact_or_operating_error=None,
        relief_direct_substance_contact_and_atmospheric_discharge=True))[0]
    assert row.annual_frequency_per_year==2e-5
    assert row.release.mode=='maximum_relief_discharge'
    assert DemandFailure(id='ESD',demands_per_year=10.,failure_probability_per_demand=.01,
        provenance='synthetic demands/proof tests').annual_failure_rate()['annual_frequency_per_year']==.1


@pytest.mark.parametrize('fault',['unknown','missing_length','missing_vessel_condition','scope_count','implicit_relief','factor','item_length'])
def test_incomplete_or_unreviewed_inputs_fail_instead_of_inventing_zero(fault):
    data=asset().model_dump()
    if fault=='unknown':data['profile']='LH2_RELIQUEFIER'
    if fault=='missing_length':data.update(profile='LH2_PIPE',nominal_diameter_m=.02,vessel_external_impact_or_operating_error=None)
    if fault=='missing_vessel_condition':data['vessel_external_impact_or_operating_error']=None
    if fault=='scope_count':data['count']=2
    if fault=='implicit_relief':data.update(profile='TNO_RELIEF_DEVICE',vessel_external_impact_or_operating_error=None)
    if fault=='factor':data.update(profile='TNO_PIPE',vessel_external_impact_or_operating_error=None,nominal_diameter_m=.02,
        length_per_item_m=20.,pipe_conditions='increased_failure_potential',pipe_correction_factor=2.,correction_provenance='invalid')
    if fault=='item_length':data['length_per_item_m']=20.
    with pytest.raises(ValueError):FrequencyAsset(**data)


def test_same_physical_scope_cannot_use_two_alternative_partitions():
    a=asset()
    b=asset(id='tank-alternative',profile='LH2_VESSEL',nominal_diameter_m=.05,vessel_external_impact_or_operating_error=None)
    with pytest.raises(ValueError):FrequencyPlan(id='double',assets=(a,b))


def test_component_coverage_cannot_silently_omit_equipment_or_reference_unknown():
    with pytest.raises(ValueError):generate_events(facility(),FrequencyPlan(id='missing',assets=(asset(),)))
    with pytest.raises(ValueError):generate_events(facility(),plan(asset(model_component_id='does-not-exist')))


def test_loc_bind_calls_existing_consequence_pipeline_and_carries_provenance():
    class Backend:
        def run(self,operation,payload):
            assert operation=='consequence_chain'
            assert payload['annual_frequency_per_year']==1e-5
            assert payload['frequency_event']['loc']=='G3'
            assert payload['source_input']['nozzle']['diameter_m']==.01
            return {'data':{'test_stub':True}}
    result=ResearchPipeline(facility(),Backend()).consequences_for_event(plan(),'diagnostic/tank-shell/G3',template())
    assert result['frequency_event']['annual_frequency_per_year']==1e-5


def test_instantaneous_and_600s_locs_cannot_be_faked_with_short_nozzle_model():
    for e in events()[:2]:
        with pytest.raises(ValueError):bind_event(template(),e)


def test_600s_inventory_event_requires_and_preserves_a_complete_long_horizon():
    data=template().model_dump(mode='json')
    data['source_operator']='inventory_over_600s'
    data['source_input']['duration_s']=600.0
    data['source_input']['time_step_s']=60.0
    data['evaluation_times_s']=[0.0,1.0,2.0,20.0,600.0]
    data['release_termination']={'basis':'inventory_over_600s','time_s':600.0,
        'provenance':'provider returned the complete declared 600 s inventory horizon'}
    data.update(annual_frequency_per_year=None,annual_frequency_provenance=None,initiation_intensity_per_s=None)
    bound=bind_event(ConsequenceRequest.model_validate_json(json.dumps(data)),events()[1])
    assert bound.source_operator=='inventory_over_600s'
    assert bound.release_termination.basis=='inventory_over_600s'
    assert bound.frequency_event.release.mode=='inventory_over_600s'


def test_600s_inventory_event_rejects_a_short_declared_history():
    data=template().model_dump(mode='json')
    data['source_operator']='inventory_over_600s'
    data['release_termination']={'basis':'inventory_over_600s','time_s':.2,
        'provenance':'short diagnostic horizon; not a complete 600 s history'}
    with pytest.raises(ValueError,match='exactly 600 s'):
        ConsequenceRequest.model_validate_json(json.dumps(data))


def test_binding_cannot_overwrite_an_existing_rate_or_ignore_wrong_hole():
    t=template().model_dump(mode='json');t['source_input']['nozzle']['diameter_m']=.02
    with pytest.raises(ValueError):bind_event(ConsequenceRequest.model_validate_json(json.dumps(t)),events()[2])
    t=template().model_dump(mode='json');t.update(annual_frequency_per_year=.01,annual_frequency_provenance='external')
    with pytest.raises(ValueError):bind_event(ConsequenceRequest.model_validate_json(json.dumps(t)),events()[2])


def test_request_rejects_tampered_bound_frequency_and_aggregated_point():
    data=bind_event(template(),events()[2]).model_dump(mode='json');data['annual_frequency_per_year']=.01
    with pytest.raises(ValueError):ConsequenceRequest.model_validate_json(json.dumps(data))
    rows=events(asset(count=2,physical_scope_ids=('one','two')))
    with pytest.raises(ValueError):bind_event(template(),rows[2])


@pytest.mark.parametrize('fault',['missing','wrong_clock'])
def test_catalogue_frequency_cannot_justify_undeclared_release_cutoff(fault):
    data=template().model_dump(mode='json')
    if fault=='missing':data['release_termination']=None
    else:data['release_termination']['time_s']=1.
    with pytest.raises(ValueError):bind_event(ConsequenceRequest.model_validate_json(json.dumps(data)),events()[2])


def test_conditional_branches_conserve_frequency_including_no_harm():
    branches=(EventBranch(id='fire',probability_given_initiation=.1,provenance='test'),
              EventBranch(id='no-fire',probability_given_initiation=.9,provenance='test'))
    result=branch_frequencies(events()[2],branches)
    assert sum(r['annual_frequency_per_year'] for r in result['branches'])==pytest.approx(1e-5)
    with pytest.raises(ValueError):branch_frequencies(events()[2],branches[:1])


def test_marginal_uncertainty_and_catalogue_are_not_shared_mutable_state():
    a=catalogue();a['profiles'].clear()
    assert len(catalogue()['profiles'])==17


def test_stationary_future_horizon_is_not_observed_leak_probability():
    row=events()[2]
    result=forecast_initiation_probability(row,365.25*86400.)
    assert result['initiation_probability']==pytest.approx(-math.expm1(-1e-5))


def test_annual_rate_and_live_forecast_cannot_use_conflicting_frequencies():
    data=template().model_dump(mode='json');data['initiation_intensity_per_s']=1e-6
    with pytest.raises(ValueError):bind_event(ConsequenceRequest.model_validate_json(json.dumps(data)),events()[2])


def test_field_update_requires_exposure_units_and_cumulative_confirmed_events():
    prior=GammaRatePrior(profile='LH2_VALVE',loc='AREA_1%',rate_unit='item^-1 year^-1',
        shape=1.,exposure_rate=10000.,provenance='explicit synthetic alternative prior')
    obs=ConfirmedLeakExperience(profile=prior.profile,loc=prior.loc,rate_unit=prior.rate_unit,
        confirmed_leak_count=2,exposure=5000.,origin='reviewed_field_event_register',
        observation_id='register-v1',provenance='synthetic example',complete_ascertainment=True)
    assert updated_rate(prior,obs)['mean_rate']==pytest.approx(3/15000)
    assert updated_rate(prior,obs)==updated_rate(prior,obs)  # pure cumulative recomputation
    with pytest.raises(ValueError):updated_rate(prior,obs.model_copy(update={'rate_unit':'m^-1 year^-1'}))
    data=obs.model_dump();data['origin']='sensor_alarm'
    with pytest.raises(ValueError):ConfirmedLeakExperience(**data)
