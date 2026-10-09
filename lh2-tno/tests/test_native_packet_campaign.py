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


def test_native_packet_campaign_records_explicit_compressible_handoff_rebind():
    campaign = {"id": "campaign-1", "event_routes": [{"event_id": "event-1"}]}
    result = {
        "events": [{"id": "event-1"}],
        "cases": [{
            "event_id": "event-1",
            "status": "EXECUTED_OPERATOR_LIMITED",
            "provider_packet_identity": {
                "provider_source_digests": ["source"],
                "provider_result_digests": ["handoff-result"],
            },
        }],
        "risk_atoms": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    provenance = {
        "schema_version": "prism.campaign_compressible_handoff_rebind.v1",
        "event_id": "event-1",
        "original_provider_result_digest": "original",
        "handoff_provider_result_digest": "handoff-result",
        "compressible_plane_handoff_consumed": True,
        "physical_validation_claim": False,
        "frequency_inference": False,
    }
    ledger = build_native_packet_campaign_execution_ledger(campaign, result, provenance)
    assert ledger["compressible_handoff_rebind"]["consumed"] is True
    assert ledger["compressible_handoff_rebind"]["event_id"] == "event-1"
    assert ledger["compressible_handoff_rebind"]["physical_validation_claim"] is False


def test_native_packet_campaign_keeps_uncomputed_cases_without_packet_identity():
    campaign = {
        "id": "campaign-partial",
        "event_routes": [{"event_id": "event-1"}, {"event_id": "event-2"}],
    }
    result = {
        "events": [{"id": "event-1"}, {"id": "event-2"}],
        "cases": [
            {
                "event_id": "event-1",
                "status": "EXECUTED_OPERATOR_LIMITED",
                "provider_packet_identity": {
                    "provider_source_digests": ["source"],
                    "provider_result_digests": ["result"],
                },
            },
            {"event_id": "event-2", "status": "UNCOMPUTED", "reason": "provider packet missing"},
        ],
        "risk_atoms": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    ledger = build_native_packet_campaign_execution_ledger(campaign, result)
    assert ledger["status"] == "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED"
    assert ledger["packet_identity_consumed"] is True
    assert ledger["packet_identity_case_count"] == 1
    assert ledger["uncomputed_case_count"] == 1
    assert ledger["uncomputed_without_packet_identity_case_count"] == 1


def test_native_packet_campaign_reconciles_state_snapshot_event_set():
    campaign = {
        "id": "campaign-state",
        "event_routes": [{"event_id": "event-1"}],
    }
    result = {
        "events": [{"id": "event-1"}],
        "cases": [{
            "event_id": "event-1",
            "status": "EXECUTED_OPERATOR_LIMITED",
            "provider_packet_identity": {"component_id": "tank-1"},
        }],
        "risk_atoms": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    audit = {
        "status": "STATE_SNAPSHOT_BOUND_AND_ECHOED",
        "rows": [{
            "event_id": "event-1",
            "component_id": "tank-1",
            "status": "BOUND_AND_ECHOED",
        }],
    }
    ledger = build_native_packet_campaign_execution_ledger(
        campaign, result, state_snapshot_audit=audit
    )
    reconciliation = ledger["state_snapshot_campaign_reconciliation"]
    assert reconciliation["status"] == "STATE_SNAPSHOT_CAMPAIGN_RECONCILED"
    assert reconciliation["event_set_match"] is True
    assert reconciliation["bound_event_count"] == 1
