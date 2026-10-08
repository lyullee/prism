"""Provider ownership, PH checks, event clocks, ports and frequency semantics."""
import copy
import json
import math
from pathlib import Path
import pytest
from lh2_tno.contracts import Facility
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.equipment_boundary import (ResolvedGasRelease, ResolvedGasReleaseSet,
    ResolvedLiquidRelease, VerticalGasHandoff, thermodynamic_rows)
from lh2_tno.resolved_liquid_worker import resolve_liquid_rows
from lh2_tno.layered_network_boundary import audit_layered_liquid_boundary
from lh2_tno.provider_liquid_partition import combine_provider_liquid_partition
from lh2_tno.frequency import FrequencyAsset,FrequencyPlan,generate_events,bind_event
from lh2_tno.pipeline import ResearchPipeline
from lh2_tno.service import request_from_telemetry
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from validate_layered_tank_slabsx_bridge import _packet_from_bridge, _provider_rows


def packet():
    steps=[]
    for t,v in [(0.,30.),(.2,40.)]:
        steps.append(dict(time_s=t,mass_flow_kg_s=.2*v*.0005,pressure_pa_abs=101325.,
            specific_enthalpy_j_kg=3e6,temperature_k=150.,density_kg_m3=.2,effective_area_m2=.0005,
            velocity_m_s=v,area_provenance='synthetic test plane',velocity_origin='provider_resolved'))
    mass=sum(s['mass_flow_kg_s']*(end-s['time_s']) for s,end in zip(steps,[.2,.37]))
    return dict(component_id='vent',port_id='vent.out',event_id='test-vent',event_kind='normal_vent',
        upstream_service='COLD_GH2',upstream_service_provenance='synthetic cold gas equipment state',
        enthalpy_convention='static_exit_enthalpy',property_basis={'fluid':'ParaHydrogen','backend':'CoolProp-HEOS',
        'energy_reference':'CoolProp-HEOS:ParaHydrogen:native'},provider_source_digest='a'*64,provider_result_digest='b'*64,
        provider_boundary_reference='synthetic native gas outlet',input_origin='synthetic',position_enu_m=[0.,0.,1.],
        direction_enu=[1.,0.,0.],ambient_pressure_pa_abs=101325.,ambient_temperature_k=288.15,
        duration_s=.37,available_mass_kg=5.,cumulative_mass_out_kg=mass,
        cumulative_static_enthalpy_out_j=mass*3e6,steps=steps,termination_provenance='synthetic command at 0.37 s')


def request_data(p=None):
    root=Path(__file__).parents[1]
    d=json.loads((root/'examples/consequence_request.json').read_text(encoding='utf-8'))
    d.update(source_input=None,resolved_release=packet() if p is None else p,component_id='vent',
        available_mass_kg=5.,source_position_enu_m=[0.,0.,1.],annual_frequency_per_year=None,
        annual_frequency_provenance=None,initiation_intensity_per_s=None,
        release_termination={'basis':'synthetic_diagnostic_horizon','time_s':.37,'provenance':'test event clock'},
        evaluation_times_s=[0.,.1,.2,.37,.5,1.,2.,3.,4.,5.,10.,20.])
    return d


def two_sided_request_data():
    first = packet()
    first.update(event_kind='accidental_leak', event_id='two-sided-test', port_id='vent.a',
                 failure_opening_diameter_m=.0254)
    second = copy.deepcopy(first)
    second.update(port_id='vent.b', position_enu_m=[2., 0., 1.])
    release_set = ResolvedGasReleaseSet.model_validate_json(json.dumps({
        'event_id':'two-sided-test', 'component_id':'vent',
        'releases':[first, second], 'available_mass_kg':5.,
        'cumulative_mass_out_kg':first['cumulative_mass_out_kg']+second['cumulative_mass_out_kg'],
        'inventory_provenance':'synthetic shared pipe inventory',
    }))
    d = request_data()
    d.update(source_input=None, resolved_release=None,
             resolved_release_set=release_set.model_dump(mode='json'),
             source_operator='equipment_two_sided_rupture',
             available_mass_kg=5., source_position_enu_m=[0., 0., 1.],
             source_positions_enu_m=[[0., 0., 1.], [2., 0., 1.]],
             annual_frequency_per_year=None, annual_frequency_provenance=None,
             initiation_intensity_per_s=None,
             release_termination={'basis':'two_sided_rupture','time_s':.37,
                                  'provenance':'synthetic two-endpoint provider closure'})
    return d, release_set


