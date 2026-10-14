from lh2_tno.completion_audit import build_ijhe_completion_audit


def _status() -> dict:
    return {
        "physical_validation_claim": False,
        "provider_release_contract_actual_facility_packet_available": False,
        "external_provider_evidence_release_inventory_status": "NO_ACCIDENT_RELEASE_EXPORT",
    }


def test_completion_audit_checks_case_keyed_conditional_release_trace() -> None:
    trace = {
        "schema_version": "prism.conditional_facility_release_trace.v1",
        "source_status": "CASE_BOUNDARY_PARTIAL",
        "case_key_definition": "event_id|release_branch_id|annual_condition_id",
        "summary": {
            "case_count": 1,
            "risk_atom_count": 1,
            "facility_ir_fn_promotion": False,
        },
        "rows": [
            {
                "case_key": "event-1||weather-1",
                "numerical_release_closed": True,
                "risk_atom_accounting": {"risk_atom_count": 1},
                "facility_qra_promotion_eligible": False,
            }
        ],
        "semantics": {"promotion": "diagnostic only"},
    }
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        facility_assessment={
            "conditional_diagnostic_facility_coverage": {
                "case_count": 1,
                "risk_atom_count": 1,
            }
        },
        conditional_facility_release_trace=trace,
    )
    check = next(
        row
        for row in report["checks"]
        if row["name"] == "diagnostic_conditional_facility_release_trace"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_rejects_release_trace_promotion_claim() -> None:
    trace = {
        "schema_version": "prism.conditional_facility_release_trace.v1",
        "source_status": "CASE_BOUNDARY_PARTIAL",
        "case_key_definition": "event_id|release_branch_id|annual_condition_id",
        "summary": {"case_count": 1, "risk_atom_count": 1, "facility_ir_fn_promotion": True},
        "rows": [
            {
                "case_key": "event-1||weather-1",
                "numerical_release_closed": True,
                "risk_atom_accounting": {"risk_atom_count": 1},
                "facility_qra_promotion_eligible": False,
            }
        ],
        "semantics": {},
    }
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        conditional_facility_release_trace=trace,
    )
    check = next(
        row
        for row in report["checks"]
        if row["name"] == "diagnostic_conditional_facility_release_trace"
    )
    assert check["status"] == "BLOCKED"
    assert "unsafe promotion" in check["blocking_reason"]
