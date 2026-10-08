"""Actual backend checks: event branches, invariance, failures, exact cache."""
import copy,json,math
from validate_chain import prepare,execute,save,OUT
from lh2_tno.backend import BackendError,IsolatedBackend
from lh2_tno.contracts import Facility
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.pipeline import ResearchPipeline
from lh2_tno.service import ConsequenceService
from lh2_tno.telemetry import TelemetryNormalizer,TagMapping,Frame

config,facility,payload=prepare()
backend=IsolatedBackend(config)
pipeline=ResearchPipeline(Facility.model_validate_json(json.dumps(facility)),backend)
tests=[]

none=copy.deepcopy(payload)
none['ignition'].update(direct_probability=0.,delayed_probability_given_no_direct=0.)
none['annual_frequency_per_year']=None;none['annual_frequency_provenance']=None
result=execute('no_ignition',none,config,facility)
assert all(r['harm_given_observed_release_low_high']==[0.,0.] and r['annual_current_weather_contribution_low_high'] is None for r in result['data']['receptors'])
tests.append('no ignition -> zero combustion harm; unknown frequency -> None')

zero=copy.deepcopy(payload)
zero['source_input']['tank']['pressure_pa']=zero['source_input']['ambient']['pressure_pa']
result=execute('zero_release',zero,config,facility)
assert result['data']['mass_ledger']['released_kg']==0.
assert all(r['harm_given_observed_release_low_high']==[0.,0.] for r in result['data']['receptors'])
tests.append('zero driving pressure -> zero release, cloud, combustion harm')

rotated=copy.deepcopy(payload);rotfacility=copy.deepcopy(facility)
rotated['source_input']['nozzle']['direction_enu']=[0.,1.,0.]
rotated['source_input']['ambient']['wind_from_bearing_deg']=180.
rotated['weather']['wind_from_bearing_deg']=180.
for receptor in rotfacility['receptors']:
    x,y,z=receptor['position_enu_m'];receptor['position_enu_m']=[-y,x,z]
rot=execute('rotated_90_degrees',rotated,config,rotfacility)
base=json.loads((OUT/'gas_release_result.json').read_text(encoding='utf-8'))
assert math.isclose(rot['data']['explosion']['flammable_mass_in_domain_kg'],base['data']['explosion']['flammable_mass_in_domain_kg'],rel_tol=1e-8)
for a,b in zip(rot['data']['receptors'],base['data']['receptors']):
    assert all(math.isclose(x,y,abs_tol=1e-9) for x,y in zip(a['harm_given_observed_release_low_high'],b['harm_given_observed_release_low_high']))
tests.append('ENU/wind/fire rotation by 90 degrees preserves cloud mass and receptor harm')

for name,mutate in [('incomplete_source',lambda x:x['source_input'].update(duration_s=1.)),
    ('undeclared_pool',lambda x:(x['source_input']['nozzle'].update(height_m=.001,direction_enu=[1.,0.,-1.]),
         x['source_input']['choices'].update(droplet_correlation='henk2007_phaseII'),x['source_position_enu_m'].__setitem__(2,.001)))]:
    p=copy.deepcopy(payload);mutate(p)
    try:pipeline.consequences(ConsequenceRequest.model_validate_json(json.dumps(p)))
    except BackendError as e:tests.append(name+' correctly withheld: '+str(e))
    else:raise AssertionError(name+' was not blocked')

service=ConsequenceService(pipeline)
request=ConsequenceRequest.model_validate_json(json.dumps(payload))
first=service.evaluate(request);cached=service.evaluate(request)
assert not first['service']['exact_cache_hit'] and cached['service']['exact_cache_hit']
assert first['data']==cached['data']
tests.append('exact cache preserves the full result and distinguishes fresh physics')

normalizer=TelemetryNormalizer(tuple(TagMapping(tag=tag,component_id='storage',quantity=quantity,
    source_unit=unit,pressure_basis='absolute' if quantity=='pressure' else None,sensor_location='declared-tank-boundary')
    for tag,quantity,unit in [('PT','pressure','bar'),('TT','temperature','K')]),maximum_age_s=2.)
frame=Frame.model_validate_json(json.dumps({'stream_id':'synthetic','sequence':1,'source_time_s':100.,'arrival_time_s':100.,
    'origin':'synthetic','values':{'PT':{'value':6.,'unit':'bar','quality':'valid'},'TT':{'value':20.893,'unit':'K','quality':'valid'}}}))
normalized=normalizer.normalize(frame,now_s=100.1)
sensor=service.update_from_telemetry(request,normalized,pressure_tag='PT',temperature_tag='TT')
assert sensor['service']['exact_cache_hit'] and not sensor['telemetry_boundary']['independent_measurement_claim']
save('telemetry_result.json',sensor)
tests.append('normalized sensor tank state reaches complete consequence chain; synthetic origin retained')
save('edgecase_verification.json',{'passed':len(tests),'checks':tests,'cache_lookup_ms':cached['service']['service_elapsed_ms'],
    'telemetry_cache_lookup_ms':sensor['service']['service_elapsed_ms'],'physical_validation_claim':False})
print(json.dumps({'passed':len(tests),'checks':tests,'cache_lookup_ms':cached['service']['service_elapsed_ms']},ensure_ascii=False,indent=2))
