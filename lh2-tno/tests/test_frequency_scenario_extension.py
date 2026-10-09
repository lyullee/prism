from __future__ import annotations

from lh2_tno.frequency_scenario_extension import (
    VERTICAL_HANDOFF_EVENT_IDS,
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
