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
    assert rows["vertical_handoff"]["status"] == "PARTIAL"
    assert rows["vessel_hole"]["status"] == "NO_EVENT_GENERATED"
    assert merged["facility_total_risk_available"] is False
    assert merged["diagnostic_only"] is True
