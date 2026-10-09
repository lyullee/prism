from __future__ import annotations

from lh2_tno.frequency_scenario_extension import (
    VERTICAL_HANDOFF_EVENT_IDS,
    extend_frequency_scenarios_for_independent_event_bounds,
    extend_frequency_scenarios_for_vertical_handoff,
)


def test_extension_adds_fixed_vertical_asset_without_mutating_source():
    source = {
        "scenarios": [
            {
                "id": "central",
                "asset_quantiles": {"transfer-line": "published"},
                "provenance": "catalogue central",
            }
        ]
    }
    result = extend_frequency_scenarios_for_vertical_handoff(source)
    assert "vertical-handoff-vent" not in source["scenarios"][0]["asset_quantiles"]
    assert result["scenarios"][0]["asset_quantiles"]["vertical-handoff-vent"] == "published"
    assert "declared diagnostic rate" in result["scenarios"][0]["provenance"]


def test_extension_adds_all_vertical_events_to_event_scenarios():
    source = {
        "scenarios": [
            {
                "id": "independent-low",
                "event_quantiles": {"event-1": "p05"},
            }
        ]
    }
    result = extend_frequency_scenarios_for_vertical_handoff(source)
    events = result["scenarios"][0]["event_quantiles"]
    assert all(events[event_id] == "published" for event_id in VERTICAL_HANDOFF_EVENT_IDS)
    assert events["event-1"] == "p05"


def test_independent_event_extension_uses_bounds_and_explicit_fixed_fallbacks():
    source = {
        "scenarios": [
            {
                "id": "central",
                "asset_quantiles": {"transfer-line": "published"},
                "provenance": "catalogue central",
            }
        ]
    }
    events = [
        {"id": "event-with-bounds", "marginal_p05_per_year": 1e-7, "marginal_p95_per_year": 1e-4},
        {"id": "diagnostic-event-without-bounds", "marginal_p05_per_year": None, "marginal_p95_per_year": None},
    ]
    result = extend_frequency_scenarios_for_independent_event_bounds(source, events)
    assert len(result["scenarios"]) == 3
    low = result["scenarios"][1]
    high = result["scenarios"][2]
    assert low["correlation_assumption"] == "independent_event_bounds"
    assert high["event_quantiles"]["event-with-bounds"] == "p95"
    assert low["event_quantiles"]["event-with-bounds"] == "p05"
    assert low["event_quantiles"]["diagnostic-event-without-bounds"] == "fixed"
    assert result["independent_event_bound_fixed_event_count"] == 1
    assert source["scenarios"][0]["asset_quantiles"] == {"transfer-line": "published"}
