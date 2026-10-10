from lh2_tno.facility_scope_matrix import (
    build_scope_matrix_from_facility_ledger,
    repair_facility_ledger_scenario_families,
)


def _ledger():
    return {
        "facility_id": "facility-1",
        "facility_total_risk_available": False,
        "conditional_uncomputed_case_count": 1,
        "events": [
            {
                "id": "facility/pipe/1",
                "profile": "LH2_PIPE",
                "release": {"mode": "hole"},
                "annual_frequency_per_year": 1.0e-3,
            },
            {
                "id": "facility/vertical/1",
                "profile": "LH2_VALVE",
                "release": {"mode": "hole"},
                "annual_frequency_per_year": 2.0e-3,
            },
        ],
        "cases": [
            {
                "event_id": "facility/pipe/1",
                "status": "EXECUTED",
                "scenario_families": ["pipe_hole", "liquid_two_phase"],
            },
            {
                "event_id": "facility/vertical/1",
                "status": "UNCOMPUTED",
            },
        ],
        "uncomputed_cases": [],
        "risk_atoms": [],
    }


def test_repair_preserves_existing_tags_and_requires_exact_override():
    repaired = repair_facility_ledger_scenario_families(
        _ledger(),
        event_family_overrides={"facility/vertical/1": ["vertical_handoff"]},
    )
    event = {row["id"]: row for row in repaired["events"]}
    assert event["facility/pipe/1"]["scenario_families"] == [
        "pipe_hole",
        "liquid_two_phase",
    ]
    assert event["facility/vertical/1"]["scenario_families"] == [
        "valve_hole",
        "liquid_two_phase",
        "vertical_handoff",
    ]
    assert repaired["cases"][1]["scenario_families"] == [
        "valve_hole",
        "liquid_two_phase",
        "vertical_handoff",
    ]
    assert repaired["scenario_family_metadata"]["explicit_override_event_count"] == 1


def test_ledger_backed_matrix_matches_repaired_ledger_accounting():
    repaired = repair_facility_ledger_scenario_families(
        _ledger(),
        event_family_overrides={"facility/vertical/1": ["vertical_handoff"]},
    )
    matrix = build_scope_matrix_from_facility_ledger(
        repaired,
        required_families=("pipe_hole", "liquid_two_phase", "vertical_handoff"),
    )
    rows = {row["family"]: row for row in matrix["rows"]}
    assert matrix["event_count"] == 2
    assert matrix["case_count"] == 2
    assert matrix["conditional_uncomputed_case_count"] == 1
    assert rows["pipe_hole"]["event_ids"] == ["facility/pipe/1"]
    assert rows["vertical_handoff"]["event_ids"] == ["facility/vertical/1"]
    assert rows["vertical_handoff"]["conditional_uncomputed_case_count"] == 1
    assert rows["vertical_handoff"]["not_numerically_executed_case_count"] == 1
    assert rows["vertical_handoff"]["qualified_evidence_withheld_case_count"] == 0
    assert rows["vertical_handoff"]["numerically_executed_case_count"] == 0
    assert rows["vertical_handoff"]["fully_validated_case_count"] == 0
    assert rows["vertical_handoff"]["operator_limited_case_count"] == 0
    assert rows["vertical_handoff"]["domain_incomplete_case_count"] == 0
    assert rows["vertical_handoff"]["failed_case_count"] == 0
    assert rows["vertical_handoff"]["uncomputed_case_count"] == 1
    assert rows["vertical_handoff"]["conditional_status"] == "UNCOMPUTED"
    assert matrix["not_numerically_executed_case_count"] == 1
    assert matrix["qualified_evidence_withheld_case_count"] == 0
    assert matrix["numerically_executed_case_count"] == 1
    assert matrix["conditional_chain_blocking_reasons"] == [
        "liquid_two_phase: PARTIAL",
        "vertical_handoff: UNCOMPUTED",
    ]
    assert rows["pipe_hole"]["gap_class"] == "COMPLETE"
    assert rows["vertical_handoff"]["gap_class"] == "NUMERICAL_CASE_MISSING"
    assert rows["vertical_handoff"]["case_status_counts"] == {"UNCOMPUTED": 1}
    assert rows["vertical_handoff"]["closure_requirements"]
    assert matrix["gap_summary"]["numerical_case_gap_family_count"] == 2
    assert matrix["matrix_complete"] is False


def test_operator_limited_cases_are_qualification_gaps_not_numerical_gaps():
    ledger = _ledger()
    ledger["conditional_uncomputed_case_count"] = 0
    ledger["cases"] = [
        {
            "event_id": "facility/pipe/1",
            "status": "EXECUTED_OPERATOR_LIMITED",
            "scenario_families": ["pipe_hole"],
        },
    ]
    ledger["events"] = ledger["events"][:1]
    ledger["events"][0]["scenario_families"] = ["pipe_hole"]
    matrix = build_scope_matrix_from_facility_ledger(
        ledger,
        required_families=("pipe_hole",),
    )
    row = matrix["rows"][0]
    assert row["conditional_status"] == "EXECUTED"
    assert row["not_numerically_executed_case_count"] == 0
    assert row["qualified_evidence_withheld_case_count"] == 1
    assert row["gap_class"] == "QUALIFICATION_EVIDENCE_WITHHELD"
    assert matrix["gap_summary"]["families_with_qualification_gap"] == ["pipe_hole"]
