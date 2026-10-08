"""Execute the actual release-to-human-harm chain and save reviewable results."""
from pathlib import Path
import copy
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import BackendConfig,PackagePin,tree_digest,IsolatedBackend
from lh2_tno.contracts import Facility
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.pipeline import ResearchPipeline

OUT=ROOT/'results'/'20261008'/'full_chain'
OUT.mkdir(parents=True,exist_ok=True)
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def prepare():
    old=json.loads((ROOT/'results/20261008/backend_config.json').read_text(encoding='utf-8'))
    # This chain does not invoke lh2dt. Pin only the libraries actually used;
    # retain the previous component-only config and its evidence unchanged.
    old['packages']=[p for p in old['packages'] if p['name']!='lh2dt']
    root=Path(r'C:\Users\lyul\Desktop\DocuData\SLABx_LH2\.venv-transfer\Lib\site-packages\slabx')
    old['packages'].append(PackagePin(name='slabx',root=str(root),sha256=tree_digest(root)).model_dump())
    old['timeout_s']=180.
    config=BackendConfig.model_validate_json(json.dumps(old))
    save('backend_config.json',config.model_dump(mode='json'))
    facility=json.loads((ROOT/'examples/storage_terminal.json').read_text(encoding='utf-8'))
    facility['components'][0]['parameters_si']['volume_m3']=.2
    facility['receptors']=[{'id':name,'position_enu_m':pos} for name,pos in [
        ('near_worker',[2.,0.,1.]),('downwind_worker',[10.,0.,.1]),
        ('side_worker',[25.,4.,1.8]),('distant_worker',[60.,0.,1.8])]]
    save('facility.json',facility)
    source=json.loads((ROOT/'results/20261008/source_request.json').read_text(encoding='utf-8'))
    source['nozzle']['direction_enu']=[1.,0.,0.]
    source['ambient'].update(wind_speed_m_s=3.,wind_from_bearing_deg=270.)
    payload={'component_id':'storage','source_input':source,'available_mass_kg':10.,'source_position_enu_m':[0.,0.,.05],
        'weather':{'wind_speed_m_s':3.,'wind_from_bearing_deg':270.,'relative_humidity':.5},
        'ignition':{'direct_probability':.1,'delayed_probability_given_no_direct':.2,
            'explosion_probability_given_delayed':.4,'delayed_time_s':1.,'burn_back_duration_s':2.,
            'obstructed_energy_fraction':.08,'provenance':'synthetic declared sensitivity; not center-derived ignition frequency'},
        'domain':{'downwind_bounds_m':[-2.,80.],'crosswind_bounds_m':[-10.,10.],
            'height_bounds_m':[0.,12.],'cell_size_m':.5},
        'evaluation_times_s':[0.,.1,.2,.3,.5,1.,2.,3.,4.,5.,10.,20.],
        'radiative_fraction_range':[.06,.12],
        'radiation_provenance':'LH2 spill radiation sensitivity consistent with existing TNO spill_fire range; not a universal jet calibration',
        'annual_frequency_per_year':.001,'annual_frequency_provenance':'synthetic demonstration only',
        'initiation_intensity_per_s':1e-6,'dispersion_x_max_m':100.,'transition_x_max_m':50.,'transition_dx_m':.05}
    return config,facility,payload

def execute(name,payload,config,facility):
    request=ConsequenceRequest.model_validate_json(json.dumps(payload))
    save(name+'_request.json',request.model_dump(mode='json'))
    result=ResearchPipeline(Facility.model_validate_json(json.dumps(facility)),IsolatedBackend(config)).consequences(request)
    save(name+'_result.json',result)
    d=result['data']
    assert d['full_chain_executed']
    assert abs(d['mass_ledger']['end_to_end_residual_kg'])<1e-8
    assert abs(sum(d['ignition_branch_probabilities'].values())-1)<1e-10
    for row in d['cloud_history_unignited_counterfactual']:
        assert abs(row['mass_residual_kg'])<1e-8
        assert row['flammable_mass_in_domain_kg']<=row['vapour_emitted_kg']+1e-8
    for receptor in d['receptors']:
        assert all(0<=x<=1 for x in receptor['harm_given_observed_release_low_high'])
    summary={'case':name,'full_chain_executed':True,'elapsed_ms':result['elapsed_ms'],
        'mass_ledger':d['mass_ledger'],'pool_executed':d['pool'] is not None,
        'cloud_at_ignition':d['explosion'],'stage_elapsed_ms':d['stage_elapsed_ms'],
        'receptor_harm_low_high':{r['id']:r['harm_given_observed_release_low_high'] for r in d['receptors']},
        'physical_validation_claim':False,'realtime_requirement_demonstrated':False}
    save(name+'_summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    return result

if __name__=='__main__':
    config,facility,payload=prepare()
    gas=execute('gas_release',payload,config,facility)
    liquid=copy.deepcopy(payload)
    liquid['source_input']['nozzle'].update(height_m=.001,direction_enu=[1.,0.,-1.])
    liquid['source_position_enu_m'][2]=.001
    liquid['source_input']['choices']['droplet_correlation']='henk2007_phaseII'
    liquid['pool']={'footprint_origin':'declared_sensitivity','radius_m':.2,
        'conductivity_w_mk':.88,'diffusivity_m2_s':1.5775e-7,'initial_temperature_k':288.15,
        'domain_radius_m':2.,'radial_step_m':.025,'maximum_time_step_s':.01}
    pool_result=execute('rainout_pool',liquid,config,facility)
    d=pool_result['data']
    assert d['pool'] is not None and d['mass_ledger']['ground_inflow_kg']>0
    end=next(r for r in d['pool']['ledger'] if r['time_s']==.2)
    assert end['liquid_mass_kg']>0
    assert d['pool']['ledger'][-1]['cumulative_evaporation_kg']>end['cumulative_evaporation_kg']
    summary={'gas_executed':True,'rainout_pool_executed':True,
        'pool_input_derived_from_source':True,'pool_footprint_origin':'declared_sensitivity',
        'post_release_evaporation_checked':True,'unit_and_contract_tests':68,
        'full_chain_executed':True,'physical_validation_claim':False,'realtime_requirement_demonstrated':False}
    save('verification.json',summary)
