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
    assert rows["vertical_handoff"]["conditional_status"] == "UNCOMPUTED"
    assert matrix["conditional_chain_blocking_reasons"] == [
        "liquid_two_phase: PARTIAL",
        "vertical_handoff: UNCOMPUTED",
    ]
    assert matrix["matrix_complete"] is False
