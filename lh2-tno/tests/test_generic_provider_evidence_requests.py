import json

from scripts.export_generic_provider_evidence_requests import export_requests


def _packet(*, event_id: str, termination_basis: str) -> dict:
    packet = {
        "provider_export_schema": "prism.resolved_release.v1",
        "event_id": event_id,
        "component_id": "component-1",
        "port_id": "port-1",
        "event_kind": "accidental_leak",
        "upstream_service": "LH2",
        "upstream_service_provenance": "reviewed provider boundary",
        "state_owner": "equipment_twin",
        "discharge_owner": "equipment_twin",
        "boundary_kind": "resolved_atmospheric_gas_exit",
        "enthalpy_convention": "static_exit_enthalpy",
        "property_basis": {
            "fluid": "Hydrogen",
            "backend": "CoolProp-HEOS",
            "energy_reference": "CoolProp-HEOS:Hydrogen:native",
        },
        "provider_boundary_reference": "provider-boundary-test",
        "input_origin": "reviewed_measurement",
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "termination_basis": termination_basis,
        "termination_provenance": "reviewed provider boundary",
        "duration_s": 0.2,
        "available_mass_kg": 1.0,
        "cumulative_mass_out_kg": 0.2,
        "cumulative_static_enthalpy_out_j": 200.0,
        "provider_source_digest": "0" * 64,
        "provider_result_digest": "1" * 64,
        "vertical_handoff": None,
        "failure_opening_diameter_m": 0.01,
        "steps": [{
            "time_s": 0.0,
            "mass_flow_kg_s": 1.0,
            "pressure_pa_abs": 101325.0,
            "specific_enthalpy_j_kg": 1000.0,
            "temperature_k": 288.15,
            "density_kg_m3": 1.0,
            "effective_area_m2": 1.0,
            "velocity_m_s": 1.0,
            "area_provenance": "provider",
            "velocity_origin": "provider_resolved",
        }],
        "provider_mass_balance": {
            "schema_version": "prism.provider_mass_balance.v1",
            "initial_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.2,
            "final_mass_kg": 0.8,
            "reported_residual_mass_kg": 0.0,
            "derived_accounting_residual_kg": 0.0,
            "isolation_time_s": 0.1,
            "isolation_success": True,
        },
    }
    return packet


def test_every_packet_gets_closure_or_qualification_request(tmp_path):
    root = tmp_path / "packets"
    open_path = root / "open" / "resolved_release.json"
    ready_path = root / "ready" / "resolved_release.json"
    open_packet = _packet(event_id="open-event", termination_basis="synthetic_diagnostic_horizon")
    ready_packet = _packet(event_id="ready-event", termination_basis="reviewed_isolation_success")
    open_path.parent.mkdir(parents=True)
    ready_path.parent.mkdir(parents=True)
    open_path.write_text(json.dumps(open_packet), encoding="utf-8")
    ready_path.write_text(json.dumps(ready_packet), encoding="utf-8")
    _write_verification(open_path.parent, open_packet, "synthetic_diagnostic_horizon")
    _write_verification(ready_path.parent, ready_packet, "reviewed_isolation_success")
    evidence = tmp_path / "packet_evidence.json"
    evidence.write_text(json.dumps({
        "schema_version": "prism.native_packet_evidence.v1",
        "rows": [
            {"event_id": "open-event", "component_id": "component-1", "evidence": {"resolved_packet_paths": ["open/resolved_release.json"]}},
            {"event_id": "ready-event", "component_id": "component-1", "evidence": {"resolved_packet_paths": ["ready/resolved_release.json"]}},
        ],
    }), encoding="utf-8")

    result = export_requests(evidence, packet_root=root)

    assert result["request_count"] == 2
    assert result["closure_open_request_count"] == 1
    assert result["qualification_open_request_count"] == 1
    assert {item["request_kind"] for item in result["requests"]} == {
        "release_closure_and_qualification",
        "qualification_only",
    }
    ready = next(item for item in result["requests"] if item["request_id"] == "ready-event")
    assert ready["status"] == "OPEN_QUALIFICATION"
    assert ready["qualification_sidecar_required"]["exact_digest_binding"] is True
    assert ready["acceptance"]["facility_qra_allowed"] is False


def _write_verification(directory, packet, basis):
    payload = {
        "provider_result_digest": packet["provider_result_digest"],
        "termination_basis": basis,
        "initial_mass_kg": packet["available_mass_kg"],
        "released_mass_kg": packet["cumulative_mass_out_kg"],
        "final_mass_kg": 0.0,
        "residual_tolerance_kg": 1e-8,
        "isolation_success": True,
    }
    (directory / "verification.json").write_text(json.dumps(payload), encoding="utf-8")
