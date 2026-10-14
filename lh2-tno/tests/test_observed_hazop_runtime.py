from __future__ import annotations

import pytest

from lh2_tno.observed_hazop_runtime import audit_observed_hazop_runtime
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames


def _source(component_id="tank-01"):
    return {
        "source_id": f"historian-{component_id}",
        "source_sha256": "a" * 64,
        "component_id": component_id,
        "origin": "historian_measured",
        "samples": [{
            "captured_at_s": 3.0,
            "values": {"pressure": {"value_si": 650000.0, "sensor_location": "PT-01"}},
        }],
    }


def _table(component_id="tank-01"):
    return {
        "schema_version": "prism.hazop_operating_mode_selection.v1",
        "id": "runtime-test-hazop",
        "facility_id": "runtime-test-facility",
        "operating_modes": ["receiving", "supply", "standby"],
        "configuration_origin": "synthetic",
        "source_provenance": "test",
        "rows": [{
            "id": "high-pressure",
            "component_id": component_id,
            "component_kind": "storage_tank",
            "operating_modes": ["receiving"],
            "variable_tag": "pressure",
            "quantity": "pressure",
            "trigger": "at_or_above",
            "threshold_high_si": 600000.0,
            "scenario_family": "vessel_hole",
            "release_mode": "hole",
            "priority": "high",
            "deviation_label": "high pressure",
            "cause_summary": "test",
            "consequence_summary": "provider required",
            "provenance": "test",
        }],
    }


def test_observed_hazop_runtime_preserves_explicit_mode_and_selects_scenario():
    frame_report = build_observed_state_runtime_frames(
        [_source()],
        operating_mode_map={"source_to_mode": {"historian-tank-01": "receiving"}},
    )
    report = audit_observed_hazop_runtime(
        frame_report,
        {
            "schema_version": "prism.hazop_runtime_table_set.v1",
            "tables": {"tank-01": _table()},
        },
        now_s=4.0,
    )
    assert report["status"] == "OBSERVED_HAZOP_MODE_SCENARIOS_SELECTED"
    assert report["selected_scenario_count"] == 1
    assert report["operating_mode_counts"] == {"receiving": 1}
    assert report["rows"][0]["selected_scenarios"][0]["provider_release_required"] is True
    assert report["policy"]["operating_mode_inferred"] is False


def test_observed_hazop_runtime_blocks_missing_table():
    frame_report = build_observed_state_runtime_frames(
        [_source()],
        operating_mode_map={"historian-tank-01": "receiving"},
    )
    report = audit_observed_hazop_runtime(
        frame_report,
        {
            "schema_version": "prism.hazop_runtime_table_set.v1",
            "tables": {"other-component": _table("other-component")},
        },
        now_s=4.0,
    )
    assert report["status"] == "OBSERVED_HAZOP_MODE_AUDIT_BLOCKED"
    assert report["rows"][0]["status"] == "HAZOP_TABLE_MISSING"


def test_observed_hazop_runtime_rejects_empty_table_set():
    frame_report = build_observed_state_runtime_frames(
        [_source()],
        operating_mode_map={"historian-tank-01": "receiving"},
    )
    with pytest.raises(ValueError, match="non-empty object"):
        audit_observed_hazop_runtime(
            frame_report,
            {"schema_version": "prism.hazop_runtime_table_set.v1", "tables": {}},
            now_s=4.0,
        )
