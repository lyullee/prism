from lh2_tno.facility_qra_gate import build_facility_qra_gate_summary


def _inputs():
    trace = {
        "status": "CLOSED",
        "risk_atom_count": 1,
        "eligible_risk_atom_count": 1,
        "withheld_risk_atom_count": 0,
        "unmatched_risk_atom_count": 0,
        "ambiguous_risk_atom_count": 0,
        "blocking_reasons": [],
    }
    ledger = {
        "status": "FACILITY_SCOPE_EXECUTED",
        "facility_id": "facility-a",
        "declared_scope_numerically_complete": True,
        "uncomputed_case_count": 0,
        "event_count": 1,
        "case_count": 1,
        "strict_release_boundary": {
            "strict_release_boundary_ready": True,
            "withheld_case_count": 0,
            "blocking_reasons": [],
        },
        "frequency_port_binding": {
            "status": "ALIGNED",
            "facility_qra_allowed": True,
            "frequency_inference_allowed": False,
            "port_scoped_event_count": 1,
            "port_unbound_event_count": 0,
            "mismatch_count": 0,
        },
        "risk_atom_case_traceability": trace,
    }
    assessment = {
        "facility_id": "facility-a",
        "facility_risk_ledger": ledger,
        "provider_qualification_coverage": {
            "complete": True,
            "blocking_reasons": [],
        },
        "conditional_diagnostic_facility_risk_available": True,
    }
    provider = {
        "status": "QUALIFIED",
        "qualification_status": "QUALIFIED_FULL_WORKLIST",
        "release_identity_request_count": 1,
        "exact_match_count": 1,
        "qualified_provider_packet_count": 1,
    }
    validation = {
        "schema_version": "prism.validation_evidence_matrix.v1",
        "status": "INDEPENDENT_VALIDATED",
        "decision": "FACILITY_QRA_ALLOWED",
        "physical_validation_claim": True,
        "full_chain_validation_claim": True,
        "accident_release_validation_claim": True,
        "facility_qra_claim": True,
        "evidence_domains": [{}],
    }
    scope = {
        "schema_version": "prism.major_accident_scope.v1",
        "facility_id": "facility-a",
        "scope": "outdoor_major_accidents",
        "matrix_complete": True,
        "conditional_chain_complete": True,
        "required_families": ["vessel_hole"],
        "case_count": 1,
        "rows": [{
            "family": "vessel_hole",
            "status": "EXECUTED",
            "gap_class": "COMPLETE",
            "operator_limited_case_count": 0,
            "strict_uncomputed_case_count": 0,
            "failed_case_count": 0,
        }],
    }
    return assessment, provider, validation, scope


def test_facility_qra_gate_requires_all_independent_gates():
    assessment, provider, validation, scope = _inputs()
    result = build_facility_qra_gate_summary(
        assessment,
        provider,
        validation,
        assessment_record="assessment.json",
        provider_audit_record="provider.json",
        validation_record="validation.json",
        scope_matrix=scope,
        scope_matrix_record="scope.json",
    )
    assert result["status"] == "FACILITY_QRA_ALLOWED"
    assert result["promotion_allowed"] is True
    assert all(gate["complete"] for gate in result["gates"].values())


def test_facility_qra_gate_withholds_restricted_validation_and_provider():
    assessment, provider, validation, scope = _inputs()
    provider["qualified_provider_packet_count"] = 0
    provider["status"] = "NO_QUALIFIED_PROVIDER_EVIDENCE"
    validation["status"] = "RESTRICTED_EVIDENCE_MATRIX"
    validation["decision"] = "FACILITY_QRA_WITHHELD"
    validation["physical_validation_claim"] = False
    validation["full_chain_validation_claim"] = False
    validation["accident_release_validation_claim"] = False
    validation["facility_qra_claim"] = False
    result = build_facility_qra_gate_summary(
        assessment,
        provider,
        validation,
        assessment_record="assessment.json",
        provider_audit_record="provider.json",
        validation_record="validation.json",
        scope_matrix=scope,
        scope_matrix_record="scope.json",
    )
    assert result["status"] == "FACILITY_QRA_WITHHELD"
    assert result["promotion_allowed"] is False
    assert result["gates"]["provider_qualification"]["complete"] is False
    assert result["gates"]["physical_validation"]["complete"] is False
    assert result["policy"]["missing_evidence_assigned_zero_risk"] is False


def test_facility_qra_gate_uses_full_scope_without_provider_projection():
    assessment, provider, validation, scope = _inputs()
    assessment.pop("provider_qualification_coverage")
    provider["qualified_provider_packet_count"] = 0
    provider["status"] = "NO_QUALIFIED_PROVIDER_EVIDENCE"
    validation["status"] = "RESTRICTED_EVIDENCE_MATRIX"
    validation["decision"] = "FACILITY_QRA_WITHHELD"
    for field in (
        "physical_validation_claim",
        "full_chain_validation_claim",
        "accident_release_validation_claim",
        "facility_qra_claim",
    ):
        validation[field] = False
    result = build_facility_qra_gate_summary(
        assessment,
        provider,
        validation,
        assessment_record="full-scope-assessment.json",
        provider_audit_record="provider.json",
        validation_record="validation.json",
        scope_matrix=scope,
        scope_matrix_record="scope.json",
    )
    assert result["status"] == "FACILITY_QRA_WITHHELD"
    assert result["gates"]["facility_scope"]["case_count"] == 1
    assert result["gates"]["provider_qualification"]["complete"] is False


def test_facility_qra_gate_withholds_without_complete_scope_matrix():
    assessment, provider, validation, _scope = _inputs()
    result = build_facility_qra_gate_summary(
        assessment,
        provider,
        validation,
        assessment_record="assessment.json",
        provider_audit_record="provider.json",
        validation_record="validation.json",
    )
    assert result["status"] == "FACILITY_QRA_WITHHELD"
    assert result["gates"]["facility_scope"]["complete"] is False
    assert result["gates"]["facility_scope"]["scope_matrix_complete"] is False
    assert any("scope matrix" in reason for reason in result["blocking_reasons"])
