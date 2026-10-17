from lh2_tno.completion_audit import build_ijhe_completion_audit


def _base_inputs():
    return (
        {
            "provider_release_contract_actual_facility_packet_available": False,
            "external_provider_evidence_release_inventory_status": "NO_QUALIFIED_PACKET",
        },
        {"matrix_complete": False, "blocking_reasons": ["scope incomplete"]},
        {
            "events": [],
            "cases": [],
            "timing": {"fresh_physics_cases": 0, "campaign_elapsed_ms": 0.0},
        },
    )


def _audit(status="PASS", **overrides):
    value = {
        "schema_version": "prism.dynamic_state_closure_ledger_audit.v1",
        "status": status,
        "campaign_count": 1,
        "facility_supplied": True,
        "check_count": 3,
        "blocking_reason_count": 0 if status == "PASS" else 1,
        "blocking_reasons": [] if status == "PASS" else ["count mismatch"],
        "diagnostic_only": True,
        "frequency_reallocation_performed": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    value.update(overrides)
    return value


def test_completion_audit_consumes_dynamic_state_closure_consistency():
    current_status, matrix, campaign = _base_inputs()
    report = build_ijhe_completion_audit(
        current_status,
        matrix,
        campaign,
        dynamic_state_closure_ledger_audit=_audit(),
    )
    check = next(
        item
        for item in report["checks"]
        if item["name"] == "diagnostic_dynamic_state_closure_ledger_consistency"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_blocks_dynamic_state_closure_mismatch():
    current_status, matrix, campaign = _base_inputs()
    report = build_ijhe_completion_audit(
        current_status,
        matrix,
        campaign,
        dynamic_state_closure_ledger_audit=_audit("BLOCKED"),
    )
    check = next(
        item
        for item in report["checks"]
        if item["name"] == "diagnostic_dynamic_state_closure_ledger_consistency"
    )
    assert check["status"] == "BLOCKED"
    assert report["status"] == "INCOMPLETE_EVIDENCE"
