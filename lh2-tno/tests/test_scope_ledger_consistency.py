from lh2_tno.scope_ledger_consistency import audit_scope_ledger_consistency


def _inputs():
    return (
        {
            "facility_id": "facility-1",
            "required_families": ["pipe_hole", "vertical_handoff"],
            "matrix_complete": False,
            "conditional_chain_complete": True,
            "conditional_uncomputed_case_count": 0,
            "rows": [
                {
                    "family": "pipe_hole",
                    "generated_event_count": 1,
                    "event_ids": ["event-1"],
                    "case_count": 1,
                    "conditional_executed_case_count": 1,
                    "conditional_uncomputed_case_count": 0,
                },
                {
                    "family": "vertical_handoff",
                    "generated_event_count": 1,
                    "event_ids": ["event-2"],
                    "case_count": 1,
                    "conditional_executed_case_count": 1,
                    "conditional_uncomputed_case_count": 0,
                },
            ],
        },
        {
            "facility_id": "facility-1",
            "status": "PARTIAL_FACILITY_SCOPE",
            "conditional_uncomputed_case_count": 1,
            "events": [{"id": "event-1"}, {"id": "event-3"}],
            "cases": [
                {"event_id": "event-1", "status": "EXECUTED", "scenario_families": ["pipe_hole"]},
                {"event_id": "event-3", "status": "UNCOMPUTED", "scenario_families": ["pipe_hole"]},
            ],
            "case_count": 2,
        },
    )


def test_scope_ledger_audit_fails_closed_on_event_and_case_mismatch():
    result = audit_scope_ledger_consistency(*_inputs())
    assert result["status"] == "INCONSISTENT_SCOPE_LEDGER"
    assert result["facility_qra_claim"] is False
    assert result["scope_only_event_ids"] == ["event-2"]
    assert result["ledger_only_event_ids"] == ["event-3"]
    assert result["unattributed_ledger_case_count"] == 0
    assert result["blocking_reasons"]


def test_scope_ledger_audit_accepts_matching_tagged_ledger():
    scope, ledger = _inputs()
    ledger["events"] = [{"id": "event-1"}, {"id": "event-2"}]
    ledger["cases"] = [
        {"event_id": "event-1", "status": "EXECUTED", "scenario_families": ["pipe_hole"]},
        {"event_id": "event-2", "status": "EXECUTED", "scenario_families": ["vertical_handoff"]},
    ]
    ledger["case_count"] = 2
    ledger["conditional_uncomputed_case_count"] = 0
    result = audit_scope_ledger_consistency(scope, ledger)
    assert result["status"] == "CONSISTENT_SCOPE_LEDGER"
    assert result["blocking_reasons"] == []
