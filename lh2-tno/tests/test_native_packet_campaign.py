from lh2_tno.native_packet_campaign import build_native_packet_campaign_execution_ledger


def test_native_packet_campaign_preserves_failed_case_and_packet_identity():
    campaign = {
        "id": "campaign-1",
        "scope_provenance": "diagnostic",
        "event_routes": [{"event_id": "event-1"}],
    }
    result = {
        "events": [{"id": "event-1"}],
        "cases": [{
            "event_id": "event-1",
            "status": "FAILED",
            "reason": "handoff required",
            "provider_packet_identity": {
                "provider_source_digests": ["source"],
                "provider_result_digests": ["result"],
            },
        }],
        "risk_atoms": [],
        "total_facility_annual_ir_low_high": None,
        "total_facility_expected_death_fn_low_high": None,
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    ledger = build_native_packet_campaign_execution_ledger(campaign, result)
    assert ledger["status"] == "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED"
    assert ledger["packet_identity_consumed"] is True
    assert ledger["failed_case_count"] == 1
    assert ledger["chain_executed_case_count"] == 0
    assert ledger["facility_total_risk_available"] is False
