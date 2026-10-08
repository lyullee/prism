import copy
import pytest
from lh2_tno.sensitivity import FrequencySensitivity,frequency_sensitivity
from test_campaign import run


def scenarios():
    return tuple(FrequencySensitivity(id=str(m),asset_multipliers={'shell':m},
        provenance='synthetic deterministic sensitivity, no statistical prior') for m in (.1,1.,10.))


def test_frequency_scaling_changes_ir_and_fn_linearly_without_physics():
    base,_=run();r=frequency_sensitivity(base,scenarios())
    rid=next(iter(base['known_contribution_annual_ir_low_high']))
    for row,m in zip(r['scenarios'],(.1,1.,10.)):
        assert row['known_annual_ir_low_high'][rid]==pytest.approx([v*m for v in base['known_contribution_annual_ir_low_high'][rid]])
        assert row['known_expected_death_fn_low_high'][0]['expected_deaths']==base['known_contribution_expected_death_fn_low_high'][0]['expected_deaths']
        assert row['known_expected_death_fn_low_high'][0]['cumulative_frequency_per_year']==pytest.approx([v*m for v in base['known_contribution_expected_death_fn_low_high'][0]['cumulative_frequency_per_year']])
        assert row['total_facility_annual_ir_low_high'] is None
        assert row['declared_scope_annual_ir_low_high'] is None
        assert row['uncomputed_cases']==base['uncomputed_cases']
    assert r['fresh_physics_executed'] is False
    assert r['statistical_confidence_interval'] is False


def test_failed_or_uncomputed_asset_rank_is_withheld():
    base,_=run(fault='backend')
    r=frequency_sensitivity(base,scenarios())
    assert all(x=={'shell':None} for x in r['scenarios'][0]['asset_rank_by_known_expected_fatalities_low_high'])


@pytest.mark.parametrize('fault',['asset','frequency','harm','weight'])
def test_sensitivity_rejects_mismatched_or_nonfinite_saved_atoms(fault):
    base,_=run();base=copy.deepcopy(base)
    if fault=='asset':base['risk_atoms'][0]['asset_id']='wrong'
    if fault=='frequency':base['risk_atoms'][0]['initiating_frequency_per_year']=2.
    if fault=='harm':next(iter(base['risk_atoms'][0]['receptor_harm_low_high'].values()))[0]=float('nan')
    if fault=='weight':base['risk_atoms'][0]['conditional_weight']=2.
    with pytest.raises(ValueError):frequency_sensitivity(base,scenarios())


def test_explicit_full_asset_scope_and_unique_scenarios_required():
    base,_=run()
    with pytest.raises(ValueError):frequency_sensitivity(base,(scenarios()[0],scenarios()[0]))
    with pytest.raises(ValueError):frequency_sensitivity(base,(FrequencySensitivity(id='bad',asset_multipliers={'wrong':1.},provenance='test'),))