def liquid_packet():
    base = packet()
    steps = []
    for source_step, ground_fraction in zip(base['steps'], (.6, .625)):
        total = source_step['mass_flow_kg_s']
        gas = total * (1. - ground_fraction)
        ground = total * ground_fraction
        velocity = source_step['velocity_m_s']
        density = source_step['density_kg_m3']
        steps.append({
            'time_s': source_step['time_s'], 'total_mass_flow_kg_s': total,
            'gas_mass_flow_kg_s': gas, 'ground_liquid_mass_flow_kg_s': ground,
            'airborne_liquid_mass_flow_kg_s': 0., 'specific_enthalpy_j_kg': 3e6,
            'gas_pressure_pa_abs': 101325., 'gas_temperature_k': 150.,
            'gas_density_kg_m3': density, 'gas_effective_area_m2': gas / (density * velocity),
            'gas_velocity_m_s': velocity, 'gas_velocity_origin': 'provider_resolved',
            'droplet_class_outcomes': [{
                'ground_liquid_mass_flow_kg_s': ground,
                'airborne_liquid_mass_flow_kg_s': 0., 'flight_time_s': .1,
                'impact_position_m': [.2, 0., 0.], 'droplet_diameter_m': 5e-4,
            }],
        })
    mass = sum(s['total_mass_flow_kg_s'] * (end - s['time_s'])
               for s, end in zip(steps, [.2, .37]))
    return {
        'component_id': 'vent', 'port_id': 'vent.out', 'event_id': 'liquid-test',
        'event_kind': 'accidental_leak', 'upstream_service': 'LH2',
        'upstream_service_provenance': 'synthetic LH2 liquid provider',
        'boundary_kind': 'resolved_atmospheric_liquid_exit', 'phase_basis': 'two_phase',
        'enthalpy_convention': 'provider_total_outlet_enthalpy',
        'property_basis': base['property_basis'], 'provider_source_digest': 'a' * 64,
        'provider_result_digest': 'b' * 64, 'provider_boundary_reference': 'synthetic flash boundary',
        'input_origin': 'synthetic', 'position_enu_m': [0., 0., 1.],
        'direction_enu': [1., 0., 0.], 'ambient_pressure_pa_abs': 101325.,
        'ambient_temperature_k': 288.15, 'duration_s': .37, 'available_mass_kg': 5.,
        'cumulative_mass_out_kg': mass, 'cumulative_specific_enthalpy_out_j': mass * 3e6,
        'reference_area_m2': .001, 'reference_area_provenance': 'synthetic provider liquid outlet',
        'steps': steps, 'termination_provenance': 'synthetic positive inventory threshold',
        'droplet_partition_provenance': 'synthetic provider flash and rainout partition',
        'failure_opening_diameter_m': .0025,
    }


def facility_data(kind='vent_stack'):
    parameters={'vent_stack':{'length_m':6.,'diameter_m':.0254},'pipe':{'length_m':1.,'diameter_m':.0254},
                'storage_tank':{'volume_m3':1.}}.get(kind,{})
    return {'id':'generic-provider','configuration_origin':'synthetic','environment':'outdoor',
        'components':[{'id':'vent','kind':kind,'position_enu_m':[0.,0.,0.],
        'parameters_si':parameters,'property_basis':packet()['property_basis']}],
        'ports':[{'id':'vent.out','component_id':'vent','phase':'vapour','direction':'out'}],'edges':[],
        'receptors':[{'id':'worker','position_enu_m':[2.,0.,1.]}]}


def two_sided_facility_data():
    f = facility_data('pipe')
    f['ports'][0]['id'] = 'vent.a'
    f['ports'].append({'id':'vent.b','component_id':'vent','phase':'vapour','direction':'out',
                       'position_enu_m':[2.,0.,1.]})
    f['ports'][0]['position_enu_m']=[0.,0.,1.]
    return f


class FakeCP:
    def __init__(self,temperature=150.,density=.2,quality=-1.,sound=1000.):
        self.temperature=temperature;self.density=density;self.quality=quality;self.sound=sound
    def PropsSI(self,quantity,k1,v1,k2,v2,fluid):
        if quantity=='T' and k2=='Q':return 20.3
        return {'T':self.temperature,'D':self.density,'Q':self.quality,'A':self.sound}[quantity]


def test_native_event_clock_and_mass_static_enthalpy_are_preserved():
    p=ResolvedGasRelease.model_validate_json(json.dumps(packet()))
    assert p.integrated_mass_kg==pytest.approx(.003*.2+.004*.17)
    assert p.integrated_static_enthalpy_j==pytest.approx(p.integrated_mass_kg*3e6)
    rows,history=thermodynamic_rows(packet(),101325.,FakeCP())
    assert [r['time_s'] for r in rows]==[0.,.2]
    assert [r['gas_mass_flow_kg_s'] for r in rows]==[.003,.004]
    assert history['discharge_recalculated'] is False
    assert history['equipment_dynamics_recalculated'] is False
    assert rows[0]['gas_boundary_temperature_k']==150.  # never replace by saturation/ambient T


@pytest.mark.parametrize('fault',['mass','energy','area','inventory','clock','zero_velocity','direction','basis','owner','digest'])
def test_inconsistent_or_ambiguous_provider_contracts_are_rejected(fault):
    d=packet()
    if fault=='mass':d['cumulative_mass_out_kg']*=2
    if fault=='energy':d['cumulative_static_enthalpy_out_j']*=2
    if fault=='area':d['steps'][0]['effective_area_m2']*=2
    if fault=='inventory':d['available_mass_kg']=1e-5
    if fault=='clock':d['steps'][1]['time_s']=0.
    if fault=='zero_velocity':d['steps'][0]['velocity_m_s']=0.
    if fault=='direction':d['direction_enu']=[0.,0.,1.]
    if fault=='basis':d['property_basis']['energy_reference']='unknown reference'
    if fault=='owner':d['discharge_owner']='consumer'
    if fault=='digest':d['provider_source_digest']='untracked'
    with pytest.raises(ValueError):ResolvedGasRelease.model_validate_json(json.dumps(d))


