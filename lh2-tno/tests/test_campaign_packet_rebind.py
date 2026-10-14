import json
from pathlib import Path

import pytest

from lh2_tno.campaign_packet_rebind import (
    _load_selected_state_snapshot,
    _request_from_selected_packet,
    packet_rebind_provenance,
    rebind_request_to_compressible_handoff,
)
from lh2_tno.equipment_boundary import (
    CompressibleGasPlaneHandoff,
    ResolvedGasRelease,
    ResolvedGasStep,
    VerticalGasHandoffState,
)


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


def test_rebind_binds_equipment_inventory_source_operator_from_provider_basis():
    release = _release().model_copy(update={"termination_basis": "inventory_depletion"})

    rebound = _request_from_selected_packet(_request(), release)

    assert rebound["source_operator"] == "equipment_inventory_depletion"
    assert rebound["release_termination"]["basis"] == "inventory_depletion"


def test_selected_packet_state_snapshot_is_loaded_from_verification_sidecar(tmp_path):
    packet_path = tmp_path / "resolved_release.json"
    packet_path.write_text("{}\n", encoding="utf-8")
    snapshot = {
        "schema_version": "prism.equipment_state_snapshot.v1",
        "component_id": "storage-tank-01",
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": 600000.0,
        "temperature_k": 20.9,
        "mass_kg": 1.0,
        "phase": "liquid",
        "position_enu_m": [0.0, 0.0, 1.0],
        "measurements": {},
        "source_digest": None,
        "quality": "valid",
    }
    from lh2_tno.state_snapshot import EquipmentStateSnapshot

    digest = EquipmentStateSnapshot.from_mapping(snapshot).digest()
    (tmp_path / "verification.json").write_text(
        json.dumps({
            "state_snapshot": snapshot,
            "state_snapshot_handoff": {
                "digest": digest,
                "provider_echo_digest": digest,
            },
        }),
        encoding="utf-8",
    )

    payload, actual_digest = _load_selected_state_snapshot(
        packet_path,
        event_id="event-01",
        component_id="storage-tank-01",
    )

    assert payload["component_id"] == "storage-tank-01"
    assert actual_digest == digest


def test_rebind_provenance_is_separate_from_strict_campaign_schema():
    provenance = packet_rebind_provenance(
        {"status": "PARTIAL_DIAGNOSTIC_EVIDENCE", "frequency_bound": False},
        ["event-01"],
    )

    assert provenance["schema_version"] == "prism.campaign_packet_rebind.v1"
    assert provenance["event_count"] == 1
    assert provenance["frequency_bound"] is False


def test_compressible_handoff_rebind_requires_same_source_and_preserves_diagnostic_policy():
    release = _release()
    handoff = CompressibleGasPlaneHandoff(
        position_enu_m=(0.0, 0.0, 1.0),
        direction_enu=(1.0, 0.0, 0.0),
        velocity_m_s=1.0,
        density_kg_m3=1.0,
        temperature_k=288.15,
        h2_mass_fraction=1.0,
        half_width_m=0.5,
        depth_m=1.0,
        provenance="test compressible handoff; not independently validated",
        states=(VerticalGasHandoffState(
            time_s=0.0,
            direction_enu=(1.0, 0.0, 0.0),
            velocity_m_s=1.0,
            density_kg_m3=1.0,
            temperature_k=288.15,
            h2_mass_fraction=1.0,
            half_width_m=0.5,
            depth_m=1.0,
            provenance="test compressible handoff; not independently validated",
        ),),
    )
    handoff_payload = release.model_dump(mode="json")
    handoff_payload["compressible_plane_handoff"] = handoff.model_dump(mode="json")
    handoff_payload["provider_result_digest"] = "2" * 64
    request = _request()
    request["resolved_release"] = release.model_dump(mode="json")

    rebound, provenance = rebind_request_to_compressible_handoff(
        request,
        handoff_payload,
        event_id=release.event_id,
    )

    assert rebound["resolved_release"]["provider_result_digest"] == "2" * 64
    assert rebound["resolved_release"]["compressible_plane_handoff"] is not None
    assert provenance["identity_checks"]["source_digest_match"] is True
    assert provenance["compressible_plane_handoff_consumed"] is True
    assert provenance["physical_validation_claim"] is False
    assert provenance["frequency_inference"] is False


def test_compressible_handoff_rebind_rejects_different_source_digest():
    release = _release()
    payload = release.model_dump(mode="json")
    payload["provider_source_digest"] = "3" * 64
    request = _request()
    request["resolved_release"] = release.model_dump(mode="json")

    with pytest.raises(ValueError, match="source_digest_match"):
        rebind_request_to_compressible_handoff(request, payload, event_id=release.event_id)
