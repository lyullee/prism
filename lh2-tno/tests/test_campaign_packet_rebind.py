import json
from pathlib import Path

from lh2_tno.campaign_packet_rebind import (
    _request_from_selected_packet,
    packet_rebind_provenance,
)
from lh2_tno.equipment_boundary import ResolvedGasRelease, ResolvedGasStep


def _release() -> ResolvedGasRelease:
    return ResolvedGasRelease(
        component_id="storage-tank-01",
        port_id="tank-out",
        event_id="rebind-event-01",
        event_kind="accidental_leak",
        upstream_service="GH2",
        upstream_service_provenance="test provider boundary",
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
        termination_basis="reviewed_isolation_success",
        termination_provenance="provider inventory boundary",
        failure_opening_diameter_m=0.01,
    )


def _request() -> dict:
    root = Path(__file__).parents[1]
    value = json.loads(
        (root / "examples" / "equipment_consequence_template.json").read_text(encoding="utf-8")
    )
    value.update(
        component_id="storage-tank-01",
        source_input=None,
        source_position_enu_m=[0.0, 0.0, 1.0],
        available_mass_kg=1.0,
        resolved_release=None,
        resolved_release_set=None,
        resolved_liquid_release=None,
        source_operator="integrated_transient",
        evaluation_times_s=[0.0, 0.2, 1.0, 2.0, 3.0, 5.0],
        release_termination={
            "basis": "synthetic_diagnostic_horizon",
            "time_s": 0.2,
            "provenance": "test context",
        },
    )
    return value


def test_rebind_preserves_campaign_facility_placement_and_provider_clock():
    rebound = _request_from_selected_packet(_request(), _release())

    assert rebound["source_position_enu_m"] == [0.0, 0.0, 1.0]
    assert rebound["resolved_release"]["duration_s"] == 0.2
    assert rebound["release_termination"]["basis"] == "reviewed_isolation_success"
    assert rebound["evaluation_times_s"] == [0.0, 0.2, 1.0, 2.0, 3.0, 5.0]


def test_rebind_provenance_is_separate_from_strict_campaign_schema():
    provenance = packet_rebind_provenance(
        {"status": "PARTIAL_DIAGNOSTIC_EVIDENCE", "frequency_bound": False},
        ["event-01"],
    )

    assert provenance["schema_version"] == "prism.campaign_packet_rebind.v1"
    assert provenance["event_count"] == 1
    assert provenance["frequency_bound"] is False
