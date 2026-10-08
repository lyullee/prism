import pytest
from lh2_tno.backend import BackendError
from lh2_tno.source import ledger_from_response, integrated_source


def test_incomplete_native_source_cannot_be_extrapolated():
    payload={'duration_s':1.,'time_step_s':.2}
    response={'data':{'steps':[{'time_s':0.}]}}
    with pytest.raises(BackendError,match='ended early'):
        ledger_from_response(payload,response,available_mass_kg=10.,position_enu_m=(0.,0.,0.))


def test_empty_native_source_has_no_usable_history():
    with pytest.raises(BackendError):
        ledger_from_response({}, {'data':{'steps':[]}},available_mass_kg=10.,position_enu_m=(0.,0.,0.))


class NeverCalled:
    def run(self,*args):raise AssertionError('invalid boundaries must not invoke physics')


@pytest.mark.parametrize('mass,position',[(0.,(0.,0.,.05)),(True,(0.,0.,.05)),(10.,(0.,0.,5.))])
def test_invalid_inventory_or_geometry_fails_before_physics(mass,position):
    with pytest.raises(ValueError):
        integrated_source(NeverCalled(),{'nozzle':{'height_m':.05}},available_mass_kg=mass,position_enu_m=position)
