from lh2_tno.release_boundary_evidence_intake import (
    RESPONSE_SCHEMA,
    build_release_boundary_evidence_response_template,
    build_release_boundary_evidence_handoff,
    build_provider_termination_evidence_catalog,
    validate_release_boundary_evidence_response,
)
from lh2_tno.release_boundary_case_audit import build_release_boundary_case_audit


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


def test_horizon_response_pressure_equalization_remains_diagnostic_only():
    request = _request("inventory_over_600s")
    response = _common(request)
    response["termination_basis"] = "model_pressure_equalization"
    report = validate_release_boundary_evidence_response({"requests": [request]}, {"responses": [response]})
    assert report["status"] == "RESPONSE_EVIDENCE_OPEN"
    assert "response_replaces_horizon_basis" in report["rows"][0]["blocking_reasons"]


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


def test_valid_response_is_translated_to_case_audit_catalog_without_promotion():
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
    requests = {"requests": [request]}
    responses = {"responses": [response]}
    intake = validate_release_boundary_evidence_response(requests, responses)
    catalog = build_provider_termination_evidence_catalog(
        requests, responses, validation_report=intake
    )
    assert catalog["status"] == "PROVIDER_TERMINATION_EVIDENCE_READY"
    assert catalog["ready_count"] == 1
    row = catalog["rows"][0]
    assert row["event_id"] == request["identity"]["event_id"]
    assert row["case_key"] == request["identity"]["case_key"]
    assert row["provider_result_digest"] == "c" * 64
    assert row["duration_s"] == 10.0
    assert row["available_mass_kg"] == 1.0
    assert row["cumulative_mass_out_kg"] == 0.75
    assert catalog["provider_qualification_claim"] is False
    assert catalog["facility_qra_promotion_allowed"] is False


def test_invalid_response_is_not_emitted_to_case_audit_catalog():
    request = _request("inventory_over_600s")
    response = _common(request)
    response["termination_basis"] = "inventory_over_600s"
    requests = {"requests": [request]}
    responses = {"responses": [response]}
    catalog = build_provider_termination_evidence_catalog(requests, responses)
    assert catalog["status"] == "PROVIDER_TERMINATION_EVIDENCE_PARTIAL"
    assert catalog["ready_count"] == 0
    assert catalog["skipped_count"] == 1
    assert catalog["rows"] == []


def test_catalog_can_be_consumed_by_case_audit_at_the_same_packet_grain():
    request = _request("emergency_relief_discharge")
    request["identity"]["case_key"] = "facility/event/G1|branch|weather"
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
    requests = {"requests": [request]}
    responses = {"responses": [response]}
    catalog = build_provider_termination_evidence_catalog(requests, responses)
    case = {
        "event_id": "facility/event/G1",
        "release_branch_id": "branch",
        "annual_condition_id": "weather",
        "asset_id": "asset-01",
        "frequency_port_ids": ["accident-out"],
        "provider_packet_identity": {
            "component_id": "component-01",
            "provider_result_digests": ["c" * 64],
            "input_origins": ["provider_actual"],
        },
        "status": "EXECUTED",
        "domain_assessment": {"domain_truncated": False},
    }
    ledger_row = {
        "event_id": "facility/event/G1",
        "release_branch_id": "branch",
        "annual_condition_id": "weather",
        "asset_id": "asset-01",
        "status": "EXECUTED",
        "ledger_status": "COMPLETE",
        "termination": {
            "basis": "emergency_relief_discharge",
            "time_s": 10.0,
            "provenance": "provider",
        },
        "provider": {
            "provider_mass_balance_statuses": ["CLOSED"],
            "duration_s": [10.0],
            "available_mass_kg": [1.0],
            "cumulative_mass_out_kg": [0.75],
            "residual_mass_kg": [0.25],
        },
        "mass_ledger": {"end_to_end_residual_kg": 0.0},
    }
    audit = build_release_boundary_case_audit(
        {"facility_risk_ledger": {
            "cases": [case],
            "release_termination_inventory_ledger": {"rows": [ledger_row]},
            "events": [],
        }},
        provider_termination_evidence=catalog,
    )
    assert audit["rows"][0]["provider_termination_evidence_status"] == "VALID"
    assert audit["rows"][0]["strict_release_boundary_eligible"] is True


def test_single_handoff_api_preserves_intake_catalog_and_case_audit():
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
    case = {
        "event_id": "facility/event/G1",
        "release_branch_id": "branch",
        "annual_condition_id": "weather",
        "asset_id": "asset-01",
        "frequency_port_ids": ["accident-out"],
        "provider_packet_identity": {
            "component_id": "component-01",
            "provider_result_digests": ["c" * 64],
            "input_origins": ["provider_actual"],
        },
        "status": "EXECUTED",
        "domain_assessment": {"domain_truncated": False},
    }
    ledger_row = {
        "event_id": "facility/event/G1",
        "release_branch_id": "branch",
        "annual_condition_id": "weather",
        "asset_id": "asset-01",
        "status": "EXECUTED",
        "ledger_status": "COMPLETE",
        "termination": {
            "basis": "emergency_relief_discharge",
            "time_s": 10.0,
            "provenance": "provider",
        },
        "provider": {
            "provider_mass_balance_statuses": ["CLOSED"],
            "duration_s": [10.0],
            "available_mass_kg": [1.0],
            "cumulative_mass_out_kg": [0.75],
            "residual_mass_kg": [0.25],
        },
        "mass_ledger": {"end_to_end_residual_kg": 0.0},
    }
    handoff = build_release_boundary_evidence_handoff(
        {"requests": [request]},
        {"responses": [response]},
        facility_assessment={
            "facility_risk_ledger": {
                "cases": [case],
                "release_termination_inventory_ledger": {"rows": [ledger_row]},
                "events": [],
            }
        },
        facility_evidence_request={
            "case_requests": [{
                "event_id": "facility/event/G1",
                "release_branch_id": "branch",
                "annual_condition_id": "weather",
            }]
        },
    )
    assert handoff["intake"]["status"] == "RELEASE_BOUNDARY_REAUDIT_READY"
    assert handoff["provider_termination_evidence"]["ready_count"] == 1
    assert handoff["case_audit"]["rows"][0]["provider_termination_evidence_status"] == "VALID"
    assert handoff["case_audit"]["rows"][0]["strict_release_boundary_eligible"] is True
    assert handoff["facility_qra_promotion_allowed"] is False
