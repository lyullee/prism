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
    assert report["family_requests"][0]["promotion_allowed_now"] is False
    assert "pipe upstream/downstream state and isolation response history" in report["family_requests"][0]["required_provider_evidence"]
    assert report["blocking_reasons"] == ["family pipe_hole: PARTIAL"]
    assert report["frequency_policy"]["infer_frequency_from_provider_or_sensor"] is False
    assert {row["component_id"] for row in report["component_requests"]} == {"pipe-01", "vent-01"}
    assert report["excluded_components"] == [{"component_id": "boundary-01", "current_status": "EXCLUDED"}]
