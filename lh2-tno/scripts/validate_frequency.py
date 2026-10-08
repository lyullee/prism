"""Generate generic LH2 events and execute one genuinely bound G3 chain."""
from pathlib import Path
import json
import math
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import BackendConfig,IsolatedBackend
from lh2_tno.contracts import Facility
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.frequency import FrequencyPlan,generate_events,bind_event,forecast_initiation_probability
from lh2_tno.pipeline import ResearchPipeline

OUT=ROOT/'results/20261008/frequency_v030'
OUT.mkdir(parents=True,exist_ok=True)
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

# Explicitly synthetic, generic equipment; no centre geometry/tags as defaults.
basis={'fluid':'Hydrogen','backend':'CoolProp-HEOS','energy_reference':'CoolProp-HEOS:Hydrogen:native'}
components=[]
for id,kind,params,pos in [
    ('tank','storage_tank',{'volume_m3':10.},[0.,0.,0.]),
    ('transfer','pipe',{'length_m':30.,'diameter_m':.025},[10.,0.,1.]),
    ('valves','valve',{},[12.,0.,1.]),
    ('pump','pump',{},[3.,0.,1.]),
    ('vaporizer','vaporizer',{},[20.,0.,1.]),
    ('vent','vent_stack',{'length_m':5.,'diameter_m':.04},[25.,0.,0.])]:
    components.append(dict(id=id,kind=kind,parameters_si=params,position_enu_m=pos,property_basis=basis))
generic=dict(id='generic-lh2-frequency-example',configuration_origin='synthetic',environment='outdoor',
    components=components,ports=[],edges=[],receptors=[{'id':'worker','position_enu_m':[10.,5.,1.8]}])
assets=[]
for id,component,profile,scope,extra in [
    ('tank-shell','tank','TNO_PRESSURE_VESSEL',['tank-shell'],{'vessel_external_impact_or_operating_error':False}),
    ('transfer-pipe','transfer','TNO_PIPE',['transfer-segment'],dict(nominal_diameter_m=.025,length_per_item_m=30.,pipe_conditions='default_conditions',pipe_correction_factor=1.)),
    ('valve-seals','valves','LH2_VALVE',['valve-1','valve-2','valve-3','valve-4'],dict(count=4,nominal_diameter_m=.025)),
    ('pump-body','pump','TNO_PUMP_CANNED',['pump-body'],dict(nominal_diameter_m=.025)),
    ('vaporizer-tubes','vaporizer','TNO_HX_INSIDE_WEAK_SHELL',['vaporizer-core'],dict(nominal_diameter_m=.01)),
    ('relief-discharge','vent','TNO_RELIEF_DEVICE',['relief-valve'],dict(relief_direct_substance_contact_and_atmospheric_discharge=True))]:
    assets.append(dict(id=id,model_component_id=component,profile=profile,physical_scope_ids=scope,
        classification_basis='synthetic declared design example; requires actual equipment review',**extra))
generic_plan=dict(id='generic-lh2-v030',assets=assets,excluded_model_components={})
for name,value in [('lh2_frequency_facility.json',generic),('lh2_frequency_plan.json',generic_plan)]:
    (ROOT/'examples'/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
facility=Facility.model_validate_json(json.dumps(generic))
plan=FrequencyPlan.model_validate_json(json.dumps(generic_plan))
start=time.perf_counter()
rows=generate_events(facility,plan)
generation_ms=(time.perf_counter()-start)*1000
save('generic_events.json',{'facility_digest':facility.digest(),'plan_digest':plan.digest(),
    'events':[e.model_dump(mode='json') for e in rows], 'elapsed_ms':generation_ms,
    'total_facility_annual_risk':None,'physical_validation_claim':False})
assert len(rows)==16
assert math.isclose(next(e for e in rows if e.asset_id=='transfer-pipe' and e.loc=='G1').annual_frequency_per_year,3e-5,rel_tol=1e-12)

# Reuse the previously demonstrated physical diagnostic with matching 10 mm
# G3 hole; leave all other LOC consequences explicitly uncomputed.
base=ROOT/'results/20261008/full_chain'
f=Facility.model_validate_json((base/'facility.json').read_text(encoding='utf-8'))
p={'id':'tank-g3-diagnostic','assets':[dict(id='shell',model_component_id='storage',profile='TNO_PRESSURE_VESSEL',
    classification_basis='synthetic pressurised storage vessel diagnostic',physical_scope_ids=['single-tank'],
    vessel_external_impact_or_operating_error=False)],
    'excluded_model_components':{x.id:'not part of this single-tank shell diagnostic' for x in f.components if x.id!='storage'}}
plan=FrequencyPlan.model_validate_json(json.dumps(p))
config=BackendConfig.model_validate_json((base/'backend_config.json').read_text(encoding='utf-8'))
pipeline=ResearchPipeline(f,IsolatedBackend(config))
events=pipeline.frequency_events(plan)
raw=json.loads((base/'gas_release_request.json').read_text(encoding='utf-8'))
raw.update(annual_frequency_per_year=None,annual_frequency_provenance=None,initiation_intensity_per_s=None)
raw['source_input']['nozzle']['diameter_m']=.01
raw['release_termination']={'basis':'synthetic_diagnostic_horizon','time_s':.2,
    'provenance':'0.2 s pulse to verify automatic frequency-to-consequence binding; not validated full-duration Purple G3'}
request=ConsequenceRequest.model_validate_json(json.dumps(raw))
bound=bind_event(request,events[2])
save('facility.json',f.model_dump(mode='json'))
save('plan.json',p)
save('template.json',request.model_dump(mode='json'))
save('bound_request.json',bound.model_dump(mode='json'))
save('backend_config.json',config.model_dump(mode='json'))
result=pipeline.consequences_for_event(plan,events[2].id,request)
save('actual_g3_chain.json',result)
data=result['data']
assert data['full_chain_executed'] and abs(data['mass_ledger']['end_to_end_residual_kg'])<1e-8
for row in data['receptors']:
    conditional=row['harm_given_observed_release_low_high']
    expected=[1e-5*x*bound.occupancy_probability for x in conditional]
    actual=row['annual_current_weather_contribution_low_high']
    assert all(abs(a-b)<1e-14 for a,b in zip(actual,expected))
save('verification.json',{'package_version':'0.3.0','catalogue_profiles':17,'catalogue_event_rows':55,
    'generic_example_events':len(rows),'generic_generation_elapsed_ms':generation_ms,
    'actual_g3_frequency_per_year':1e-5,'actual_hole_diameter_m':.01,
    'actual_chain_executed':True,'actual_chain_elapsed_ms':result['elapsed_ms'],
    'release_duration_s':.2,'duration_basis':'synthetic_diagnostic_horizon; not full G3 duration qualification',
    'annual_contribution_multiplication_verified':True,
    'uncomputed_tank_locs':[e.id for e in events[:2]],'total_facility_annual_risk':None,
    'physical_validation_claim':False,'frequency_validation_against_field_events':False,
    'forecast_60s':forecast_initiation_probability(events[2],60.)})
print((OUT/'verification.json').read_text(encoding='utf-8'))
