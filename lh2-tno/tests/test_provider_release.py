import json
from pathlib import Path

import pytest

from lh2_tno.equipment_boundary import (
    ResolvedGasRelease,
    ResolvedGasReleaseSet,
    ResolvedGasStep,
    ResolvedLiquidRelease,
    ResolvedLiquidStep,
)
from lh2_tno.provider_release import (
    PROVIDER_RELEASE_SET_SCHEMA,
    ProviderReleaseContractError,
    build_consequence_request_from_provider_release,
    build_consequence_request_from_provider_release_set,
    load_provider_emergency_relief,
    load_provider_emergency_relief_catalog,
    load_provider_release,
    load_provider_release_branch_catalog,
    load_provider_release_catalog,
    load_provider_release_set,
    load_provider_release_set_catalog,
    load_provider_release_set_branch_catalog,
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


def _release_set() -> ResolvedGasReleaseSet:
    left = _release()
    right = left.model_copy(update={
        "port_id": "tank-return",
        "event_id": "provider-two-sided-01",
        "position_enu_m": (2.0, 0.0, 1.0),
        "direction_enu": (-1.0, 0.0, 0.0),
    })
    left = left.model_copy(update={"event_id": "provider-two-sided-01"})
    return ResolvedGasReleaseSet(
        event_id="provider-two-sided-01",
        component_id="storage-tank-01",
        releases=(left, right),
        available_mass_kg=1.0,
        cumulative_mass_out_kg=0.4,
        inventory_provenance="provider shared inventory ledger",
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


def test_provider_two_sided_set_has_dedicated_schema_and_adapter(tmp_path):
    release_set = _release_set()
    packet = {
        "provider_export_schema": PROVIDER_RELEASE_SET_SCHEMA,
        **release_set.model_dump(mode="json"),
    }
    path = tmp_path / "two_sided.json"
    path.write_text(json.dumps({"release_sets": [packet]}), encoding="utf-8")

    loaded = load_provider_release_set(packet)
    catalog = load_provider_release_set_catalog(path)
    defaults = _defaults()
    defaults.update(
        source_operator="equipment_two_sided_rupture",
        release_termination={
            "basis": "two_sided_rupture",
            "time_s": 0.2,
            "provenance": "provider shared rupture clock",
        },
    )
    request = build_consequence_request_from_provider_release_set(loaded, defaults)

    assert len(catalog) == 1
    assert request.source_operator == "equipment_two_sided_rupture"
    assert request.resolved_release_set is not None
    assert request.source_positions_enu_m == ((0.0, 0.0, 1.0), (2.0, 0.0, 1.0))
    assert request.release_termination.basis == "two_sided_rupture"
    assert request.annual_frequency_per_year is None


def test_provider_two_sided_adapter_rejects_single_exit_defaults():
    defaults = _defaults()
    defaults["source_operator"] = "integrated_transient"
    defaults["release_termination"]["basis"] = "synthetic_diagnostic_horizon"
    with pytest.raises(ProviderReleaseContractError, match="two-sided request requires"):
        build_consequence_request_from_provider_release_set(_release_set(), defaults)


def test_provider_two_sided_branch_catalog_keeps_set_boundary(tmp_path):
    release_set = _release_set()
    packet = {
        "provider_export_schema": PROVIDER_RELEASE_SET_SCHEMA,
        **release_set.model_dump(mode="json"),
    }
    path = tmp_path / "two_sided_branches.json"
    path.write_text(json.dumps({
        "branches": [
            {
                "id": "isolation-success",
                "probability_given_event": 0.7,
                "provenance": "synthetic two-sided isolation success",
                "release": packet,
            },
            {
                "id": "isolation-failure",
                "probability_given_event": 0.3,
                "provenance": "synthetic two-sided isolation failure",
                "release": packet,
            },
        ]
    }), encoding="utf-8")

    branches = load_provider_release_set_branch_catalog(path)

    assert [branch.id for branch in branches] == [
        "isolation-success", "isolation-failure"
    ]
    assert all(isinstance(branch.release, ResolvedGasReleaseSet) for branch in branches)
    assert sum(branch.probability_given_event for branch in branches) == pytest.approx(1.0)


def test_provider_release_branch_catalog_preserves_conditional_partition(tmp_path):
    packet = _release().model_dump(mode="json")
    path = tmp_path / "branch_catalog.json"
    path.write_text(json.dumps({
        "branches": [
            {
                "id": "isolation-success",
                "probability_given_event": 0.7,
                "provenance": "synthetic provider success",
                "release": packet,
            },
            {
                "id": "isolation-failure",
                "probability_given_event": 0.3,
                "provenance": "synthetic provider failure",
                "release": packet,
            },
        ]
    }), encoding="utf-8")

    branches = load_provider_release_branch_catalog(path)

    assert [branch.id for branch in branches] == [
        "isolation-success", "isolation-failure"
    ]
    assert sum(branch.probability_given_event for branch in branches) == pytest.approx(1.0)
    assert all(branch.release.event_id == "provider-accident-01" for branch in branches)


def test_provider_release_branch_catalog_rejects_duplicate_branch_ids(tmp_path):
    packet = _release().model_dump(mode="json")
    row = {
        "id": "duplicate",
        "probability_given_event": 0.5,
        "provenance": "synthetic duplicate",
        "release": packet,
    }
    path = tmp_path / "duplicate_branch_catalog.json"
    path.write_text(json.dumps([row, row]), encoding="utf-8")

    with pytest.raises(ProviderReleaseContractError, match="branch ids must be unique"):
        load_provider_release_branch_catalog(path)


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


def test_provider_emergency_relief_packet_uses_dedicated_operator_and_basis():
    packet = _release().model_dump(mode="json")
    packet.update(event_kind="emergency_relief", failure_opening_diameter_m=None)
    release = load_provider_emergency_relief(packet)
    defaults = _defaults()
    defaults["source_operator"] = "equipment_emergency_relief"
    defaults["release_termination"] = {
        "basis": "emergency_relief_discharge",
        "time_s": 0.2,
        "provenance": "provider maximum relief discharge horizon",
    }

    request = build_consequence_request_from_provider_release(release, defaults)

    assert request.source_operator == "equipment_emergency_relief"
    assert request.resolved_release is not None
    assert request.resolved_release.event_kind == "emergency_relief"
    assert request.release_termination is not None
    assert request.release_termination.basis == "emergency_relief_discharge"


def test_provider_emergency_relief_catalog_is_separate_from_accidental_catalog(tmp_path):
    packet = _release().model_dump(mode="json")
    packet.update(event_kind="emergency_relief", failure_opening_diameter_m=None)
    path = tmp_path / "relief.json"
    path.write_text(json.dumps({"releases": [packet]}), encoding="utf-8")

    rows = load_provider_emergency_relief_catalog(path)

    assert len(rows) == 1
    assert rows[0].event_kind == "emergency_relief"
    with pytest.raises(ProviderReleaseContractError, match="accidental_leak"):
        load_provider_release_catalog(path)


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
