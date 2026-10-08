import json
from pathlib import Path

import pytest

from lh2_tno.equipment_boundary import (
    ResolvedGasRelease,
    ResolvedGasStep,
    ResolvedLiquidRelease,
    ResolvedLiquidStep,
)
from lh2_tno.provider_release import (
    ProviderReleaseContractError,
    build_consequence_request_from_provider_release,
    load_provider_release,
    load_provider_release_catalog,
)


def _release() -> ResolvedGasRelease:
    return ResolvedGasRelease(
        component_id="storage-tank-01",
        port_id="tank-out",
        event_id="provider-accident-01",
        event_kind="accidental_leak",
        upstream_service="GH2",
        upstream_service_provenance="reviewed provider boundary",
        enthalpy_convention="static_exit_enthalpy",
        property_basis={
            "fluid": "Hydrogen",
            "energy_reference": "CoolProp-HEOS:Hydrogen:native",
        },
        provider_source_digest="0" * 64,
        provider_result_digest="1" * 64,
        provider_boundary_reference="provider-boundary-01",
        input_origin="model_prediction",
        position_enu_m=(0.0, 0.0, 1.0),
        direction_enu=(1.0, 0.0, 0.0),
        ambient_pressure_pa_abs=101325.0,
        ambient_temperature_k=288.15,
        duration_s=0.2,
        available_mass_kg=1.0,
        cumulative_mass_out_kg=0.2,
        cumulative_static_enthalpy_out_j=200.0,
        steps=(ResolvedGasStep(
            time_s=0.0,
            mass_flow_kg_s=1.0,
            pressure_pa_abs=101325.0,
            specific_enthalpy_j_kg=1000.0,
            temperature_k=288.15,
            density_kg_m3=1.0,
            effective_area_m2=1.0,
            velocity_m_s=1.0,
            area_provenance="provider",
            velocity_origin="provider_resolved",
        ),),
        termination_provenance="provider inventory boundary",
        failure_opening_diameter_m=0.01,
    )


def _liquid_release() -> ResolvedLiquidRelease:
    return ResolvedLiquidRelease(
        component_id="storage-tank-01",
        port_id="tank-liquid-out",
        event_id="provider-liquid-accident-01",
        event_kind="accidental_leak",
        upstream_service="LH2",
        upstream_service_provenance="synthetic liquid provider boundary",
        phase_basis="two_phase",
        enthalpy_convention="provider_total_outlet_enthalpy",
        property_basis={
            "fluid": "Hydrogen",
            "energy_reference": "CoolProp-HEOS:Hydrogen:native",
        },
        provider_source_digest="2" * 64,
        provider_result_digest="3" * 64,
        provider_boundary_reference="provider-liquid-boundary-01",
        input_origin="model_prediction",
        position_enu_m=(0.0, 0.0, 1.0),
        direction_enu=(1.0, 0.0, 0.0),
        ambient_pressure_pa_abs=101325.0,
        ambient_temperature_k=288.15,
        duration_s=0.2,
        available_mass_kg=1.0,
        cumulative_mass_out_kg=0.2,
        cumulative_specific_enthalpy_out_j=200.0,
        reference_area_m2=1.0,
        reference_area_provenance="synthetic provider",
        steps=(ResolvedLiquidStep(
            time_s=0.0,
            total_mass_flow_kg_s=1.0,
            gas_mass_flow_kg_s=1.0,
            ground_liquid_mass_flow_kg_s=0.0,
            airborne_liquid_mass_flow_kg_s=0.0,
            specific_enthalpy_j_kg=1000.0,
            gas_pressure_pa_abs=101325.0,
            gas_temperature_k=288.15,
            gas_density_kg_m3=1.0,
            gas_effective_area_m2=1.0,
            gas_velocity_m_s=1.0,
            gas_velocity_origin="provider_resolved",
        ),),
        termination_provenance="provider inventory boundary",
        droplet_partition_provenance="provider partition; no airborne liquid",
        failure_opening_diameter_m=0.01,
    )


def _defaults() -> dict:
    root = Path(__file__).parents[1]
    value = json.loads(
        (root / "examples" / "equipment_consequence_template.json").read_text(encoding="utf-8")
    )
    value.update(
        source_input=None,
        available_mass_kg=1.0,
        resolved_release=None,
        resolved_release_set=None,
        resolved_liquid_release=None,
        source_operator="integrated_transient",
        evaluation_times_s=[0.0, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0],
        release_termination={
            "basis": "synthetic_diagnostic_horizon",
            "time_s": 0.2,
            "provenance": "explicit test context",
        },
    )
    return value


def test_provider_packet_loads_only_explicit_accident_contract(tmp_path):
    release = _release()
    path = tmp_path / "release.json"
    path.write_text(json.dumps(release.model_dump(mode="json")), encoding="utf-8")

    loaded = load_provider_release(path)

    assert loaded == release
    assert loaded.provider_export_schema == "prism.resolved_release.v1"


def test_provider_packet_rejects_missing_schema_and_normal_vent():
    packet = _release().model_dump(mode="json")
    packet.pop("provider_export_schema")
    with pytest.raises(ProviderReleaseContractError, match="provider_export_schema"):
        load_provider_release(packet)

    normal = _release().model_dump(mode="json")
    normal["event_kind"] = "normal_vent"
    normal["failure_opening_diameter_m"] = None
    with pytest.raises(ProviderReleaseContractError, match="accidental_leak"):
        load_provider_release(normal)


def test_provider_release_catalog_and_request_adapter_preserve_context(tmp_path):
    packet = _release().model_dump(mode="json")
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"releases": [packet]}), encoding="utf-8")

    catalog = load_provider_release_catalog(path)
    request = build_consequence_request_from_provider_release(catalog[0], _defaults())

    assert len(catalog) == 1
    assert request.component_id == "storage-tank-01"
    assert request.resolved_release is not None
    assert request.resolved_release.event_id == "provider-accident-01"
    assert request.resolved_release.duration_s == 0.2
    assert request.source_input is None
    assert request.annual_frequency_per_year is None


def test_provider_liquid_packet_uses_liquid_operator_and_inventory_termination():
    packet = _liquid_release().model_dump(mode="json")
    release = load_provider_release(packet)
    defaults = _defaults()
    defaults["source_operator"] = "equipment_liquid_release"
    defaults["release_termination"] = {
        "basis": "inventory_depletion",
        "time_s": 0.2,
        "provenance": "provider positive inventory boundary",
    }

    request = build_consequence_request_from_provider_release(release, defaults)

    assert request.resolved_liquid_release is not None
    assert request.source_operator == "equipment_liquid_release"
    assert request.release_termination is not None
    assert request.release_termination.basis == "inventory_depletion"


def test_provider_request_adapter_rejects_integrated_source_defaults():
    defaults = _defaults()
    defaults["source_input"] = {"tank": {"fluid": "Hydrogen"}}
    with pytest.raises(ProviderReleaseContractError, match="source_input"):
        build_consequence_request_from_provider_release(_release(), defaults)


def test_provider_request_adapter_rejects_missing_termination_time():
    defaults = _defaults()
    defaults["release_termination"].pop("time_s")
    with pytest.raises(ProviderReleaseContractError, match="finite provider duration"):
        build_consequence_request_from_provider_release(_release(), defaults)
