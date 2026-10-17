import pytest

from lh2_tno.facility_campaign_rebaseline import (
    FacilityCampaignRebaselineError,
    rebaseline_facility_campaign,
)


def _row(event_id: str, source: str, result: str):
    return {
        "event_id": event_id,
        "component_id": "line-01",
        "port_id": "line-out",
        "port_ids": ["line-out"],
        "event_kind": "accidental_leak",
        "release_kind": "liquid",
        "provider_source_digest": source * 64,
        "provider_result_digest": result * 64,
        "termination_basis": "reviewed_isolation_success",
        "duration_s": 0.5,
    }


def _record(source: str = "a", result: str = "b"):
    return {
        "status": "NATIVE_PROVIDER_MULTI_EQUIPMENT_FACILITY_CAMPAIGN_EXECUTED_DIAGNOSTIC",
        "packet_digests": [_row("facility/line/G1", source, result)],
        "event_count": 1,
        "case_count": 1,
        "executed_case_count": 1,
        "uncomputed_case_count": 0,
        "failed_case_count": 0,
        "operator_limited_case_count": 0,
        "withheld_case_count": 0,
        "risk_atom_count": 4,
        "facility_total_risk_available": False,
        "facility_qra_claim": False,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "conditional_diagnostic_facility_risk_available": True,
        "frequency_scenario_count": 3,
        "campaign_elapsed_ms": 100.0,
    }


def test_rebaseline_requires_explicit_acknowledgement():
    with pytest.raises(FacilityCampaignRebaselineError, match="acknowledgement"):
        rebaseline_facility_campaign(_record(), _record("c", "d"))


def test_rebaseline_preserves_digest_changes_and_keeps_qra_closed():
    report = rebaseline_facility_campaign(
        _record(), _record("c", "d"), acknowledged=True
    )
    assert report["event_count"] == 1
    assert report["identity_match_count"] == 1
    assert report["digest_comparison"]["result_digest_changed_count"] == 1
    assert report["promotion"]["authoritative_union_rebound"] is False
    assert report["promotion"]["facility_qra_allowed"] is False


def test_rebaseline_rejects_event_set_drift():
    current = _record("c", "d")
    current["packet_digests"][0]["event_id"] = "facility/other/G1"
    with pytest.raises(FacilityCampaignRebaselineError, match="event sets differ"):
        rebaseline_facility_campaign(_record(), current, acknowledged=True)
