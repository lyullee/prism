from __future__ import annotations

from scripts.run_process_forecast_hazop_scan import build_scan


def _table():
    return {
        "schema_version": "prism.hazop_operating_mode_selection.v1",
        "id": "table",
        "facility_id": "facility",
        "operating_modes": ["receiving"],
        "configuration_origin": "synthetic",
        "source_provenance": "test table",
        "rows": [{
            "id": "TK01-high-pressure",
            "component_id": "TK-01",
            "component_kind": "storage_tank",
            "operating_modes": ["receiving"],
            "variable_tag": "PT-01",
            "quantity": "pressure",
            "trigger": "at_or_above",
            "threshold_high_si": 600000.0,
            "scenario_family": "vessel_hole",
            "release_mode": "hole",
            "priority": "high",
            "deviation_label": "high pressure",
            "cause_summary": "forecast excursion",
            "consequence_summary": "provider release required",
            "provenance": "test table",
        }],
    }


def test_saved_process_frame_set_runs_fail_closed_hazop_scan():
    record = {
        "schema_version": "prism.process_forecast_frame_set.v1",
        "facility_id": "facility",
        "component_id": "TK-01",
        "operating_mode": "receiving",
        "origin": "model_prediction",
        "source": {"source_digest": "a" * 64},
        "frames": [{
            "schema_version": "prism.hazop_state_frame.v1",
            "facility_id": "facility",
            "component_id": "TK-01",
            "operating_mode": "receiving",
            "captured_at_s": 0.0,
            "forecast_time_s": 0.0,
            "origin": "model_prediction",
            "source_digest": "a" * 64,
            "source_provenance": "test forecast",
            "values": {"PT-01": {
                "component_id": "TK-01",
                "quantity": "pressure",
                "value_si": 650000.0,
                "sensor_location": "tank-vapour",
                "quality": "valid",
            }},
        }],
    }
    result = build_scan(record, {"tables": {"TK-01": _table()}})
    assert result["status"] == "FORECAST_RISK_SCAN_COMPLETE"
    assert result["trigger_count"] == 1
    assert result["evaluated_count"] == 0
    assert result["withheld_count"] == 1
    assert result["policy"]["quantitative_callback_supplied"] is False
    assert result["policy"]["facility_qra_promotion"] is False
