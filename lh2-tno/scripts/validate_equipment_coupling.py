"""Run real equipment-network gas exits through SLAB and TNO damage.

The normal-vent example uses declared horizontal geometry and a 0.37 s
closure clock. It tests the coupling, not real centre geometry or a
provider transient with leak feedback.
"""
from pathlib import Path
import copy
import json
import math
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import CoolProp.CoolProp as CP
from external_paths import required_external_path
from lh2_tno.backend import BackendConfig,PackagePin,tree_digest,IsolatedBackend,BackendError
from lh2_tno.contracts import Facility,canonical_digest
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.equipment_boundary import ResolvedGasRelease
from lh2_tno.pipeline import ResearchPipeline

OUT=ROOT/'results/20261008/equipment_coupling_v040'
OUT.mkdir(parents=True,exist_ok=True)
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

provider=required_external_path('PRISM_LH2DT_SRC_ROOT', 'the optional equipment digital-twin source root')
provider_digest=tree_digest(provider)
raw=json.loads((ROOT/'results/20261008/full_chain/backend_config.json').read_text(encoding='utf-8'))
raw['packages']=[p for p in raw['packages'] if p['name']!='lh2dt']
raw['packages'].append(PackagePin(name='lh2dt',root=str(provider),sha256=provider_digest).model_dump(mode='json'))
config=BackendConfig.model_validate_json(json.dumps(raw))
backend=IsolatedBackend(config)
fluid='ParaHydrogen';ambient_pressure=101325.;ambient_temperature=288.15
def ph(pressure,temperature):
    return {'pressure_pa_abs':pressure,'specific_enthalpy_j_kg':CP.PropsSI('H','P',pressure,'T',temperature,fluid)}
exports=[];inputs=[]
for pressure,temperature in [(101525.,150.),(101625.,160.)]:
    payload={'fluid':fluid,'provider_link_id':'VENT_OUTLET','upstream':ph(pressure,temperature),
        'downstream':ph(ambient_pressure,ambient_temperature),
        'stack':{'length_m':6.,'inner_diameter_m':.0254,'roughness_m':1.5e-6,
                 'local_loss_coefficient':2.,'elevation_change_m':0.,
                 'ambient_temperature_K':ambient_temperature,'ambient_UA_W_K':5.,'integration_segments':64}}
    response=backend.run('equipment_network_exit',payload)
    inputs.append(payload);exports.append(response)
save('native_provider_inputs.json',inputs)
save('native_provider_exports.json',exports)
steps=[]
for time,response in zip((0.,.2),exports):
    d=response['data'];state=d['outlet']
    steps.append({'time_s':time,'mass_flow_kg_s':d['flow']['mass_flow_kg_s'],
        'pressure_pa_abs':state['pressure_Pa'],'specific_enthalpy_j_kg':state['specific_enthalpy_J_kg'],
        'temperature_k':state['temperature_K'],'density_kg_m3':state['density_kg_m3'],
        'effective_area_m2':d['effective_area_m2'],'velocity_m_s':d['velocity_m_s'],
        'area_provenance':'synthetic horizontal terminal plane using declared native stack bore',
        'velocity_origin':d['velocity_origin']})
ends=[.2,.37]
mass=sum(x['mass_flow_kg_s']*(end-x['time_s']) for x,end in zip(steps,ends))
energy=sum(x['mass_flow_kg_s']*x['specific_enthalpy_j_kg']*(end-x['time_s']) for x,end in zip(steps,ends))
basis={'fluid':fluid,'backend':'CoolProp-HEOS','energy_reference':f'CoolProp-HEOS:{fluid}:native'}
packet={'component_id':'vent','port_id':'vent.out','event_id':'normal-vent-diagnostic',
    'event_kind':'normal_vent','enthalpy_convention':'static_exit_enthalpy','property_basis':basis,
    'upstream_service':'COLD_GH2','upstream_service_provenance':'native provider PH gas states at 150/160 K',
    'provider_source_digest':provider_digest,'provider_result_digest':canonical_digest(exports),
    'provider_boundary_reference':'SteadyNetwork.link_flows[VENT_OUTLET] transmitted enthalpy + ATMOSPHERE pressure',
    'input_origin':'synthetic','position_enu_m':[0.,0.,1.],'direction_enu':[1.,0.,0.],
    'ambient_pressure_pa_abs':ambient_pressure,'ambient_temperature_k':ambient_temperature,
    'duration_s':.37,'available_mass_kg':1.,'cumulative_mass_out_kg':mass,
    'cumulative_static_enthalpy_out_j':energy,'steps':steps,
    'termination_provenance':'synthetic command closure at 0.37 s; two prescribed native steady states, not a solved tank transient'}
