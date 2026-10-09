from lh2_tno.combined_chain_closure_audit import build_combined_chain_closure_audit


def _packet(**overrides):
    value = {
        "status": "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED",
        "facility_id": "facility",
        "campaign_event_count": 29,
        "packet_event_count": 24,
        "packet_chain_closed_event_count": 24,
        "packet_chain_mismatch_event_ids": [],
        "facility_ir_aggregate_closed": True,
        "facility_fn_aggregate_closed": True,
        "qualified_provider_packet_count": 0,
    }
    value.update(overrides)
    return value


def _vertical(**overrides):
    value = {
        "status": "VERTICAL_OPERATOR_LIMITED_CHAIN_CLOSED",
        "facility_id": "facility",
        "vertical_event_count": 5,
        "vertical_chain_closed_event_count": 5,
        "vertical_chain_mismatch_event_ids": [],
        "all_declared_events_diagnostic_chain_closed": True,
    }
    value.update(overrides)
    return value


def test_combined_closure_keeps_evidence_classes_separate():
    result = build_combined_chain_closure_audit(_packet(), _vertical())
    assert result["status"] == "FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED"
    assert result["combined_diagnostic_closed_event_count"] == 29
    assert result["class_counts"] == {
        "qualified_subset_diagnostic_events": 24,
        "operator_limited_vertical_events": 5,
        "combined_diagnostic_events": 29,
    }
    assert result["qualified_provider_packet_count"] == 0
    assert result["facility_qra_claim"] is False


def test_combined_closure_blocks_count_mismatch():
    result = build_combined_chain_closure_audit(_packet(campaign_event_count=30), _vertical())
    assert result["status"] == "BLOCKED_COMBINED_CHAIN_CLOSURE"
    assert result["event_count_matches_declared_scope"] is False


def test_combined_closure_blocks_vertical_mismatch():
    result = build_combined_chain_closure_audit(
        _packet(), _vertical(vertical_chain_mismatch_event_ids=["vertical/G1"])
    )
    assert result["status"] == "BLOCKED_COMBINED_CHAIN_CLOSURE"
    assert result["mismatch_event_ids"] == ["vertical/G1"]
