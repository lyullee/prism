from lh2_tno.completion_audit import build_ijhe_completion_audit


def _status():
    return {
        "physical_validation_claim": False,
        "provider_release_contract_actual_facility_packet_available": False,
        "external_provider_evidence_release_inventory_status": "NO_ACCIDENT_RELEASE_EXPORT",
        "equipment_provider_release_worklist_status": "READY_FOR_PROVIDER_PACKETS",
        "equipment_provider_release_worklist_event_count": 1,
        "equipment_provider_release_worklist_provider_packet_count": 1,
        "equipment_provider_release_worklist_uncomputed_count": 0,
    }


def _audit(**overrides):
    value = {
        "schema_version": "prism.release_boundary_case_audit.v1",
        "status": "CASE_BOUNDARY_PARTIAL",
        "case_count": 2,
        "source_case_count": 2,
        "source_release_ledger_row_count": 2,
        "source_alignment_status": "ALIGNED",
        "strict_release_boundary_eligible_case_count": 1,
        "strict_release_boundary_blocked_case_count": 1,
        "provider_qualification_claim": False,
        "independent_physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_ir_fn_promotion": False,
        "rows": [
            {
                "strict_release_boundary_eligible": True,
                "facility_qra_promotion_eligible": False,
                "facility_qra_blocking_reasons": ["model_prediction"],
            },
            {
                "strict_release_boundary_eligible": False,
                "facility_qra_promotion_eligible": False,
                "facility_qra_blocking_reasons": ["operator_limited"],
            },
        ],
    }
    value.update(overrides)
    return value


def test_completion_audit_consumes_release_boundary_case_audit_as_diagnostic_only():
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        release_boundary_case_audit=_audit(),
    )
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_release_boundary_case_audit"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert report["status"] == "INCOMPLETE_EVIDENCE"


def test_completion_audit_rejects_boundary_audit_with_unsafe_promotion_flag():
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        release_boundary_case_audit=_audit(facility_ir_fn_promotion=True),
    )
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_release_boundary_case_audit"
    )
    assert check["status"] == "BLOCKED"
    assert "unsafe promotion" in check["blocking_reason"]


def test_completion_audit_cross_checks_boundary_rows_against_case_requests():
    audit = _audit()
    audit["rows"] = [
        {
            "event_id": "e1",
            "annual_condition_id": "weather-1",
            "release_branch_id": "branch-1",
            "strict_release_boundary_eligible": True,
            "facility_qra_promotion_eligible": False,
            "facility_qra_blocking_reasons": ["model_prediction"],
            "facility_evidence_request_match": True,
        },
        {
            "event_id": "e2",
            "annual_condition_id": "weather-1",
            "release_branch_id": "branch-1",
            "strict_release_boundary_eligible": False,
            "facility_qra_promotion_eligible": False,
            "facility_qra_blocking_reasons": ["operator_limited"],
            "facility_evidence_request_match": True,
        },
    ]
    audit["facility_evidence_request_alignment_status"] = "ALIGNED"
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        facility_evidence_request={
            "case_requests": [
                {"event_id": "e1", "annual_condition_id": "weather-1", "release_branch_id": "branch-1"},
                {"event_id": "e2", "annual_condition_id": "weather-1", "release_branch_id": "branch-1"},
            ]
        },
        release_boundary_case_audit=audit,
    )
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_release_boundary_case_audit"
    )
    assert check["status"] == "PASS"
    assert check["evidence"]["facility_evidence_request_alignment"] is True


def test_completion_audit_consumes_request_contract_gate():
    audit = _audit(
        facility_evidence_request_contract_status_counts={"ALIGNED": 2},
        facility_evidence_request_contract_blocked_case_count=0,
    )
    for row in audit["rows"]:
        row["facility_evidence_request_contract_status"] = "ALIGNED"
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        release_boundary_case_audit=audit,
    )
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_release_boundary_case_audit"
    )
    assert check["status"] == "PASS"
    assert check["evidence"]["release_audit_evidence_request_contract_valid"] is True


def test_completion_audit_blocks_request_contract_gate_when_case_is_blocked():
    audit = _audit(
        facility_evidence_request_contract_status_counts={"ALIGNED": 1, "BLOCKED": 1},
        facility_evidence_request_contract_blocked_case_count=1,
    )
    audit["rows"][0]["facility_evidence_request_contract_status"] = "ALIGNED"
    audit["rows"][1]["facility_evidence_request_contract_status"] = "BLOCKED"
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        release_boundary_case_audit=audit,
    )
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_release_boundary_case_audit"
    )
    assert check["status"] == "BLOCKED"


def test_completion_audit_blocks_invalid_case_frequency_metadata():
    audit = _audit(
        frequency_binding_status_counts={"BOUND": 1, "UNBOUND": 1},
        frequency_unbound_case_count=1,
        frequency_uncertainty_status_counts={"BOUND": 1, "INVALID": 1},
    )
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        release_boundary_case_audit=audit,
    )
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_release_boundary_case_audit"
    )
    assert check["status"] == "BLOCKED"
    assert check["evidence"]["frequency_binding_metadata_valid"] is False
    assert check["evidence"]["frequency_uncertainty_metadata_valid"] is False