def test_vertical_exit_requires_provider_handoff_and_preserves_original_direction():
    d=packet()
    d.update(direction_enu=[0.,0.,1.], vertical_handoff={
        'position_enu_m':[1.,0.,2.], 'direction_enu':[1.,0.,0.],
        'velocity_m_s':8., 'density_kg_m3':.2, 'temperature_k':150.,
        'h2_mass_fraction':.5, 'half_width_m':.1, 'depth_m':.2,
        'provenance':'synthetic vertical-to-horizontal provider handoff'})
    release=ResolvedGasRelease.model_validate_json(json.dumps(d))
    assert release.direction_enu == (0.,0.,1.)
    assert release.vertical_handoff.direction_enu == (1.,0.,0.)
    no_adapter=copy.deepcopy(d);no_adapter.pop('vertical_handoff')
    with pytest.raises(ValueError, match='horizontal handoff adapter'):
        ResolvedGasRelease.model_validate_json(json.dumps(no_adapter))
    mixed=copy.deepcopy(d);mixed['direction_enu']=[.6,0.,.8]
    with pytest.raises(ValueError, match='horizontal handoff adapter'):
        ResolvedGasRelease.model_validate_json(json.dumps(mixed))


def test_vertical_provider_handoff_is_accepted_by_consequence_contract():
    d=packet()
    d.update(direction_enu=[0.,0.,1.], vertical_handoff={
        'position_enu_m':[1.,0.,2.], 'direction_enu':[1.,0.,0.],
        'velocity_m_s':8., 'density_kg_m3':.2, 'temperature_k':150.,
        'h2_mass_fraction':.5, 'half_width_m':.1, 'depth_m':.2,
        'provenance':'synthetic vertical-to-horizontal provider handoff'})
    request=ConsequenceRequest.model_validate_json(json.dumps(request_data(d)))
    assert request.resolved_release.vertical_handoff.position_enu_m == (1.,0.,2.)


def test_variable_vertical_handoff_states_close_provider_clock_and_mass():
    d = packet()
    h2_fraction = .5
    width = .05
    states = []
    for step, velocity in zip(d['steps'], (30., 40.)):
        depth = step['mass_flow_kg_s'] / (h2_fraction * step['density_kg_m3'] * velocity * 2. * width)
        states.append({
            'time_s': step['time_s'], 'direction_enu': [1., 0., 0.],
            'velocity_m_s': velocity, 'density_kg_m3': step['density_kg_m3'],
            'temperature_k': step['temperature_k'], 'h2_mass_fraction': h2_fraction,
            'half_width_m': width, 'depth_m': depth,
            'provenance': 'synthetic variable provider handoff state',
        })
    d.update(direction_enu=[0., 0., 1.], vertical_handoff={
        'position_enu_m': [1., 0., 2.], 'direction_enu': [1., 0., 0.],
        'velocity_m_s': 30., 'density_kg_m3': .2, 'temperature_k': 150.,
        'h2_mass_fraction': h2_fraction, 'half_width_m': width,
        'depth_m': states[0]['depth_m'], 'provenance': 'synthetic variable handoff',
        'states': states,
    })
    release = ResolvedGasRelease.model_validate_json(json.dumps(d))
    assert [state.time_s for state in release.vertical_handoff.states] == [0., .2]
    bad = copy.deepcopy(d)
    bad['vertical_handoff']['states'][1]['depth_m'] *= 1.1
    with pytest.raises(ValueError, match='does not close provider mass flow'):
        ResolvedGasRelease.model_validate_json(json.dumps(bad))


@pytest.mark.parametrize('fault',['both','neither','inventory','position','clock','normal_frequency'])
def test_request_ownership_and_normal_vent_frequency_are_explicit(fault):
    d=request_data()
    if fault=='both':d['source_input']={'unwanted':'second source calculation'}
    if fault=='neither':d['resolved_release']=None
    if fault=='inventory':d['available_mass_kg']=9.
    if fault=='position':d['source_position_enu_m'][2]=2.
    if fault=='clock':d['evaluation_times_s'].remove(.2)
    if fault=='normal_frequency':d.update(annual_frequency_per_year=.01,annual_frequency_provenance='must not classify normal vent as accident')
    with pytest.raises(ValueError):ConsequenceRequest.model_validate_json(json.dumps(d))


