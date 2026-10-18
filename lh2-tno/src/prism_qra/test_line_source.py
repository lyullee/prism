"""Finite GH2 supply-line source: unit, input and pipeline boundaries."""

import pytest

import pipeline
import siteio
from source_term import discharge, haaland_friction_factor, line_discharge
from taxonomy import DischargeCoefficientBasis, enumerate_scenarios


@pytest.fixture(scope="module")
def proust_900bar_sources():
    pressure_pa = 900.0e5 + 101325.0
    temperature_k = 46.0 + 273.15
    direct = discharge(pressure_pa, temperature_k, "Hydrogen", 0.003)
    smooth = line_discharge(
        pressure_pa, temperature_k, "Hydrogen", 0.003,
        line_length_m=10.0, line_diameter_m=0.010)
    rough = line_discharge(
        pressure_pa, temperature_k, "Hydrogen", 0.003,
        line_length_m=10.0, line_diameter_m=0.010,
        roughness_m=45e-6, minor_loss_k=20.0)
    return direct, smooth, rough


def test_haaland_smooth_pipe_reference_value():
    assert haaland_friction_factor(1.0e5) == pytest.approx(0.017825, rel=1e-3)


def test_proust_line_loss_is_small_and_auditable(proust_900bar_sources):
    direct, smooth, _ = proust_900bar_sources
    assert smooth.rate_kg_s / direct.rate_kg_s == pytest.approx(0.980, abs=0.003)
    assert smooth.line_pressure_drop_pa / 1e6 == pytest.approx(2.0, abs=0.3)
    assert smooth.line_outlet_mach < 0.1
    assert smooth.line_reynolds > 1.0e6
    assert smooth.flow_model == "isothermal-real-gas-line+terminal-orifice"


def test_roughness_and_fittings_do_not_increase_flow(proust_900bar_sources):
    _, smooth, rough = proust_900bar_sources
    assert rough.rate_kg_s < smooth.rate_kg_s
    assert rough.line_pressure_drop_pa > smooth.line_pressure_drop_pa


def test_line_loss_does_not_explain_proust_900bar_measurement(
        proust_900bar_sources):
    _, smooth, _ = proust_900bar_sources
    measured_kg_s = 0.165
    assert smooth.rate_kg_s / measured_kg_s > 1.9


def test_site_csv_propagates_line_to_scenario_and_pipeline():
    sections = (
        "section_id,service,inventory_kg,isolation_time_s\n"
        "HP,GH2,120,15\n")
    components = (
        "tag,primitive,service,count,diameter_mm,pressure_barg,"
        "temperature_k,orientation,x_m,y_m,z_m,section_id,"
        "upstream_line_length_m,upstream_line_diameter_mm,"
        "upstream_line_roughness_mm,upstream_minor_loss_k\n"
        "V-1,VALVE,GH2,1,3,900,319.15,HORIZONTAL,0,0,0,HP,"
        "10,10,0.0015,0\n")
    site = siteio.load_site("line", sections, components)
    scenario = [s for s in enumerate_scenarios(site)
                if s.bin_label == "100%"][0]
    assert scenario.upstream_line.length_m == 10.0
    assert scenario.upstream_line.diameter_m == pytest.approx(0.010)
    result, _ = pipeline._source(scenario, isolation_s=15.0)
    assert result.flow_model.startswith("isothermal-real-gas-line")
    assert result.rate_kg_s < 0.34


def test_partial_line_input_reports_the_row_and_missing_field():
    sections = (
        "section_id,service,inventory_kg,isolation_time_s\n"
        "HP,GH2,120,15\n")
    components = (
        "tag,primitive,service,count,diameter_mm,pressure_barg,"
        "temperature_k,orientation,x_m,y_m,z_m,section_id,"
        "upstream_line_length_m\n"
        "V-1,VALVE,GH2,1,3,900,319.15,HORIZONTAL,0,0,0,HP,10\n")
    with pytest.raises(siteio.SheetErrors) as caught:
        siteio.load_site("line", sections, components)
    message = str(caught.value)
    assert "components row 2" in message
    assert "upstream_line_diameter_mm" in message


