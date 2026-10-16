from lh2_tno.release_boundary_requests import build_release_boundary_evidence_requests


def _row(event_id, basis, *, evidence="INVALID", status="NUMERICALLY_OPEN"):
    return {
        "event_id": event_id,
        "case_key": f"{event_id}|branch|condition",
        "asset_id": event_id.split("/")[-2],
        "model_component_id": "component-01",
        "frequency_port_ids": ["accident-out"],
        "operating_mode": "supply",
        "hazop_scenario_id": "hazop-01",
        "provider_termination_evidence_basis": basis,
        "provider_termination_evidence_status": evidence,
        "numerical_closure_status": status,
        "provider_termination_evidence_blocking_reasons": ["boundary_open"],
        "release_duration_s": [600.0],
        "available_mass_kg": [1.0],
        "cumulative_mass_out_kg": [0.1],
        "residual_mass_kg": [0.9],
    }


def test_relief_request_requires_relief_identity_and_device_fields():
    report = build_release_boundary_evidence_requests({
        "schema_version": "prism.release_boundary_case_audit.v1",
        "status": "CASE_BOUNDARY_PARTIAL",
        "case_count": 1,
        "rows": [_row("facility/pressure-relief/G1", "emergency_relief_discharge")],
    })
    request = report["requests"][0]
    required = request["required_provider_evidence"]
    assert "source_operator=equipment_emergency_relief" in required
    assert "positive provider relief_setpoint_pa" in required
    assert request["qualification_requirements"]
    assert report["policy"]["frequency_inference_allowed"] is False


def test_inventory_horizon_request_does_not_substitute_a_new_basis():
    report = build_release_boundary_evidence_requests({
        "schema_version": "prism.release_boundary_case_audit.v1",
        "status": "CASE_BOUNDARY_PARTIAL",
        "case_count": 1,
        "rows": [_row("facility/ambient-vaporizer/G2", "inventory_over_600s")],
    })
    required = report["requests"][0]["required_provider_evidence"]
    assert any("continues beyond 600 s" in item for item in required)
    assert any("different supported termination basis" in item for item in required)
    assert report["policy"]["termination_basis_substitution_allowed"] is False


def test_closed_rows_are_not_exported():
    row = _row("facility/closed/G1", "inventory_depletion", evidence="VALID", status="NUMERICALLY_CLOSED")
    report = build_release_boundary_evidence_requests({"rows": [row], "case_count": 1})
    assert report["status"] == "NO_OPEN_RELEASE_BOUNDARY_EVIDENCE_REQUESTS"
    assert report["requests"] == []
