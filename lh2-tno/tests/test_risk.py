import math
import pytest
from lh2_tno.risk import AnnualScenario, FluxStep, HazardInterval, annual_risk, first_event_harm_probability, harm_given_observed_release, thermal_dose


def test_constant_first_event_has_analytic_solution():
    r=first_event_harm_probability((HazardInterval(duration_s=300.,initiation_intensity_per_s=.002,harm_probability_given_initiation=.4),))
    assert r["value"]==pytest.approx(.4*(1-math.exp(-.6)))


def test_discretization_does_not_create_independent_repeated_events():
    a=HazardInterval(duration_s=300.,initiation_intensity_per_s=.002,harm_probability_given_initiation=.4)
    b=HazardInterval(duration_s=1.,initiation_intensity_per_s=.002,harm_probability_given_initiation=.4)
    assert first_event_harm_probability((b,)*300)["value"]==pytest.approx(first_event_harm_probability((a,))["value"])


def test_zero_intensity_and_already_observed_release_are_distinct():
    assert first_event_harm_probability((HazardInterval(duration_s=60.,initiation_intensity_per_s=0.,harm_probability_given_initiation=.7),))["value"]==0
    assert harm_given_observed_release(.7,horizon_s=60.)["value"]==.7


def test_very_small_hazards_are_not_rounded_to_zero():
    r=first_event_harm_probability((HazardInterval(duration_s=1.,initiation_intensity_per_s=1e-18,harm_probability_given_initiation=1.),))
    assert r['initiation_probability']==pytest.approx(1e-18,abs=1e-30)


def scenario(**kw):
    d=dict(id="leak/D",initiating_event_id="leak",weather_class="D",frequency_per_year=.01,
           harm_probability_given_event=.2,annual_weather_probability=1.,occupancy_probability=1.)
    d.update(kw);return AnnualScenario(**d)


def test_missing_frequency_retains_known_contribution_but_no_total():
    r=annual_risk((scenario(),scenario(id="pump/D",initiating_event_id="pump",frequency_per_year=None)))
    assert r["value"] is None and r["known_contribution"]==pytest.approx(.002)
    assert r["uncomputed_scenarios"]==["pump"]


def test_weather_partition_closes_and_is_weighted_once():
    r=annual_risk((scenario(annual_weather_probability=.4),scenario(id="leak/F",weather_class="F",annual_weather_probability=.6)))
    assert r["value"]==pytest.approx(.002)
    with pytest.raises(ValueError):annual_risk((scenario(annual_weather_probability=.4),))


def test_annual_branches_cannot_duplicate_weather_or_change_frequency():
    with pytest.raises(ValueError):annual_risk((scenario(annual_weather_probability=.5),scenario(id="other",annual_weather_probability=.5)))
    with pytest.raises(ValueError):annual_risk((scenario(annual_weather_probability=.5),scenario(id="F",weather_class="F",annual_weather_probability=.5,frequency_per_year=.02)))


def test_constant_flux_dose_and_equivalent_flux():
    r=thermal_dose((FluxStep(time_s=0.,heat_flux_w_m2=10000.),FluxStep(time_s=20.,heat_flux_w_m2=10000.)))
    assert r["dose"]==pytest.approx(20*10000**(4/3))
    assert r["equivalent_heat_flux_w_m2"]==pytest.approx(10000)


def test_linear_pulse_integral_is_invariant_under_sampling():
    a=(FluxStep(time_s=0.,heat_flux_w_m2=0.),FluxStep(time_s=20.,heat_flux_w_m2=10000.))
    b=(a[0],FluxStep(time_s=10.,heat_flux_w_m2=5000.),a[1])
    assert thermal_dose(a)["dose"]==pytest.approx(thermal_dose(b)["dose"])


def test_zero_flux_has_no_thermal_dose():
    assert thermal_dose((FluxStep(time_s=0.,heat_flux_w_m2=0.),FluxStep(time_s=20.,heat_flux_w_m2=0.)))["dose"]==0