def test_line_rejects_terminal_hole_larger_than_pipe():
    with pytest.raises(ValueError, match="cannot exceed"):
        line_discharge(10e6, 300.0, "Hydrogen", 0.012,
                       line_length_m=10.0, line_diameter_m=0.010)


def test_site_csv_propagates_declared_cd_and_pipeline_uses_it():
    sections = (
        "section_id,service,inventory_kg,isolation_time_s\n"
        "HP,GH2,120,15\n")
    components = (
        "tag,primitive,service,count,diameter_mm,pressure_barg,"
        "temperature_k,orientation,x_m,y_m,z_m,section_id,"
        "discharge_coefficient,discharge_coefficient_basis,"
        "discharge_coefficient_note\n"
        "V-1,VALVE,GH2,1,3,900,319.15,HORIZONTAL,0,0,0,HP,"
        "0.61,ENGINEERING_ASSUMPTION,declared sensitivity boundary\n")
    site = siteio.load_site("cd", sections, components)
    scenario = [s for s in enumerate_scenarios(site)
                if s.bin_label == "100%"][0]
    assert scenario.discharge_coefficient == pytest.approx(0.61)
    assert scenario.discharge_coefficient_basis is \
        DischargeCoefficientBasis.ENGINEERING_ASSUMPTION
    result, _ = pipeline._source(scenario, isolation_s=15.0)
    unit = discharge(
        scenario.pressure_pa, scenario.temperature_k, "Hydrogen",
        scenario.hole_diameter_m)
    assert result.rate_kg_s == pytest.approx(0.61 * unit.rate_kg_s)
    assert any("measured equipment" in claim
               for p in scenario.provenance
               for claim in p.not_claimable_as)


def test_cd_below_one_without_basis_is_rejected_at_its_row():
    sections = (
        "section_id,service,inventory_kg,isolation_time_s\n"
        "HP,GH2,120,15\n")
    components = (
        "tag,primitive,service,count,diameter_mm,pressure_barg,"
        "temperature_k,orientation,x_m,y_m,z_m,section_id,"
        "discharge_coefficient\n"
        "V-1,VALVE,GH2,1,3,900,319.15,HORIZONTAL,0,0,0,HP,0.61\n")
    with pytest.raises(siteio.SheetErrors) as caught:
        siteio.load_site("cd", sections, components)
    message = str(caught.value)
    assert "components row 2" in message
    assert "discharge_coefficient_basis" in message


def test_calibrated_cd_cannot_be_claimed_as_independent_validation():
    sections = (
        "section_id,service,inventory_kg,isolation_time_s\n"
        "HP,GH2,120,15\n")
    components = (
        "tag,primitive,service,count,diameter_mm,pressure_barg,"
        "temperature_k,orientation,x_m,y_m,z_m,section_id,"
        "discharge_coefficient,discharge_coefficient_basis,"
        "discharge_coefficient_note\n"
        "V-1,VALVE,GH2,1,3,900,319.15,HORIZONTAL,0,0,0,HP,"
        "0.53,CALIBRATED,Proust Figure 5 same-series fit\n")
    scenario = [s for s in enumerate_scenarios(
        siteio.load_site("cd", sections, components))
        if s.bin_label == "100%"][0]
    assert any("independent validation" in claim
               for p in scenario.provenance
               for claim in p.not_claimable_as)


@pytest.mark.parametrize("coefficient", [0.0, -0.1, 1.01])
def test_source_rejects_unphysical_discharge_coefficients(coefficient):
    with pytest.raises(ValueError, match="coefficient"):
        discharge(10e6, 300.0, "Hydrogen", 0.003, Cd=coefficient)