release=ResolvedGasRelease.model_validate_json(json.dumps(packet))
facility={'id':'generic-resolved-gas-coupling','configuration_origin':'synthetic','environment':'outdoor',
    'components':[{'id':'vent','kind':'vent_stack','position_enu_m':[0.,0.,0.],
                   'property_basis':basis,'parameters_si':{'length_m':6.,'diameter_m':.0254}}],
    'ports':[{'id':'vent.out','component_id':'vent','phase':'vapour','direction':'out'}],'edges':[],
    'receptors':[{'id':'near','position_enu_m':[2.,0.,1.]},{'id':'downwind','position_enu_m':[10.,0.,1.]}]}
f=Facility.model_validate_json(json.dumps(facility))
request=json.loads((ROOT/'results/20261008/full_chain/gas_release_request.json').read_text(encoding='utf-8'))
request.update(component_id='vent',source_input=None,resolved_release=release.model_dump(mode='json'),
    available_mass_kg=1.,source_position_enu_m=[0.,0.,1.],annual_frequency_per_year=None,
    annual_frequency_provenance=None,frequency_event=None,initiation_intensity_per_s=None,
    release_termination={'basis':'synthetic_diagnostic_horizon','time_s':.37,'provenance':packet['termination_provenance']},
    evaluation_times_s=[0.,.1,.2,.37,.5,1.,2.,3.,4.,5.,10.,20.])
q=ConsequenceRequest.model_validate_json(json.dumps(request))
save('facility.json',facility);save('resolved_release.json',release.model_dump(mode='json'))
save('request.json',q.model_dump(mode='json'));save('backend_config.json',config.model_dump(mode='json'))
result=ResearchPipeline(f,backend).consequences(q)
save('actual_equipment_to_harm.json',result)
d=result['data']
assert d['full_chain_executed'] and d['source']['discharge_recalculated'] is False
assert d['source']['equipment_dynamics_recalculated'] is False
assert math.isclose(d['mass_ledger']['released_kg'],mass,rel_tol=1e-10)
assert abs(d['mass_ledger']['end_to_end_residual_kg'])<1e-9
assert all(x['annual_current_weather_contribution_low_high'] is None for x in d['receptors'])
assert [x['time_s'] for x in d['source']['steps']]==[0.,.2]
assert max(x['entry_temperature_k'] for x in d['handoffs'])>100.
# Replay the earlier high-pressure terminal assumption: reject, do not silently
# replace the provider flow or infer a missing compressible expansion plane.
high=copy.deepcopy(inputs[0]);high['upstream']=ph(400000.,150.)
response=backend.run('equipment_network_exit',high)
row=response['data'];s=row['outlet']
bad=copy.deepcopy(request);badstep=bad['resolved_release']['steps'][0]
badstep.update(mass_flow_kg_s=row['flow']['mass_flow_kg_s'],pressure_pa_abs=s['pressure_Pa'],
    specific_enthalpy_j_kg=s['specific_enthalpy_J_kg'],temperature_k=s['temperature_K'],density_kg_m3=s['density_kg_m3'],
    effective_area_m2=row['effective_area_m2'],velocity_m_s=row['velocity_m_s'])
bad['resolved_release']['steps']=[badstep]
bad['resolved_release']['cumulative_mass_out_kg']=badstep['mass_flow_kg_s']*.37
bad['resolved_release']['cumulative_static_enthalpy_out_j']=badstep['mass_flow_kg_s']*badstep['specific_enthalpy_j_kg']*.37
try:
    ResearchPipeline(f,backend).consequences(ConsequenceRequest.model_validate_json(json.dumps(bad)))
    raise AssertionError('high-Mach assumed terminal plane should be rejected')
except BackendError as error:
    assert 'Mach' in str(error)
    high_gate={'rejected':True,'reason':str(error),'provider_flow_recomputed_by_consumer':False}
save('high_pressure_plane_gate.json',high_gate)
assert provider_digest==tree_digest(provider)
save('verification.json',{'version':'0.4.0','actual_provider_network_executed':True,
    'provider_export_PH_preserved':True,'resolved_flow_to_complete_harm_chain_executed':True,
    'source_mass_flow_recalculated':False,'tank_dynamics_recalculated':False,
    'provider_mass_kg':mass,'static_enthalpy_transport_j':energy,'event_closure_time_s':.37,
    'provider_temperature_preserved_above_100K':True,'normal_vent_annual_frequency_applied':False,
    'high_Mach_terminal_assumption_rejected':True,'provider_source_unchanged':True,
    'elapsed_ms':result['elapsed_ms'],'physical_validation_claim':False,
    'full_facility_twin_feedback_integrated':False,'vertical_vent_supported':False,
    'scope':'two prescribed native steady equipment states; horizontal atmospheric gas exit Mach<=0.3; no field data or 1Hz claim'})
print((OUT/'verification.json').read_text(encoding='utf-8'))
