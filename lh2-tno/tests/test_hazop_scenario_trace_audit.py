import pytest

from lh2_tno.hazop_scenario_trace_audit import audit_hazop_scenario_trace


def _campaign():
    scenario_id = "TK01-receiving-hole"
    return {
        "schema_version": "prism.hazop_facility_campaign_handoff.v1",
        "status": "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "campaign": {
            "schema_version": "prism.realtime_facility_campaign_result.v1",
            "events": [{"id": "event-1", "hazop_scenario_id": scenario_id}],
            "cases": [{"event_id": "event-1", "hazop_scenario_id": scenario_id}],
            "risk_atoms": [{"event_id": "event-1", "hazop_scenario_id": scenario_id}],
        },
    }


def test_hazop_scenario_trace_requires_all_downstream_rows_to_match():
    request = {
        "case_requests": [{
            "event_id": "event-1",
            "hazop_scenario_id": "TK01-receiving-hole",
            "exact_match_required": {"hazop_scenario_id": "TK01-receiving-hole"},
        }]
    }
    report = audit_hazop_scenario_trace(_campaign(), facility_evidence_request=request)
    assert report["status"] == "HAZOP_SCENARIO_TRACE_COMPLETE"
    assert report["traceable_event_count"] == 1
    assert report["traceable_case_count"] == 1
    assert report["traceable_risk_atom_count"] == 1
    assert report["traceable_provider_request_count"] == 1
    assert report["policy"]["facility_qra_promotion"] is False


def test_hazop_scenario_trace_rejects_drift():
    campaign = _campaign()
    campaign["campaign"]["risk_atoms"][0]["hazop_scenario_id"] = "TK01-supply-hole"
    report = audit_hazop_scenario_trace(campaign)
    assert report["status"] == "HAZOP_SCENARIO_TRACE_BLOCKED"
    assert any("does not match event identity" in error for error in report["errors"])


def test_generic_campaign_without_scenario_id_is_reported_without_inference():
    report = audit_hazop_scenario_trace({
        "schema_version": "prism.realtime_facility_campaign_result.v1",
        "events": [{"id": "event-1"}],
        "cases": [{"event_id": "event-1"}],
        "risk_atoms": [{"event_id": "event-1"}],
    })
    assert report["status"] == "NO_HAZOP_SCENARIO_ID_DECLARED"
    assert report["policy"]["hazop_scenario_id_inferred"] is False
