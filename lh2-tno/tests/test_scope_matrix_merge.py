from lh2_tno.scope_matrix_merge import merge_scope_matrices


def test_scope_matrix_merge_preserves_partial_family_and_counts_events():
    merged = merge_scope_matrices(
        [
            {
                "facility_id": "a",
                "rows": [
                    {"family": "pipe_hole", "status": "EXECUTED", "generated_event_count": 2,
                     "event_ids": ["a/p1", "a/p2"], "case_count": 2, "executed_case_count": 2,
                     "uncomputed_case_count": 0, "generated_initiation_frequency_per_year": 1.0},
                    {"family": "vertical_handoff", "status": "NO_EVENT_GENERATED", "generated_event_count": 0},
                ],
            },
            {
                "facility_id": "b",
                "rows": [
                    {"family": "pipe_hole", "status": "PARTIAL", "generated_event_count": 1,
                     "event_ids": ["b/p3"], "case_count": 1, "executed_case_count": 1,
                     "uncomputed_case_count": 1, "generated_initiation_frequency_per_year": 2.0},
                    {"family": "vertical_handoff", "status": "PARTIAL", "generated_event_count": 2,
                     "event_ids": ["b/v1", "b/v2"], "case_count": 2, "executed_case_count": 1,
                     "uncomputed_case_count": 1, "generated_initiation_frequency_per_year": 3.0},
                ],
            },
        ],
        facility_id="common",
        required_families=("pipe_hole", "vertical_handoff", "vessel_hole"),
    )
    rows = {row["family"]: row for row in merged["rows"]}
    assert rows["pipe_hole"]["status"] == "PARTIAL"
    assert rows["pipe_hole"]["generated_event_count"] == 3
    assert rows["pipe_hole"]["uncomputed_case_count"] == 1
    assert rows["pipe_hole"]["strict_uncomputed_case_count"] == 1
    assert rows["pipe_hole"]["domain_incomplete_case_count"] == 0
    assert rows["pipe_hole"]["strict_blocking_reason"] == "pipe_hole: PARTIAL"
    assert rows["vertical_handoff"]["status"] == "PARTIAL"
    assert rows["vessel_hole"]["status"] == "NO_EVENT_GENERATED"
    assert merged["facility_total_risk_available"] is False
    assert merged["diagnostic_only"] is True


def test_scope_matrix_merge_preserves_not_applicable_family_and_ignores_it_in_blocking():
    merged = merge_scope_matrices(
        [
            {
                "facility_id": "tank-campaign",
                "rows": [{
                    "family": "pump_hole", "status": "NOT_APPLICABLE",
                    "generated_event_count": 0,
                }],
            },
            {
                "facility_id": "pipe-campaign",
                "rows": [{
                    "family": "pump_hole", "status": "NOT_APPLICABLE",
                    "generated_event_count": 0,
                }],
            },
        ],
        facility_id="tank-and-pipe",
        required_families=("pump_hole",),
    )
    row = merged["rows"][0]
    assert row["status"] == "NOT_APPLICABLE"
    assert merged["matrix_complete"] is True
    assert merged["declared_scope_numerically_complete"] is True
    assert merged["blocking_reasons"] == []


def test_scope_matrix_merge_uses_legacy_executed_count_for_conditional_accounting():
    merged = merge_scope_matrices(
        [{
            "facility_id": "legacy",
            "rows": [{
                "family": "inventory_depletion",
                "status": "PARTIAL",
                "generated_event_count": 5,
                "case_count": 5,
                "executed_case_count": 5,
                "uncomputed_case_count": 2,
                "fully_validated_case_count": 3,
                "operator_limited_case_count": 0,
            }],
        }],
        facility_id="legacy-merged",
        required_families=("inventory_depletion",),
    )
    row = merged["rows"][0]
    assert row["conditional_executed_case_count"] == 5
    assert row["conditional_uncomputed_case_count"] == 0
    assert row["conditional_status"] == "EXECUTED"
    assert merged["conditional_chain_complete"] is True
    assert merged["matrix_complete"] is False


def test_scope_matrix_merge_preserves_strict_status_breakdown():
    merged = merge_scope_matrices(
        [{
            "facility_id": "breakdown",
            "rows": [{
                "family": "liquid_two_phase",
                "status": "PARTIAL",
                "conditional_status": "EXECUTED",
                "generated_event_count": 1,
                "case_count": 3,
                "executed_case_count": 3,
                "conditional_executed_case_count": 3,
                "uncomputed_case_count": 3,
                "fully_validated_case_count": 1,
                "operator_limited_case_count": 1,
                "domain_incomplete_case_count": 1,
                "failed_case_count": 0,
            }],
        }],
        facility_id="breakdown-merged",
        required_families=("liquid_two_phase",),
    )
    row = merged["rows"][0]
    assert row["conditional_status"] == "EXECUTED"
    assert row["conditional_executed_case_count"] == 3
    assert row["conditional_uncomputed_case_count"] == 0
    assert row["fully_validated_case_count"] == 1
    assert row["operator_limited_case_count"] == 1
    assert row["domain_incomplete_case_count"] == 1
    assert row["strict_blocking_reason"] == "liquid_two_phase: PARTIAL"
