"""Run real local components without changing their source or frozen evidence."""
from pathlib import Path
import json, os, platform, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import BackendConfig, IsolatedBackend, PackagePin, tree_digest
from lh2_tno.contracts import Facility
from lh2_tno.source import integrated_source
from lh2_tno.risk import FluxStep, thermal_dose
from lh2_tno.pipeline import ResearchPipeline
from dataclasses import asdict

DOCU=Path(os.environ['PRISM_LOCAL_MODELS_ROOT']).expanduser() if os.environ.get('PRISM_LOCAL_MODELS_ROOT') else None
OUTPUT=ROOT/'results'/'20261008'
OUTPUT.mkdir(parents=True,exist_ok=True)

def save(name,data):
    (OUTPUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

if DOCU is None:
    raise SystemExit('set PRISM_LOCAL_MODELS_ROOT to run this optional local-model audit')
roots={
 'slabx_lh2':DOCU/'SLABx_LH2/slabx-lh2/source/slabx-lh2/slabx_lh2',
 'lh2dt':DOCU/'액화수소 저장탱크_밴트 시스템/06_액화수소_디지털트윈_물리모델/src/lh2dt',
 'dynamiclh2poolx':DOCU/'SLABx_LH2/논문화/PSEP_rebuild_2026-10-01/unified_runtime_2026-10-07/dependencies/DynamicLH2PoolX/src/dynamiclh2poolx',
 'prism_qra':ROOT/'src/prism_qra'}
config=BackendConfig(interpreter=str(DOCU/'SLABx_LH2/.venv-transfer/Scripts/python.exe'),
    packages=tuple(PackagePin(name=name,root=str(path),sha256=tree_digest(path)) for name,path in roots.items()),
    required_versions={'CoolProp':'8.0.0','numpy':'2.5.3','scipy':'1.18.1'},timeout_s=120.)
save('backend_config.json',config.model_dump(mode='json'))
backend=IsolatedBackend(config)

def facility(name,volume):
    basis={'fluid':'Hydrogen','energy_reference':'CoolProp-HEOS:Hydrogen:native'}
    components=[{'id':'storage','kind':'storage_tank','position_enu_m':[0,0,0],'property_basis':basis,'parameters_si':{'volume_m3':volume}},
                {'id':'isolation','kind':'valve','position_enu_m':[1,0,0],'property_basis':basis},
                {'id':'transfer','kind':'pipe','position_enu_m':[2,0,0],'property_basis':basis,'parameters_si':{'length_m':5.,'diameter_m':.0254}},
                {'id':'terminal','kind':'boundary' if name=='transfer_station' else 'vaporizer' if name=='refuelling_station' else 'vent_stack','position_enu_m':[7,0,5],'property_basis':basis,'parameters_si':{'length_m':6.,'diameter_m':.0254}}]
    ports=[]; edges=[]
    for i,c in enumerate(components):
        if i:ports.append({'id':c['id']+'.in','component_id':c['id'],'phase':'any','direction':'in'})
        if i<3:ports.append({'id':c['id']+'.out','component_id':c['id'],'phase':'any','direction':'out'})
        if i:edges.append({'id':f'link{i}','source_port':components[i-1]['id']+'.out','target_port':c['id']+'.in'})
    d={'id':name,'configuration_origin':'synthetic','environment':'outdoor','components':components,'ports':ports,'edges':edges,
       'receptors':[{'id':f'R{i}','position_enu_m':[float(i*10),0.,1.8]} for i in range(1,4)]}
    return Facility.model_validate_json(json.dumps(d))

example_dir=ROOT/'examples';example_dir.mkdir(exist_ok=True)
for name,volume in [('storage_terminal',50.),('refuelling_station',10.),('transfer_station',5.)]:
    f=facility(name,volume); p=example_dir/(name+'.json');p.write_text(f.model_dump_json(indent=2),encoding='utf-8')
    assert Facility.model_validate_json(p.read_text(encoding='utf-8')).digest()==f.digest()

source_payload={
 'tank':{'pressure_pa':600000.,'temperature_k':20.893,'volume_m3':.2,'vapour_quality':0.,'wall_heat_input_w':0.,'fluid':'Hydrogen'},
 'pipe_sections':[], 'nozzle':{'diameter_m':.0127,'length_m':.01,'height_m':.05,'direction_enu':[1.,0.,-1.],'discharge_coefficient':1.,'resistance_k':0.},
 'ambient':{'pressure_pa':101325.,'temperature_k':288.15,'wind_speed_m_s':0.,'wind_from_bearing_deg':None},
 'choices':{'phase_model':'HEM','hnem_eta':None,'fictitious_nozzle':'momentum_adiabatic','droplet_correlation':'rescigno_yellow_book','rescigno_quality_path':'printed_equation','distribution':'single_smd'},
 'duration_s':.2,'time_step_s':.2}
ledger,response=integrated_source(backend,source_payload,available_mass_kg=10.,position_enu_m=(0.,0.,.05))
flow=ledger.steps[0].total_kg_s
assert abs(flow*1000-1051.7)<.2
assert abs(ledger.released_mass_kg-sum(ledger.branch_mass_kg(k) for k in ('gas_kg_s','airborne_liquid_kg_s','ground_liquid_kg_s')))<1e-10
save('source_request.json',source_payload);save('source_result.json',response);save('source_ledger.json',ledger.model_dump(mode='json'))

stack_payload={'fluid':'Hydrogen','upstream':{'pressure_Pa':400000.,'temperature_K':150.},
               'downstream':{'pressure_Pa':101325.,'temperature_K':288.15},
               'stack':{'length_m':6.,'inner_diameter_m':.0254,'roughness_m':1.5e-6,'local_loss_coefficient':2.,
                        'elevation_change_m':6.,'ambient_temperature_K':288.15,'ambient_UA_W_K':5.,'integration_segments':64,'allow_reverse':False}}
stack=backend.run('vent_stack',stack_payload)
assert stack['data']['hydraulic']['mass_flow_kg_s']>0
assert abs(stack['data']['energy_residual_w'])<1e-6
save('vent_request.json',stack_payload);save('vent_result.json',stack)

pool_payload={'inflow_origin':'synthetic_declared_ground',
    'surface':{'name':'declared-concrete','conductivity_W_mK':.88,'diffusivity_m2_s':1.5775e-7,'initial_temperature_K':195.7},
    'numerics':{'domain_radius_m':1.,'source_radius_m':.2,'radial_step_m':.05,'maximum_time_step_s':.01},
    'inflow_times_s':[0.,.5],'inflow_rates_kg_s':[1.,0.],'output_times_s':[0.,.25,.5,1.]}
pool=backend.run('declared_pool',pool_payload)
assert abs(pool['data']['mass_balance_residual_kg'])<1e-8
assert pool['data']['ledger'][2]['liquid_mass_kg']>0
assert pool['data']['ledger'][3]['cumulative_evaporation_kg']>pool['data']['ledger'][2]['cumulative_evaporation_kg']
save('pool_request.json',pool_payload);save('pool_result.json',pool)

dose=thermal_dose((FluxStep(time_s=0.,heat_flux_w_m2=10000.),FluxStep(time_s=20.,heat_flux_w_m2=10000.)))
damage=backend.run('thermal_damage',{'equivalent_heat_flux_w_m2':dose['equivalent_heat_flux_w_m2'],'exposure_s':dose['exposure_s']})
save('thermal_damage_example.json',{'input_origin':'synthetic prescribed radiation, not calculated fire','dose':dose,'result':damage})

assurance_payload={'outputs':[{'component':'LH2-source','version':config.digest(),'quantity':'source_mass_flow','unit':'kg/s',
     'observation_operator':'instantaneous','source_fingerprint':ledger.digest(),'receptor_fingerprint':'no-receptor',
     'evidence_ids':[],'status':'diagnostic','interval':[flow,flow],'conditions_satisfied':False}], 'records':[]}
gate=backend.run('assurance',assurance_payload)
assert gate['data']['state']=='WITHHOLD_OR_ESCALATE' and gate['data']['interval'] is None
save('assurance_result.json',gate)
# Bind the actual source to a facility whose declared volume and property basis match.
bound=facility('source_component_example',.2)
evaluation=ResearchPipeline(bound,backend).source('storage',source_payload,available_mass_kg=10.,position_enu_m=(0.,0.,.05))
assert evaluation.reporting_interval_kg_s is None
save('facility_source_evaluation.json',{**asdict(evaluation),'ledger':evaluation.ledger.model_dump(mode='json')})
summary={'date_kst':'2026-10-08','facility_roundtrips':3,'source_mass_flow_kg_s':flow,'source_partition_closed':True,
 'source_energy_scope':ledger.energy_balance_scope,'source_elapsed_ms':response['elapsed_ms'],
 'vent_exit_temperature_K':stack['data']['outlet']['temperature_K'],'vent_energy_residual_w':stack['data']['energy_residual_w'],
 'vent_elapsed_ms':stack['elapsed_ms'],'thermal_damage_probability_given_synthetic_flux':damage['data']['harm_probability'],
 'declared_pool_executed':True,'declared_pool_connected_to_jet':False,'pool_elapsed_ms':pool['elapsed_ms'],
 'pool_mass_balance_residual_kg':pool['data']['mass_balance_residual_kg'],
 'pool_liquid_at_release_end_kg':pool['data']['ledger'][2]['liquid_mass_kg'],
 'pool_post_release_evaporation_kg':pool['data']['ledger'][3]['cumulative_evaporation_kg']-pool['data']['ledger'][2]['cumulative_evaporation_kg'],
 'evidence_gate_state':gate['data']['state'],'physical_validation_claim':False,
 'facility_source_evidence_gate_connected':True,'full_chain_completed':False,'realtime_requirement_demonstrated':False,'platform':platform.platform(),
 'python':sys.version,'backend_config_digest':config.digest()}
save('integration_summary.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
