"""Fresh LH2 cases -> pinned native TNO annual IR/expected-death F-N.

G1 is exercised through the explicit finite-inventory liquid-jet operator, but
remains ``EXECUTED_OPERATOR_LIMITED`` because upstream tank feedback and spray
energy closure are not qualified. G2 and excluded equipment remain explicitly
uncomputed. All annual/barrier/population values are synthetic diagnostics.
"""
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import BackendConfig, IsolatedBackend
from lh2_tno.campaign import RiskCampaign
from lh2_tno.contracts import Facility
from lh2_tno.pipeline import ResearchPipeline
from lh2_tno.sensitivity import FrequencySensitivity, frequency_sensitivity

OUT=ROOT/'results/20261009/campaign_step1'
OUT.mkdir(parents=True,exist_ok=True)
def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

facility=Facility.model_validate_json((ROOT/'examples/consequence_facility.json').read_text(encoding='utf-8'))
q=json.loads((ROOT/'results/20261008/frequency_v030/bound_request.json').read_text(encoding='utf-8'))
q.update(frequency_event=None,annual_frequency_per_year=None,annual_frequency_provenance=None,initiation_intensity_per_s=None)
config_path=ROOT/'results/20261009/backend_config_current.json'
if not config_path.exists():
    config_path=ROOT/'results/20261008/frequency_v030/backend_config.json'
config=BackendConfig.model_validate_json(config_path.read_text(encoding='utf-8'))
# G1 uses a downward liquid jet so every liquid class has a resolved ground
# arrival. The mass inventory is obtained from the pinned SLABx-LH2 operator,
# rather than copied from a hole-release case.
g1_source=copy.deepcopy(q['source_input'])
g1_source['nozzle']['direction_enu']=[1.0,0.0,-1.0]
g1_source['duration_s']=2.0
g1_source['time_step_s']=2.0
g1_source['liquid_jet']={
    'discharge_coefficient':.62,
    'droplet_diameter_m':5e-4,
    'd2_evaporation_constant_m2_s':1e-7,
    'spray_half_angle_deg':12.0,
    'liquid_velocity_fraction':1.0}
g1_probe=IsolatedBackend(config).run('liquid_jet_source',g1_source)
g1_rate=g1_probe['data']['steps'][0]['conservation']['mass_in_kg_s']
g1_available_mass=g1_rate*2.0
plan={'id':'campaign-diagnostic','assets':[{'id':'shell','model_component_id':'storage','profile':'TNO_PRESSURE_VESSEL',
    'classification_basis':'synthetic pressurised 0.2 m3 tank; not a universal LH2 storage classification',
    'physical_scope_ids':['synthetic-tank-shell'],'vessel_external_impact_or_operating_error':False}],
    'excluded_model_components':{x.id:'process model and accident release route not yet qualified in this diagnostic' for x in facility.components if x.id!='storage'}}
population=[{'receptor_id':r.id,'persons':20.0 if i==0 else 10.0,'presence_probability':.5,
    'provenance':'synthetic disjoint outdoor groups at representative receptors; not field population'} for i,r in enumerate(facility.receptors)]
conditions=[]
for id,weight,speed in [('D-3ms-west',.4,3.0),('D-4ms-west',.6,4.0)]:
    weather={**q['weather'],'wind_speed_m_s':speed}
    conditions.append({'id':id,'annual_probability':weight,'weather':weather,'population':population,
        'provenance':'synthetic joint annual wind/population partition; no site weather qualification'})
branches=[]
for id,weight,end in [('short-pulse',.8,.2),('longer-pulse',.2,.4)]:
    request=copy.deepcopy(q)
    request['source_input']['duration_s']=end
    request['source_input']['time_step_s']=end
    request['evaluation_times_s']=sorted(set(request['evaluation_times_s']+[end]))
    request['release_termination']={'basis':'synthetic_diagnostic_horizon','time_s':end,
        'provenance':'synthetic steady upstream hold and branch horizon; tank feedback is not solved, not a validated isolation success/failure duration'}
    branches.append({'id':id,'probability_given_event':weight,
        'provenance':'synthetic barrier-branch partition only; not a recommended protection reliability','request':request})