def test_equipment_inventory_depletion_operator_requires_resolved_release_and_stop_basis():
    d = request_data()
    d['resolved_release']['event_kind'] = 'accidental_leak'
    d['resolved_release']['failure_opening_diameter_m'] = .01
    d['source_operator'] = 'equipment_inventory_depletion'
    d['release_termination'] = {
        'basis': 'inventory_depletion',
        'time_s': .2,
        'provenance': 'provider positive-mass threshold reached',
    }
    request = ConsequenceRequest.model_validate_json(json.dumps(d))
    assert request.source_operator == 'equipment_inventory_depletion'
    d['release_termination']['basis'] = 'synthetic_diagnostic_horizon'
    with pytest.raises(ValueError, match='inventory-depletion termination'):
        ConsequenceRequest.model_validate_json(json.dumps(d))
    d = json.loads((Path(__file__).parents[1] / 'examples' / 'consequence_request.json').read_text(encoding='utf-8'))
    d['source_operator'] = 'equipment_inventory_depletion'
    d['release_termination'] = {
        'basis': 'inventory_depletion',
        'time_s': .2,
        'provenance': 'provider positive-mass threshold reached',
    }
    with pytest.raises(ValueError, match='resolved equipment release'):
        ConsequenceRequest.model_validate_json(json.dumps(d))


def test_two_sided_release_set_closes_shared_inventory_and_requires_two_ports():
    data, release_set = two_sided_request_data()
    request = ConsequenceRequest.model_validate_json(json.dumps(data))
    assert request.source_operator == 'equipment_two_sided_rupture'
    assert request.resolved_release_set.integrated_mass_kg == pytest.approx(release_set.integrated_mass_kg)
    bad = json.loads(json.dumps(data))
    bad['resolved_release_set']['releases'][1]['port_id'] = 'vent.a'
    with pytest.raises(ValueError, match='distinct outward ports'):
        ConsequenceRequest.model_validate_json(json.dumps(bad))


def test_two_sided_release_requires_explicit_endpoint_positions():
    data, _ = two_sided_request_data()
    data['source_positions_enu_m'] = [[0., 0., 1.]]
    with pytest.raises(ValueError, match='both provider endpoint positions'):
        ConsequenceRequest.model_validate_json(json.dumps(data))


def test_two_sided_catalogue_event_binds_once_to_a_weighted_pipe_location():
    facility = Facility.model_validate_json(json.dumps(two_sided_facility_data()))
    asset = FrequencyAsset(id='pipe-segment', model_component_id='vent', profile='TNO_PIPE',
        physical_scope_ids=('pipe-location-a',), nominal_diameter_m=.0254, length_per_item_m=10.,
        pipe_conditions='default_conditions', pipe_correction_factor=1.,
        location_weight=.1, location_weight_provenance='synthetic reviewed endpoint allocation',
        classification_basis='synthetic pipe event test')
    event = next(x for x in generate_events(facility, FrequencyPlan(id='two-sided', assets=(asset,))) if x.loc == 'G1')
    bound = bind_event(ConsequenceRequest.model_validate_json(json.dumps(two_sided_request_data()[0])), event)
    assert bound.source_operator == 'equipment_two_sided_rupture'
    assert bound.frequency_event.release.mode == 'two_sided_rupture'
    assert bound.annual_frequency_per_year == pytest.approx(1e-6)


def test_two_sided_endpoints_reach_receptor_harm_with_one_shared_event():
    class Backend:
        def __init__(self):
            self.calls = 0
        def run(self, operation, payload):
            assert operation == 'consequence_chain'
            self.calls += 1
            probabilities = {'direct_fire':.25, 'delayed_flash_fire':.225,
                             'delayed_explosion':.15, 'no_ignition':.375}
            receptors = []
            for receptor in payload['receptors']:
                branch = [
                    {'direct_fire':.4, 'delayed_flash_fire':.2, 'delayed_explosion':.1, 'no_ignition':0.},
                    {'direct_fire':.7, 'delayed_flash_fire':.6, 'delayed_explosion':.5, 'no_ignition':0.},
                ]
                receptors.append({'id':receptor['id'], 'branch_harm_low_high':branch,
                    'harm_given_observed_release_low_high':[
                        sum(probabilities[k]*branch[i][k] for k in probabilities) for i in range(2)]})
            return {'data':{'status':'END_TO_END_DIAGNOSTIC_EXECUTED','full_chain_executed':True,
                'physical_validation_claim':False,'facility_validation':'WITHHELD',
                'receptors':receptors,'ignition_branch_probabilities':probabilities,
                'source':{'duration_s':.37},'mass_ledger':{'released_kg':.001,
                    'end_to_end_residual_kg':0.},'explosion':{'domain_truncated':False}},
                'elapsed_ms':1.,'backend_config_digest':'backend','worker_sha256':'worker',
                'adapter_source_digest':'adapter'}
    data, _ = two_sided_request_data()
    result = ResearchPipeline(Facility.model_validate_json(json.dumps(two_sided_facility_data())), Backend()).consequences(
        ConsequenceRequest.model_validate_json(json.dumps(data)))
    assert result['data']['source_operator'] == 'equipment_two_sided_rupture'
    assert result['data']['full_chain_executed'] is True
    assert result['data']['receptors'][0]['branch_harm_low_high'][0]['direct_fire'] == pytest.approx(.8)
    assert result['data']['mass_ledger']['released_kg'] == pytest.approx(.002)
    assert len(result['data']['endpoint_results']) == 2


