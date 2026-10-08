"""Verify legacy diagnostic gas/pool routes after equipment-source branching."""
from pathlib import Path
import json
import math
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import BackendConfig,IsolatedBackend
from lh2_tno.contracts import Facility
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.pipeline import ResearchPipeline

base=ROOT/'results/20261008/full_chain'
out=ROOT/'results/20261008/equipment_coupling_v040'
f=Facility.model_validate_json((base/'facility.json').read_text(encoding='utf-8'))
config=BackendConfig.model_validate_json((base/'backend_config.json').read_text(encoding='utf-8'))
pipeline=ResearchPipeline(f,IsolatedBackend(config))
checks=[]
for name in ('gas_release','rainout_pool'):
    request=ConsequenceRequest.model_validate_json((base/(name+'_request.json')).read_text(encoding='utf-8'))
    result=pipeline.consequences(request)
    (out/(name+'_regression.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    previous=json.loads((base/(name+'_result.json')).read_text(encoding='utf-8'))['data']
    current=result['data']
    assert current['full_chain_executed']
    for key,value in previous['mass_ledger'].items():
        assert math.isclose(current['mass_ledger'][key],value,rel_tol=1e-8,abs_tol=1e-9),(name,key)
    for new,old in zip(current['receptors'],previous['receptors']):
        assert new['id']==old['id']
        assert all(math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-10) for a,b in zip(
            new['harm_given_observed_release_low_high'],old['harm_given_observed_release_low_high']))
    checks.append({'case':name,'previous_mass_and_harm_reproduced':True,'elapsed_ms':result['elapsed_ms']})
(out/'regression_verification.json').write_text(json.dumps({'checks':checks,'physical_validation_claim':False},indent=2),encoding='utf-8')
print(json.dumps(checks))
