import json
import pytest
from lh2_tno.contracts import Facility
from lh2_tno.pipeline import ResearchPipeline
from test_contracts import facility_data


class NeverCalled:
    def run(self,*args):raise AssertionError('invalid requests must not invoke physics')


@pytest.mark.parametrize('fault',['basis','volume','component','environment'])
def test_facility_mismatch_is_rejected_before_physics(fault):
    d=facility_data()
    if fault=='environment':d['environment']='indoor'
    f=Facility.model_validate_json(json.dumps(d))
    payload={'tank':{'fluid':'ParaHydrogen','volume_m3':10.}}
    if fault=='basis':payload['tank']['fluid']='Hydrogen'
    if fault=='volume':payload['tank']['volume_m3']=20.
    with pytest.raises(ValueError):
        ResearchPipeline(f,NeverCalled()).source('missing' if fault=='component' else 'tank',payload,available_mass_kg=10.,position_enu_m=(0.,0.,0.))
