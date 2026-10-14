import pytest

from lh2_tno.hazop_event_mode_binding import (
    audit_hazop_event_mode_binding,
    mode_bindings_from_diagnostic,
)


def _campaign(*, event_mode=None, event_scenario=None, case_mode=None, case_scenario=None):
    event = {
        "id": "facility/pipe/G1",
        "model_component_id": "pipe-01",
        "profile": "LH2_PIPE",
        "release": {"mode": "hole"},
        "annual_frequency_per_year": 1.0e-4,
    }
    if event_mode is not None:
        event["operating_mode"] = event_mode
    if event_scenario is not None:
        event["hazop_scenario_id"] = event_scenario
    case = {"event_id": event["id"], "status": "EXECUTED"}
    if case_mode is not None:
        case["operating_mode"] = case_mode
    if case_scenario is not None:
        case["hazop_scenario_id"] = case_scenario
    return {"events": [event], "cases": [case], "risk_atoms": []}


def test_missing_mode_is_an_explicit_binding_request():
    report = audit_hazop_event_mode_binding(_campaign())

    assert report["status"] == "HAZOP_EVENT_MODE_BINDING_REQUIRED"
    assert report["event_count"] == 1
    assert report["mode_required_event_count"] == 1
    assert report["event_rows"][0]["status"] == "MODE_REQUIRED"
    assert report["policy"]["mode_inference_performed"] is False
    assert report["policy"]["missing_mode_withheld"] is True


def test_explicit_mode_and_scenario_are_preserved():
    report = audit_hazop_event_mode_binding(
        _campaign(
            event_mode="supply",
            event_scenario="pipe-01-supply-hole",
            case_mode="supply",
            case_scenario="pipe-01-supply-hole",
        )
    )

    assert report["status"] == "HAZOP_EVENT_MODE_BINDING_COMPLETE"
    assert report["mode_bound_event_count"] == 1
    assert report["event_rows"][0]["status"] == "MODE_PRESENT"


def test_explicit_binding_is_checked_against_event_identity():
    report = audit_hazop_event_mode_binding(
        _campaign(),
        mode_bindings=[
            {
                "event_id": "facility/pipe/G1",
                "component_id": "wrong-component",
                "release_mode": "hole",
                "operating_mode": "supply",
                "hazop_scenario_id": "pipe-01-supply-hole",
            }
        ],
    )

    assert report["status"] == "HAZOP_EVENT_MODE_BINDING_REQUIRED"
    assert report["mode_conflict_event_count"] == 1
    assert any("component_id" in error for error in report["errors"])


def test_provider_event_missing_from_campaign_remains_visible():
    provider = {"work_items": [{"event_id": "facility/pipe/G1"}, {"event_id": "facility/valve/G1"}]}
    report = audit_hazop_event_mode_binding(_campaign(), provider_worklist=provider)

    assert report["provider_event_count"] == 2
    assert any("facility/valve/G1" in error for error in report["errors"])


def test_diagnostic_ledger_is_an_explicit_source_for_single_event_bindings():
    diagnostic = {
        "facility_handoff": {
            "facility_ledger": {
                "component_coverage": {
                    "pipe-01": {
                        "event_ids": ["facility/pipe/G1"],
                        "hazop_scenario_ids": ["pipe-01-supply-hole"],
                        "operating_modes": ["supply"],
                    }
                }
            }
        }
    }
    bindings = mode_bindings_from_diagnostic(diagnostic)

    assert bindings == [{
        "event_id": "facility/pipe/G1",
        "component_id": "pipe-01",
        "operating_mode": "supply",
        "hazop_scenario_id": "pipe-01-supply-hole",
        "source_provenance": "explicit multi-equipment HAZOP facility ledger component_coverage",
    }]


def test_diagnostic_ledger_refuses_ambiguous_multiple_rows():
    diagnostic = {
        "facility_handoff": {
            "facility_ledger": {
                "component_coverage": {
                    "pipe-01": {
                        "event_ids": ["facility/pipe/G1", "facility/pipe/G2"],
                        "hazop_scenario_ids": ["s1", "s2"],
                        "operating_modes": ["supply"],
                    }
                }
            }
        }
    }
    with pytest.raises(ValueError, match="different lengths"):
        mode_bindings_from_diagnostic(diagnostic)

