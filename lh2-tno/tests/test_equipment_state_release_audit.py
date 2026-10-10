from lh2_tno.equipment_state_release_audit import build_equipment_state_release_audit


def _result():
    case = {
        "event_id": "event-1",
        "annual_condition_id": "condition-1",
        "release_branch_id": "branch-1",
        "asset_id": "asset-1",
        "status": "EXECUTED_OPERATOR_LIMITED",
        "provider_packet_identity": {
            "component_id": "component-1",
            "provider_source_digests": ["source-digest"],
            "provider_result_digests": ["result-digest"],
            "state_snapshot": {
                "schema_version": "prism.equipment_state_snapshot.v1",
                "component_id": "component-1",
                "captured_at_s": 0.0,
                "origin": "model_prediction",
            },
            "state_snapshot_digest": "state-digest",
            "provider_state_snapshot_digest": "state-digest",
            "termination_bases": ["inventory_depletion"],
        },
        "termination": {"basis": "inventory_depletion", "time_s": 0.5},
    }
    return {"facility_id": "facility-1", "cases": [case]}


def test_equipment_state_release_audit_closes_identity_chain():
    report = build_equipment_state_release_audit(_result())
    assert report["status"] == "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
    assert report["case_count"] == 1
    assert report["complete_case_count"] == 1
    assert report["component_ids"] == ["component-1"]
    assert report["operator_limited_case_count"] == 1
    assert report["blocking_reasons"] == []


def test_equipment_state_release_audit_blocks_digest_mismatch():
    result = _result()
    result["cases"][0]["provider_packet_identity"]["provider_state_snapshot_digest"] = "wrong"
    report = build_equipment_state_release_audit(result)
    assert report["status"] == "PARTIAL_EQUIPMENT_STATE_RELEASE_CHAIN"
    assert report["complete_case_count"] == 0
    assert any("digest does not echo" in reason for reason in report["blocking_reasons"])


def test_equipment_state_release_audit_records_synthetic_horizon_echo_gap():
    result = _result()
    case = result["cases"][0]
    case["termination"] = {"basis": "synthetic_diagnostic_horizon", "time_s": 0.37}
    identity = case["provider_packet_identity"]
    identity["termination_bases"] = [None]
    identity["termination_provenances"] = ["synthetic diagnostic horizon; provider basis not declared"]
    report = build_equipment_state_release_audit(result)
    assert report["status"] == "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
    assert report["complete_case_count"] == 1
    assert report["provider_termination_echo_gap_case_count"] == 1
    assert report["blocking_reasons"] == []