@pytest.mark.parametrize('fault',['temperature','density','liquid','mach','pressure'])
def test_eos_phase_and_compressible_plane_gate(fault):
    d=packet();cp=FakeCP()
    if fault=='temperature':cp.temperature=250.
    if fault=='density':cp.density=.4
    if fault=='liquid':cp.quality=.5
    if fault=='mach':cp.sound=10.
    if fault=='pressure':d['steps'][0]['pressure_pa_abs']=200000.
    with pytest.raises(ValueError):thermodynamic_rows(d,101325.,cp)


@pytest.mark.parametrize('kind',['storage_tank','pipe','valve','pump','vaporizer','vent_stack'])
def test_resolved_port_path_is_not_tank_only_and_does_not_invoke_discharge_solver(kind):
    class Backend:
        calls=0
        def run(self,operation,payload):
            self.calls+=1
            assert operation=='consequence_chain'
            assert 'volume_m3' not in payload['source_input']['tank']
            assert payload['resolved_release']['discharge_owner']=='equipment_twin'
            assert payload['source_input']['ambient']['temperature_k']==288.15
            return {'data':{'stub_only':True}}
    backend=Backend()
    result=ResearchPipeline(Facility.model_validate_json(json.dumps(facility_data(kind))),backend).consequences(
        ConsequenceRequest.model_validate_json(json.dumps(request_data())))
    assert backend.calls==1 and result['facility_digest']


@pytest.mark.parametrize('fault',['unknown_port','inward','liquid_port','port_position','fluid','indoor'])
def test_wrong_facility_boundary_is_rejected_before_physics(fault):
    class NeverCalled:
        def run(self,*args):raise AssertionError('invalid provider/facility must not run physics')
    f=facility_data()
    if fault=='unknown_port':f['ports'][0]['id']='different.out'
    if fault=='inward':f['ports'][0]['direction']='in'
    if fault=='liquid_port':f['ports'][0]['phase']='liquid'
    if fault=='port_position':f['ports'][0]['position_enu_m']=[0.,0.,2.]
    if fault=='fluid':f['components'][0]['property_basis']={'fluid':'Hydrogen','backend':'CoolProp-HEOS','energy_reference':'CoolProp-HEOS:Hydrogen:native'}
    if fault=='indoor':f['environment']='indoor'
    with pytest.raises(ValueError):ResearchPipeline(Facility.model_validate_json(json.dumps(f)),NeverCalled()).consequences(
        ConsequenceRequest.model_validate_json(json.dumps(request_data())))


def test_raw_pressure_temperature_tags_cannot_overwrite_resolved_provider_ph_flow():
    q=ConsequenceRequest.model_validate_json(json.dumps(request_data()))
    with pytest.raises(ValueError):request_from_telemetry(q,{'values':{}},pressure_tag='PT',temperature_tag='TT')


def test_accidental_valve_frequency_can_bind_without_using_expanded_exit_diameter():
    p=packet();p.update(event_kind='accidental_leak',event_id='valve-leak',failure_opening_diameter_m=.0025,
        upstream_service='LH2',upstream_service_provenance='synthetic post-flash gas plane; flash model supplied externally and not qualified here')
    q=ConsequenceRequest.model_validate_json(json.dumps(request_data(p)))
    f=Facility.model_validate_json(json.dumps(facility_data('valve')))
    a=FrequencyAsset(id='valve',model_component_id='vent',profile='LH2_VALVE',physical_scope_ids=('valve-1',),
        nominal_diameter_m=.025,classification_basis='synthetic reviewed valve gas exit')
    plan=FrequencyPlan(id='case',assets=(a,))
    event=generate_events(f,plan)[2]  # 1% area means 10% diameter.
    bound=bind_event(q,event)
    assert bound.annual_frequency_per_year==2.2e-5
    assert math.sqrt(4*p['steps'][0]['effective_area_m2']/math.pi)!=.0025
    assert bound.resolved_release.steps[0].mass_flow_kg_s==.003
    p['upstream_service']='COLD_GH2'
    with pytest.raises(ValueError,match='LH2 literature frequency'):bind_event(
        ConsequenceRequest.model_validate_json(json.dumps(request_data(p))),event)
    p['upstream_service']='LH2'
    p['failure_opening_diameter_m']=.025
    with pytest.raises(ValueError):bind_event(ConsequenceRequest.model_validate_json(json.dumps(request_data(p))),event)


def test_accidental_liquid_frequency_binds_using_provider_failure_diameter():
    liquid = liquid_packet()
    liquid['property_basis']['fluid'] = 'Hydrogen'
    liquid['property_basis']['energy_reference'] = 'CoolProp-HEOS:Hydrogen:native'
    data = request_data()
    data.update(
        source_input=None,
        resolved_release=None,
        resolved_liquid_release=liquid,
        source_operator='equipment_liquid_release',
        available_mass_kg=5.,
        release_termination={'basis':'inventory_depletion','time_s':.37,
                             'provenance':'synthetic positive inventory threshold'},
    )
    request = ConsequenceRequest.model_validate_json(json.dumps(data))
    facility_data_value = facility_data('storage_tank')
    facility_data_value['components'][0]['property_basis']['fluid'] = 'Hydrogen'
    facility = Facility.model_validate_json(json.dumps(facility_data_value))
    asset = FrequencyAsset(
        id='storage-vessel', model_component_id='vent', profile='LH2_VESSEL',
        physical_scope_ids=('storage-shell',), nominal_diameter_m=.25,
        classification_basis='synthetic liquid provider frequency binding',
    )
    event = generate_events(facility, FrequencyPlan(id='liquid-case', assets=(asset,)))[0]
    bound = bind_event(request, event)
    assert bound.source_operator == 'equipment_liquid_release'
    assert bound.annual_frequency_per_year == pytest.approx(.00065)
    assert bound.frequency_event.release.hole_diameter_m == pytest.approx(.0025)