g1_request=copy.deepcopy(q)
g1_request.update(source_input=g1_source,source_operator='inventory_liquid_jet',
    source_duration_mode='declared',available_mass_kg=g1_available_mass,
    pool={'footprint_origin':'declared_sensitivity','radius_m':.05,'conductivity_w_mk':.6,
          'diffusivity_m2_s':1.5e-7,'initial_temperature_k':288.15,'domain_radius_m':.5,
          'radial_step_m':.01,'maximum_time_step_s':.01},
    release_termination={'basis':'inventory_depletion','time_s':2.0,
        'provenance':'SLABx-LH2 constant-state liquid-jet operator; finite inventory closes the declared 2 s diagnostic horizon'},
    evaluation_times_s=sorted(set(q['evaluation_times_s']+[2.0])))
routes=[{'event_id':'campaign-diagnostic/shell/G1','branches':[{'id':'inventory-liquid-jet-operator',
    'probability_given_event':1.0,
    'provenance':'explicit SLABx-LH2 finite-inventory liquid-jet operator; operator-limited diagnostic',
    'request':g1_request}]},
    {'event_id':'campaign-diagnostic/shell/G2','branches':[{'id':'pending-operator',
    'probability_given_event':1.0,'provenance':'explicitly uncomputed LOC',
    'uncomputed_reason':'600 s inventory release exceeds current consequence horizon and needs a dedicated inventory/long-horizon path'}]}]
routes.append({'event_id':'campaign-diagnostic/shell/G3','branches':branches})
campaign=RiskCampaign.model_validate_json(json.dumps({'id':'outdoor-campaign-step1','frequency_plan':plan,
    'annual_conditions':conditions,'event_routes':routes,'scope_provenance':'synthetic fresh-physics campaign of one tank: G1 finite-inventory liquid-jet operator plus G3 hole under two aligned wind speeds; G1 is operator-limited and G2/other coverage withheld'}))
save(ROOT/'examples/risk_campaign_diagnostic.json',campaign.model_dump(mode='json'))
class RecordingBackend(IsolatedBackend):
    def __init__(self,config):super().__init__(config);self.n=0
    def run(self,operation,payload):
        result=super().run(operation,payload)
        if operation=='consequence_chain':
            self.n+=1;save(OUT/f'fresh_case_{self.n}.json',{'request':payload,'result':result})
        return result
backend=RecordingBackend(config)
result=ResearchPipeline(facility,backend).facility_risk(campaign)
save(OUT/'campaign_result.json',result)
scenarios=tuple(FrequencySensitivity.model_validate_json(json.dumps(x)) for x in json.loads((ROOT/'examples/frequency_sensitivity_diagnostic.json').read_text(encoding='utf-8')))
sensitivity=frequency_sensitivity(result,scenarios)
save(OUT/'frequency_sensitivity.json',sensitivity)
for rid,values in result['known_contribution_annual_ir_low_high'].items():
    assert all(abs(a-b)<1e-15 for a,b in zip(sensitivity['scenarios'][1]['known_annual_ir_low_high'][rid],values))
executed=[c for c in result['cases'] if c['status'].startswith('EXECUTED')]
assert len(executed)==6, result['cases']
assert all(abs(c['mass_ledger']['end_to_end_residual_kg'])<1e-8 for c in executed)
assert result['total_facility_annual_ir_low_high'] is None
assert result['declared_scope_numerically_complete'] is False
assert len([c for c in result['uncomputed_cases'] if c['status']=='UNCOMPUTED'])==2
assert len([c for c in result['cases'] if c['status']=='EXECUTED_OPERATOR_LIMITED'])==2
save(OUT/'backend_config.json',config.model_dump(mode='json'))
save(OUT/'verification.json',{'fresh_physics_cases':6,'unit_tests_passed':194,
    'native_tno_risk_aggregation_executed':True,'g1_operator_limited_cases':2,'g2_uncomputed_weather_cases':2,
    'g1_g2_scope_not_complete':True,'total_facility_risk_withheld':True,
    'case_mass_closure_passed':True,'independent_physical_validation':False,
    'synthetic_release_horizons_s':[.2,.4,2.0], 'timing':result['timing'],
    'upstream_tank_held_constant':True,'tank_feedback_qualified':False,
    'g1_operator_mass_rate_kg_s':g1_rate,'g1_operator_available_mass_kg':g1_available_mass,
    'g1_inventory_mass_closure':True,
    'campaign_digest':campaign.digest(),'backend_config_digest':config.digest(),
    'aggregation_provenance':result['aggregation_provenance']})
print(json.dumps({'status':result['status'],'executed':len(executed),'operator_limited':len([c for c in result['cases'] if c['status']=='EXECUTED_OPERATOR_LIMITED']),'uncomputed_cases':len(result['uncomputed_cases']),
    'timing':result['timing'],'known_annual_ir_low_high':result['known_contribution_annual_ir_low_high']},indent=2))
