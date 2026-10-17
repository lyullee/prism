from copy import deepcopy

from lh2_tno.dynamic_state_closure_audit import (
    annotate_missing_dynamic_state_closure_fields,
    build_dynamic_state_closure_ledger_audit,
)


def _campaign():
    cases = [
        {
            "event_id": "event-a",
            "annual_condition_id": "normal",
            "release_branch_id": "release",
            "ignition_branch": "immediate",
            "dynamic_state_closure_status": "READY",
        },
        {
            "event_id": "event-b",
            "annual_condition_id": "normal",
            "release_branch_id": "release",
            "ignition_branch": "delayed",
            "dynamic_state_closure_status": "BLOCKED",
        },
    ]
    return {
        "events": [
            {"id": "event-a", "model_component_id": "tank"},
            {"id": "event-b", "model_component_id": "pipe"},
        ],
        "cases": cases,
        "uncomputed_cases": [],
        "coverage": {
            "dynamic_state_closure_status_counts": {"BLOCKED": 1, "READY": 1},
            "by_component": [
                {
                    "component_id": "pipe",
                    "dynamic_state_closure_status_counts": {"BLOCKED": 1},
                },
                {
                    "component_id": "tank",
                    "dynamic_state_closure_status_counts": {"READY": 1},
                },
            ],
        },
    }


def _facility():
    return {
        "events": [
            {"id": "event-a", "model_component_id": "tank"},
            {"id": "event-b", "model_component_id": "pipe"},
        ],
        "cases": _campaign()["cases"],
        "uncomputed_cases": [],
        "component_coverage": {
            "pipe": {"dynamic_state_closure_status_counts": {"BLOCKED": 1}},
            "tank": {"dynamic_state_closure_status_counts": {"READY": 1}},
        },
        "conditional_diagnostic_facility_coverage": {
            "dynamic_state_closure_status_counts": {"BLOCKED": 1, "READY": 1},
            "component_case_accounting": {
                "pipe": {"dynamic_state_closure_status_counts": {"BLOCKED": 1}},
                "tank": {"dynamic_state_closure_status_counts": {"READY": 1}},
            },
        },
    }


def test_dynamic_state_closure_audit_recomputes_campaign_and_facility_ledgers():
    report = build_dynamic_state_closure_ledger_audit(
        campaign_results=[_campaign()], facility_result=_facility()
    )
    assert report["status"] == "PASS"
    assert report["blocking_reason_count"] == 0
    assert report["diagnostic_only"] is True
    assert report["facility_qra_claim"] is False


def test_dynamic_state_closure_audit_blocks_tampered_facility_count():
    facility = _facility()
    facility["conditional_diagnostic_facility_coverage"][
        "dynamic_state_closure_status_counts"
    ] = {"READY": 2}
    report = build_dynamic_state_closure_ledger_audit(facility_result=facility)
    assert report["status"] == "BLOCKED"
    assert report["blocking_reason_count"] == 1
    assert "facility.conditional_diagnostic_facility_coverage" in report[
        "blocking_reasons"
    ][0]


def test_dynamic_state_closure_audit_counts_uncomputed_identity_once():
    campaign = _campaign()
    campaign["uncomputed_cases"] = [
        {
            "event_id": "event-b",
            "annual_condition_id": "normal",
            "release_branch_id": "release",
            "ignition_branch": "delayed",
            "dynamic_state_closure_status": "NOT_EVALUATED",
        },
        {
            "event_id": "event-c",
            "dynamic_state_closure_status": "NOT_EVALUATED",
        },
    ]
    campaign["coverage"]["dynamic_state_closure_status_counts"] = {
        "BLOCKED": 1,
        "READY": 1,
    }
    report = build_dynamic_state_closure_ledger_audit(campaign_results=campaign)
    assert report["status"] == "PASS"


def test_dynamic_state_closure_normalizer_marks_missing_campaign_fields_without_inference():
    campaign = deepcopy(_campaign())
    for row in campaign["cases"]:
        row.pop("dynamic_state_closure_status", None)
    campaign["coverage"].pop("dynamic_state_closure_status_counts", None)
    campaign["coverage"].pop("by_component", None)
    normalized = annotate_missing_dynamic_state_closure_fields(campaign)
    assert normalized["dynamic_state_closure_normalization"]["closure_inferred"] is False
    assert normalized["dynamic_state_closure_normalization"]["annotated_case_count"] == 2
    assert {
        row["dynamic_state_closure_status"] for row in normalized["cases"]
    } == {"NOT_DECLARED"}
    report = build_dynamic_state_closure_ledger_audit(campaign_results=normalized)
    assert report["status"] == "PASS"


def test_dynamic_state_closure_normalizer_handles_facility_assessment_wrapper():
    facility = deepcopy(_facility())
    for row in facility["cases"]:
        row.pop("dynamic_state_closure_status", None)
    facility["conditional_diagnostic_facility_coverage"].pop(
        "dynamic_state_closure_status_counts", None
    )
    for row in facility["component_coverage"].values():
        row.pop("dynamic_state_closure_status_counts", None)
    wrapped = {"facility_risk_ledger": facility}
    normalized = annotate_missing_dynamic_state_closure_fields(wrapped)
    assert normalized["facility_risk_ledger"]["cases"][0][
        "dynamic_state_closure_status"
    ] == "NOT_DECLARED"
    report = build_dynamic_state_closure_ledger_audit(
        facility_result=normalized["facility_risk_ledger"]
    )
    assert report["status"] == "PASS"
