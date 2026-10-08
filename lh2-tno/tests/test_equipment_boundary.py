"""Provider ownership, PH checks, event clocks, ports and frequency semantics."""
import copy
import json
import math
from pathlib import Path
import pytest
from lh2_tno.contracts import Facility
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.equipment_boundary import ResolvedGasRelease,thermodynamic_rows
from lh2_tno.frequency import FrequencyAsset,FrequencyPlan,generate_events,bind_event
from lh2_tno.pipeline import ResearchPipeline
from lh2_tno.service import request_from_telemetry


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


def facility_data(kind='vent_stack'):
    parameters={'vent_stack':{'length_m':6.,'diameter_m':.0254},'pipe':{'length_m':1.,'diameter_m':.0254},
                'storage_tank':{'volume_m3':1.}}.get(kind,{})
    return {'id':'generic-provider','configuration_origin':'synthetic','environment':'outdoor',
        'components':[{'id':'vent','kind':kind,'position_enu_m':[0.,0.,0.],
        'parameters_si':parameters,'property_basis':packet()['property_basis']}],
        'ports':[{'id':'vent.out','component_id':'vent','phase':'vapour','direction':'out'}],'edges':[],
        'receptors':[{'id':'worker','position_enu_m':[2.,0.,1.]}]}


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


def test_zero_flow_after_closure_does_not_erase_preceding_release():
    p=packet();p['steps'][1].update(mass_flow_kg_s=0.,velocity_m_s=0.)
    p['cumulative_mass_out_kg']=.003*.2;p['cumulative_static_enthalpy_out_j']=.003*.2*3e6
    p=ResolvedGasRelease.model_validate_json(json.dumps(p))
    assert p.integrated_mass_kg==pytest.approx(.0006)
