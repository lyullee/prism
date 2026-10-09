from __future__ import annotations

from lh2_tno.facility_evidence_request import build_facility_evidence_request


def _assessment() -> dict:
    return {
        "facility_id": "facility",
        "facility_risk_ledger": {
            "status": "PARTIAL_FACILITY_SCOPE",
            "event_count": 2,
            "case_count": 3,
            "uncomputed_case_count": 1,
            "risk_atoms": [{"x": 1}],
            "facility_total_risk_available": False,
            "physical_validation_claim": False,
            "blocking_reasons": ["family pipe_hole: PARTIAL", "family pipe_hole: PARTIAL"],
            "component_statuses": {"pipe-01": "PARTIAL", "vent-01": "EXECUTED", "boundary-01": "EXCLUDED"},
        },
    }


def test_builds_family_and_component_requests_without_frequency_inference():
    report = build_facility_evidence_request(
        _assessment(),
        {
            "facility_id": "facility",
            "rows": [
                {
                    "family": "pipe_hole",
                    "status": "PARTIAL",
                    "generated_event_count": 2,
                    "executed_case_count": 3,
                    "uncomputed_case_count": 1,
                    "operator_limited_case_count": 2,
                    "event_ids": ["e1", "e2"],
                }
            ],
        },
    )
    assert report["status"] == "OPEN_EVIDENCE_REQUEST"
    assert report["provider_export_schema_required"] == "prism.external_accident_history.v1"
    assert report["promotion_gate"]["provider_packet_evidence_schema"] == "prism.provider_packet_evidence.v1"
    assert report["promotion_gate"]["exact_event_component_port_and_digest_match_required"] is True
    assert report["family_requests"][0]["promotion_allowed_now"] is False
    assert report["family_requests"][0]["conditional_status"] == "PARTIAL"
    assert report["family_requests"][0]["conditional_executed_case_count"] == 3
    assert report["family_requests"][0]["conditional_uncomputed_case_count"] == 1
    assert report["family_requests"][0]["strict_blocking_reason"] == "pipe_hole: PARTIAL"
    assert report["family_requests"][0]["strict_gate_categories"] == [
        "MISSING_PROVIDER_CASES", "OPERATOR_LIMITED_INPUT"
    ]
    assert len(report["family_requests"][0]["strict_gate_requirements"]) == 2
    assert report["current_assessment"]["strict_gate_categories"] == [
        "MISSING_PROVIDER_CASES", "OPERATOR_LIMITED_INPUT"
    ]
    assert report["family_requests"][0]["family_scope_ready"] is False
    assert report["family_requests"][0]["facility_promotion_allowed_now"] is False
    assert "facility qualified IR/F-N gate is closed" in report["family_requests"][0]["facility_promotion_blocking_reasons"]
    assert "pipe upstream/downstream state and isolation response history" in report["family_requests"][0]["required_provider_evidence"]
    assert report["blocking_reasons"] == ["family pipe_hole: PARTIAL"]
    assert report["frequency_policy"]["infer_frequency_from_provider_or_sensor"] is False
    assert {row["component_id"] for row in report["component_requests"]} == {"pipe-01", "vent-01"}
    assert report["excluded_components"] == [{"component_id": "boundary-01", "current_status": "EXCLUDED"}]


def test_request_preserves_facility_level_conditional_case_accounting():
    assessment = _assessment()
    assessment["facility_risk_ledger"]["conditional_case_count"] = 12
    assessment["facility_risk_ledger"]["conditional_executed_case_count"] = 10
    assessment["facility_risk_ledger"]["conditional_uncomputed_case_count"] = 2
    assessment["facility_risk_ledger"]["conditional_diagnostic_facility_coverage"] = {
        "strict_uncomputed_case_count": 7,
    }
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": []},
    )
    current = report["current_assessment"]
    assert current["conditional_case_count"] == 12
    assert current["conditional_executed_case_count"] == 10
    assert current["conditional_uncomputed_case_count"] == 2
    assert current["strict_uncomputed_case_count"] == 7


def test_facility_promotion_gate_requires_complete_qualified_assessment():
    assessment = _assessment()
    assessment.update({
        "facility_total_risk_available": True,
        "qualified_facility_qra_available": True,
        "complete_facility_qra_claim": True,
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "vent_hole",
            "status": "EXECUTED",
            "generated_event_count": 1,
            "executed_case_count": 1,
            "uncomputed_case_count": 0,
            "event_ids": ["vent-01"],
        }]},
    )
    row = report["family_requests"][0]
    assert row["family_scope_ready"] is True
    assert row["facility_promotion_allowed_now"] is True
    assert row["facility_promotion_blocking_reasons"] == []
    assert report["current_assessment"]["facility_promotion_allowed_now"] is True


def test_not_applicable_family_does_not_create_a_provider_evidence_request():
    report = build_facility_evidence_request(
        _assessment(),
        {
            "facility_id": "facility",
            "rows": [{
                "family": "pump_hole",
                "status": "NOT_APPLICABLE",
                "generated_event_count": 0,
                "executed_case_count": 0,
                "uncomputed_case_count": 0,
                "event_ids": [],
            }],
        },
    )
    row = report["family_requests"][0]
    assert row["applicability"] == "NOT_APPLICABLE"
    assert row["evidence_required"] is False
    assert row["required_provider_evidence"] == []
    assert row["promotion_allowed_now"] is True


def test_two_sided_request_exposes_joint_interaction_evidence_gap():
    report = build_facility_evidence_request(
        _assessment(),
        {
            "facility_id": "facility",
            "rows": [{
                "family": "two_sided_rupture",
                "status": "PARTIAL",
                "generated_event_count": 1,
                "executed_case_count": 1,
                "uncomputed_case_count": 1,
                "event_ids": ["rupture-01"],
            }],
        },
    )
    required = report["family_requests"][0]["required_provider_evidence"]
    assert any("paired plume/pressure/inventory interaction" in item for item in required)


def test_gate_categories_preserve_domain_and_failure_reasons():
    report = build_facility_evidence_request(
        _assessment(),
        {"facility_id": "facility", "rows": [{
            "family": "vertical_handoff",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 0,
            "operator_limited_case_count": 0,
            "domain_incomplete_case_count": 2,
            "failed_case_count": 1,
        }]},
    )
    row = report["family_requests"][0]
    assert row["strict_gate_categories"] == ["DOMAIN_INCOMPLETE", "FAILED_PROVIDER_CASE"]
    assert "DOMAIN_INCOMPLETE" in report["current_assessment"]["strict_gate_categories"]
    assert report["strict_gate_catalog"]["FAILED_PROVIDER_CASE"].startswith("repeat the failed")