def test_provider_liquid_inventory_depletion_binds_without_hole_substitution():
    data = request_data()
    data.update(
        source_input=None,
        resolved_release=None,
        resolved_liquid_release=liquid_packet(),
        source_operator='equipment_liquid_release',
        available_mass_kg=5.,
        release_termination={'basis':'inventory_depletion', 'time_s':.37,
                             'provenance':'synthetic provider liquid inventory depletion'},
    )
    request = ConsequenceRequest.model_validate_json(json.dumps(data))
    facility_value = facility_data('storage_tank')
    facility_value['components'][0]['property_basis']['fluid'] = 'Hydrogen'
    facility = Facility.model_validate_json(json.dumps(facility_value))
    asset = FrequencyAsset(
        id='storage-vessel', model_component_id='vent', profile='TNO_PRESSURE_VESSEL',
        physical_scope_ids=('storage-shell',), nominal_diameter_m=.25,
        vessel_external_impact_or_operating_error=False,
        classification_basis='synthetic liquid provider inventory binding',
    )
    event = generate_events(facility, FrequencyPlan(id='liquid-inventory', assets=(asset,)))[0]
    bound = bind_event(request, event)
    assert bound.source_operator == 'equipment_liquid_release'
    assert bound.frequency_event.release.mode == 'instantaneous_inventory'
    assert bound.resolved_liquid_release.failure_opening_diameter_m == pytest.approx(.0025)


def test_zero_flow_after_closure_does_not_erase_preceding_release():
    p=packet();p['steps'][1].update(mass_flow_kg_s=0.,velocity_m_s=0.)
    p['cumulative_mass_out_kg']=.003*.2;p['cumulative_static_enthalpy_out_j']=.003*.2*3e6
    p=ResolvedGasRelease.model_validate_json(json.dumps(p))
    assert p.integrated_mass_kg==pytest.approx(.0006)


def test_resolved_liquid_provider_closes_partition_and_worker_rows():
    release = ResolvedLiquidRelease.model_validate_json(json.dumps(liquid_packet()))
    assert release.integrated_mass_kg == pytest.approx(.003 * .2 + .004 * .17)
    rows, history = resolve_liquid_rows(release.model_dump(mode='json'), 101325.)
    assert [row['time_s'] for row in rows] == [0., .2]
    assert sum(row['gas_mass_flow_kg_s'] for row in rows) == pytest.approx(.0012 + .0015)
    assert sum(row['ground_liquid_mass_flow_kg_s'] for row in rows) == pytest.approx(.0018 + .0025)
    assert all(row['discharge_recalculated'] is False for row in rows)
    assert history['discharge_recalculated'] is False
    assert history['equipment_dynamics_recalculated'] is False


def test_resolved_liquid_provider_rejects_airborne_liquid_without_adapter():
    d = liquid_packet()
    d['steps'][0]['airborne_liquid_mass_flow_kg_s'] = .001
    d['steps'][0]['ground_liquid_mass_flow_kg_s'] = .0018 - .001
    d['steps'][0]['droplet_class_outcomes'][0]['airborne_liquid_mass_flow_kg_s'] = .001
    d['steps'][0]['droplet_class_outcomes'][0]['ground_liquid_mass_flow_kg_s'] = .0018 - .001
    with pytest.raises(ValueError, match='airborne liquid'):
        ResolvedLiquidRelease.model_validate_json(json.dumps(d))


def test_liquid_provider_binds_to_consequence_contract():
    d = request_data()
    d.update(source_input=None, resolved_release=None,
             resolved_liquid_release=liquid_packet(),
             source_operator='equipment_liquid_release',
             release_termination={'basis':'inventory_depletion', 'time_s':.37,
                                  'provenance':'synthetic provider liquid inventory threshold'})
    request = ConsequenceRequest.model_validate_json(json.dumps(d))
    assert request.source_operator == 'equipment_liquid_release'
    assert request.resolved_liquid_release.phase_basis == 'two_phase'


