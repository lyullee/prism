from __future__ import annotations

from lh2_tno.process_forecast import build_forecast_frames, merge_forecast_frame_sets
from scripts.run_merged_process_forecast_hazop_scan import build_scan


def _table(component_id: str, mode: str, tag: str = "pressure"):
    return {
        "schema_version": "prism.hazop_operating_mode_selection.v1",
        "id": f"{component_id}-table",
        "facility_id": "facility",
        "operating_modes": [mode],
        "configuration_origin": "synthetic",
        "source_provenance": "test table",
        "rows": [{
            "id": f"{component_id}-high-pressure",
            "component_id": component_id,
            "component_kind": "storage_tank",
            "operating_modes": [mode],
            "variable_tag": tag,
            "quantity": "pressure",
            "trigger": "at_or_above",
            "threshold_high_si": 500000.0,
            "scenario_family": "vessel_hole",
            "release_mode": "hole",
            "priority": "high",
            "deviation_label": "high pressure",
            "cause_summary": "forecast excursion",
            "consequence_summary": "provider release required",
            "provenance": "test table",
        }],
    }


def test_merged_process_forecast_scan_covers_all_components_and_keeps_modes():
    records = [
        build_forecast_frames(
            [{"pressure": 0.60}, {"pressure": 0.40}],
            facility_id="facility",
            component_id="intake",
            operating_mode="receiving",
            mapping={"pressure": {"source_column": "pressure", "quantity": "pressure", "unit": "MPa"}},
            source_id="forecast://intake",
            source_provenance="test rows",
        ),
        build_forecast_frames(
            [{"pressure": 0.40}, {"pressure": 0.40}],
            facility_id="facility",
            component_id="storage",
            operating_mode="standby",
            mapping={"pressure": {"source_column": "pressure", "quantity": "pressure", "unit": "MPa"}},
            source_id="forecast://storage",
            source_provenance="test rows",
        ),
    ]
    merged = merge_forecast_frame_sets(records)
    result = build_scan(
        merged,
        {"tables": {
            "intake": _table("intake", "receiving"),
            "storage": _table("storage", "standby"),
        }},
    )

    assert result["status"] == "FORECAST_RISK_SCAN_COMPLETE"
    assert result["input_frame_set"]["component_ids"] == ["intake", "storage"]
    assert result["input_frame_set"]["operating_modes_by_component"] == {
        "intake": "receiving",
        "storage": "standby",
    }
    assert result["trigger_count"] == 1
    assert result["withheld_count"] == 1
    assert result["policy"]["quantitative_callback_supplied"] is False
    assert result["policy"]["facility_qra_promotion"] is False
