import json
from pathlib import Path
from lh2_tno.backend import BackendConfig,PackagePin,tree_digest
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.service import ConsequenceService,request_from_telemetry
from test_consequences import EXAMPLE
import pytest


class Pipeline:
    def __init__(self,tmp_path):
        (tmp_path/'model.py').write_text('a=1')
        self.config=BackendConfig(interpreter='unused',packages=(PackagePin(name='test',root=str(tmp_path),sha256=tree_digest(tmp_path)),))
        self.backend=self
        self.facility=self
        self.calls=0
    def digest(self):return 'facility'
    def consequences(self,request):
        self.calls+=1
        return {'data':{'pressure':request.source_input['tank']['pressure_pa']},'elapsed_ms':100.,
            'adapter_source_digest':tree_digest(Path(__file__).parents[1]/'src/lh2_tno')}


def request():return ConsequenceRequest.model_validate_json(EXAMPLE.read_text(encoding='utf-8'))


def test_sensor_state_change_cannot_reuse_old_physics(tmp_path):
    pipeline=Pipeline(tmp_path);service=ConsequenceService(pipeline,capacity=1)
    a=request()
    service.evaluate(a)
    cached=service.evaluate(a)
    assert pipeline.calls==1 and cached['service']['exact_cache_hit']
    cached['data']['pressure']=-999.
    assert service.evaluate(a)['data']['pressure']==600000.
    normalized={'values':{'PT':{'quantity':'pressure','component_id':'storage','value_si':500000.},
        'TT':{'quantity':'temperature','component_id':'storage','value_si':20.893}}}
    b=request_from_telemetry(a,normalized,pressure_tag='PT',temperature_tag='TT')
    fresh=service.evaluate(b)
    assert pipeline.calls==2 and fresh['data']['pressure']==500000.
    assert not fresh['service']['exact_cache_hit']
    service.evaluate(a)
    assert pipeline.calls==3  # cache capacity eviction


def test_changed_backend_code_cannot_return_cached_result(tmp_path):
    pipeline=Pipeline(tmp_path);service=ConsequenceService(pipeline)
    service.evaluate(request())
    (tmp_path/'model.py').write_text('a=2')
    with pytest.raises(RuntimeError,match='revision mismatch'):service.evaluate(request())


def test_pressure_from_other_component_is_not_used_as_tank_state():
    normalized={'values':{'PT':{'quantity':'pressure','component_id':'vent','value_si':500000.},
        'TT':{'quantity':'temperature','component_id':'storage','value_si':20.893}}}
    with pytest.raises(ValueError):request_from_telemetry(request(),normalized,pressure_tag='PT',temperature_tag='TT')