def test_liquid_provider_requires_a_liquid_or_two_phase_facility_port():
    d = request_data()
    d.update(source_input=None, resolved_release=None,
             resolved_liquid_release=liquid_packet(),
             source_operator='equipment_liquid_release',
             release_termination={'basis':'inventory_depletion', 'time_s':.37,
                                  'provenance':'synthetic provider liquid inventory threshold'})
    class NeverCalled:
        def run(self, *args):
            raise AssertionError('invalid facility phase must not run physics')
    gas_facility = Facility.model_validate_json(json.dumps(facility_data()))
    with pytest.raises(ValueError, match='declared phase'):
        ResearchPipeline(gas_facility, NeverCalled()).consequences(
            ConsequenceRequest.model_validate_json(json.dumps(d)))
    liquid_facility = facility_data()
    liquid_facility['ports'][0]['phase'] = 'two_phase'
    class Backend:
        def run(self, operation, payload):
            assert operation == 'consequence_chain'
            assert payload['source_input']['resolved_liquid_release']['phase_basis'] == 'two_phase'
            return {'data': {'status':'END_TO_END_DIAGNOSTIC_EXECUTED'}}
    result = ResearchPipeline(Facility.model_validate_json(json.dumps(liquid_facility)), Backend()).consequences(
        ConsequenceRequest.model_validate_json(json.dumps(d)))
    assert result['data']['status'] == 'END_TO_END_DIAGNOSTIC_EXECUTED'


def test_layered_tank_network_boundary_is_audited_but_not_promoted_to_atmosphere():
    """A liquid demand boundary is inventory evidence, not a release packet."""
    from types import SimpleNamespace

    flow = SimpleNamespace(
        left='TK-1101', right='LH2-DEMAND-BOUNDARY', mass_flow_kg_s=0.115,
        transmitted_specific_enthalpy_J_kg=97600.0,
        source_port_id=None, target_port_id=None,
    )
    states = {
        'TK-1101': SimpleNamespace(pressure_Pa=400000.0, phase='twophase'),
        'LH2-DEMAND-BOUNDARY': SimpleNamespace(pressure_Pa=200000.0, phase='liquid'),
    }
    result = SimpleNamespace(
        time_s=0.1,
        tank=SimpleNamespace(
            cumulative_boundary_mass_kg=-0.0115,
            cumulative_boundary_energy_J=-1122.4,
        ),
        network_solution=SimpleNamespace(
            link_flows={'E06::COMP-02': flow}, node_states=states,
        ),
    )
    audit = audit_layered_liquid_boundary(
        [result], component_id='TK-1101', source_node='TK-1101',
        target_node='LH2-DEMAND-BOUNDARY', source_phase='liquid',
        ambient_pressure_pa=101325.0, link_name='E06::COMP-02',
    )
    assert audit.outward_mass_flow_max_kg_s == pytest.approx(0.115)
    assert audit.provider_cumulative_boundary_mass_kg == pytest.approx(-0.0115)
    assert not audit.atmospheric_boundary
    assert not audit.ready_for_resolved_liquid_release
    assert 'target boundary pressure is not ambient' in audit.blocking_reasons
    assert any('flash-gas' in reason for reason in audit.blocking_reasons)


def test_layered_tank_network_boundary_reversed_link_keeps_outward_sign():
    from types import SimpleNamespace

    flow = SimpleNamespace(
        left='LH2-DEMAND-BOUNDARY', right='TK-1101', mass_flow_kg_s=-0.2,
        transmitted_specific_enthalpy_J_kg=10.0,
        source_port_id='out', target_port_id='in',
    )
    states = {
        'TK-1101': SimpleNamespace(pressure_Pa=400000.0, phase='twophase'),
        'LH2-DEMAND-BOUNDARY': SimpleNamespace(pressure_Pa=101325.0, phase='liquid'),
    }
    result = SimpleNamespace(
        time_s=0.1, network_solution=SimpleNamespace(
            link_flows={'L': flow}, node_states=states,
        ), tank=None,
    )
    audit = audit_layered_liquid_boundary(
        [result], component_id='TK-1101', source_node='TK-1101',
        target_node='LH2-DEMAND-BOUNDARY', source_phase='liquid',
        ambient_pressure_pa=101325.0, link_name='L',
    )
    assert audit.observations[0].signed_mass_flow_kg_s == pytest.approx(0.2)
    assert audit.observations[0].outward_mass_flow_kg_s == pytest.approx(0.2)


def test_layered_tank_atmospheric_pressure_still_requires_provider_partition():
    from types import SimpleNamespace

    flow = SimpleNamespace(
        left='liquid_port', right='atmospheric_sink', mass_flow_kg_s=0.0013,
        transmitted_specific_enthalpy_J_kg=27562.7,
        source_port_id='TANK:L0', target_port_id='ATMOSPHERE:IN',
    )
    states = {
        'liquid_port': SimpleNamespace(pressure_Pa=204994.0, phase='liquid'),
        'atmospheric_sink': SimpleNamespace(pressure_Pa=101325.0, phase='liquid'),
    }
    result = SimpleNamespace(
        time_s=0.1, tank=None,
        network_solution=SimpleNamespace(
            link_flows={'liquid_out': flow}, node_states=states,
        ),
    )
    audit = audit_layered_liquid_boundary(
        [result], component_id='tank', source_node='liquid_port',
        target_node='atmospheric_sink', source_phase='liquid',
        ambient_pressure_pa=101325.0, link_name='liquid_out',
    )
    assert audit.atmospheric_boundary
    assert not audit.ready_for_resolved_liquid_release
    assert not audit.phase_partition_available
    assert not audit.exit_geometry_available
    assert not audit.termination_available


