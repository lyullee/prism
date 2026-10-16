from lh2_tno.release_boundary_evidence_intake import (
    RESPONSE_SCHEMA,
    build_release_boundary_evidence_response_template,
    validate_release_boundary_evidence_response,
)


def _request(basis: str, request_id: str = "facility/event/G1"):
    return {
        "request_id": request_id,
        "termination_basis_observed": basis,
        "identity": {
            "event_id": request_id,
            "case_key": request_id + "|branch|weather",
            "asset_id": "asset-01",
            "component_id": "component-01",
            "port_ids": ["accident-out"],
            "operating_mode": "supply",
            "hazop_scenario_id": "hazop-01",
        },
        "current_boundary": {
            "provider_result_digest": "a" * 64,
        },
    }


def _common(request):
    return {
        "schema_version": RESPONSE_SCHEMA,
        "request_id": request["request_id"],
        "supersedes_provider_result_digest": "a" * 64,
        "identity": request["identity"],
        "provider_source_digest": "b" * 64,
        "provider_result_digest": "c" * 64,
        "termination_time_s": 10.0,
        "termination_history_sample_count": 3,
        "termination_provenance": "provider stopping event",
        "stopping_event": {"time_s": 10.0, "kind": "physical_stop"},
        "initial_inventory_kg": 1.0,
        "cumulative_mass_out_kg": 0.75,
        "final_inventory_kg": 0.25,
        "mass_residual_kg": 0.0,
    }


def test_relief_response_requires_family_specific_fields():
    request = _request("emergency_relief_discharge")
    response = _common(request)
    response.update({
        "termination_basis": "emergency_relief_discharge",
        "event_kind": "emergency_relief",
        "source_operator": "equipment_emergency_relief",
        "failure_opening_diameter_m": None,
        "relief_setpoint_pa": 120000.0,
        "relief_capacity_kg_s": 0.5,
        "discharge_complete": True,
    })
    report = validate_release_boundary_evidence_response({"requests": [request]}, {"responses": [response]})
    assert report["status"] == "RELEASE_BOUNDARY_REAUDIT_READY"
    assert report["ready_count"] == 1


def test_horizon_response_cannot_reuse_inventory_over_600s():
    request = _request("inventory_over_600s")
    response = _common(request)
    response["termination_basis"] = "inventory_over_600s"
    report = validate_release_boundary_evidence_response({"requests": [request]}, {"responses": [response]})
    assert report["status"] == "RESPONSE_EVIDENCE_OPEN"
    assert "response_replaces_horizon_basis" in report["rows"][0]["blocking_reasons"]


def test_horizon_response_can_close_with_reviewed_isolation():
    request = _request("inventory_over_600s")
    response = _common(request)
    response.update({
        "termination_basis": "reviewed_isolation_success",
        "isolation_success": True,
        "isolation_time_s": 4.0,
        "post_isolation_observation_s": 5.0,
        "post_isolation_zero_flow": True,
    })
    report = validate_release_boundary_evidence_response({"requests": [request]}, {"responses": [response]})
    assert report["status"] == "RELEASE_BOUNDARY_REAUDIT_READY"


def test_missing_response_is_fail_closed():
    request = _request("inventory_over_600s")
    report = validate_release_boundary_evidence_response({"requests": [request]}, {"responses": []})
    assert report["status"] == "RESPONSE_EVIDENCE_OPEN"
    assert report["rows"][0]["status"] == "MISSING"


def test_template_contains_no_fake_provider_values():
    request = _request("emergency_relief_discharge")
    template = build_release_boundary_evidence_response_template({"requests": [request]})
    row = template["responses"][0]
    assert row["provider_result_digest"] is None
    assert row["relief_setpoint_pa"] is None
    assert template["policy"]["placeholder_values_are_not_evidence"] is True