def test_provider_rate_is_retained_when_slabx_partition_is_within_gate():
    provider = [{
        'time_s': 0.0, 'total_mass_flow_kg_s': 1.0,
        'specific_enthalpy_j_kg': 100.0,
    }]
    slabsx = [{
        'time_s': 0.0, 'total_mass_flow_kg_s': 1.02,
        'gas_mass_flow_kg_s': 1.02, 'airborne_liquid_mass_flow_kg_s': 0.0,
        'ground_liquid_mass_flow_kg_s': 0.0,
        'gas_pressure_pa_abs': 101325.0, 'gas_temperature_k': 20.0,
        'gas_density_kg_m3': 2.0, 'gas_velocity_m_s': 10.0,
        'velocity_vector_m_s': [10.0, 0.0, 0.0],
        'droplet_class_outcomes': [],
    }]
    rows, audit = combine_provider_liquid_partition(
        provider, slabsx, ambient_pressure_pa=101325.0, rate_relative_tolerance=0.05,
    )
    assert rows[0]['total_mass_flow_kg_s'] == pytest.approx(1.0)
    assert rows[0]['gas_mass_flow_kg_s'] == pytest.approx(1.0)
    assert rows[0]['gas_boundary_area_m2'] == pytest.approx(0.05)
    assert audit['provider_rate_owner'] == 'equipment_twin'
    assert audit['partition_owner'] == 'SLABx-LH2'


def test_provider_rate_gate_rejects_large_slabx_mismatch():
    provider = [{'time_s': 0.0, 'total_mass_flow_kg_s': 1.0, 'specific_enthalpy_j_kg': 100.0}]
    slabsx = [{
        'time_s': 0.0, 'total_mass_flow_kg_s': 1.2,
        'gas_mass_flow_kg_s': 1.2, 'airborne_liquid_mass_flow_kg_s': 0.0,
        'ground_liquid_mass_flow_kg_s': 0.0,
        'gas_pressure_pa_abs': 101325.0, 'gas_temperature_k': 20.0,
        'gas_density_kg_m3': 2.0, 'gas_velocity_m_s': 10.0,
        'droplet_class_outcomes': [],
    }]
    with pytest.raises(ValueError, match='rate mismatch'):
        combine_provider_liquid_partition(provider, slabsx, ambient_pressure_pa=101325.0)


def test_layered_provider_endpoint_clock_uses_interval_enthalpy_and_shifts_to_start():
    packet = {
        'interval_semantics': 'provider_result_end_state_representative_for_preceding_fixed_step',
        'time_step_s': 0.5,
        'steps': [{
            'time_s': 0.5,
            'flow': {
                'mass_flow_kg_s': 2.0,
                'transmitted_specific_enthalpy_J_kg': 123.0,
            },
            'source_state': {
                'pressure_Pa': 200000.0,
                'temperature_K': 23.0,
                'density_kg_m3': 67.0,
                'specific_enthalpy_J_kg': 999.0,
            },
        }],
    }
    rows, dt = _provider_rows(packet)
    assert dt == pytest.approx(0.5)
    assert rows == [{
        'time_s': 0.0,
        'total_mass_flow_kg_s': 2.0,
        'specific_enthalpy_j_kg': 123.0,
        'source_pressure_pa': 200000.0,
        'source_temperature_k': 23.0,
        'source_density_kg_m3': 67.0,
    }]


def test_layered_slabsx_bridge_uses_strict_liquid_release_adapter():
    source = {
        'component_id': 'storage',
        'fluid': 'ParaHydrogen',
        'ambient_pressure_pa': 101325.0,
        'ambient_temperature_k': 288.15,
        'source_geometry': {
            'full_open_area_m2': 1.0e-4,
            'nozzle_height_m': 1.0,
            'direction_enu': [1.0, 0.0, 0.0],
        },
    }
    provider_rows = [{
        'time_s': 0.0,
        'total_mass_flow_kg_s': 1.0,
        'specific_enthalpy_j_kg': 1000.0,
    }]
    rows = [{
        'time_s': 0.0,
        'total_mass_flow_kg_s': 1.0,
        'gas_mass_flow_kg_s': 1.0,
        'ground_liquid_mass_flow_kg_s': 0.0,
        'airborne_liquid_mass_flow_kg_s': 0.0,
        'gas_boundary_area_m2': 0.05,
        'droplet_class_outcomes': [],
        'real_nozzle': {
            'pressure_pa': 101325.0,
            'temperature_k': 20.0,
            'density_kg_m3': 2.0,
            'velocity_m_s': 10.0,
            'effective_area_m2': 0.05,
        },
    }]
    audit = {'provider_rate_owner': 'equipment_twin', 'partition_owner': 'SLABx-LH2'}
    packet = _packet_from_bridge(source, provider_rows, rows, audit, 0.1)
    release = ResolvedLiquidRelease.model_validate_json(json.dumps(packet, allow_nan=False))
    assert release.event_kind == 'accidental_leak'
    assert release.integrated_mass_kg == pytest.approx(0.1)
    assert release.reference_area_provenance == 'SLABx-LH2 scaled atmospheric gas area'
