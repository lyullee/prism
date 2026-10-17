from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REPLAY = ROOT / "examples/inspection_center_receiving_runtime_replay_20260121.json"
HAZOP_REPLAY = ROOT / "examples/inspection_center_receiving_hazop_runtime_replay_20260121.json"


def test_inspection_center_runtime_replay_is_state_only_and_mode_bound() -> None:
    runtime = json.loads(RUNTIME_REPLAY.read_text(encoding="utf-8"))
    hazop = json.loads(HAZOP_REPLAY.read_text(encoding="utf-8"))

    assert runtime["status"] == "DIAGNOSTIC_STATE_REPLAY_READY"
    assert runtime["source"]["sample_count"] == 121
    assert runtime["source"]["excel_data_row_start"] == 2
    assert runtime["source"]["excel_data_row_end"] == 122
    frame = runtime["latest_runtime_frame"]
    assert frame["origin"] == "historian_measured"
    assert frame["operating_mode"] == "receiving"
    assert runtime["policy"]["hazop_mode_input_bound"] is True
    assert runtime["policy"]["release_scenario_generated"] is False
    assert runtime["policy"]["frequency_inference_performed"] is False
    assert runtime["policy"]["facility_qra_claim"] is False

    assert hazop["status"] == "OBSERVED_STATE_HAZOP_REPLAY_COMPLETED"
    assert hazop["runtime_frame"]["operating_mode"] == "receiving"
    assert hazop["hazop_selection"]["status"] == "NO_DEVIATION"
    assert hazop["hazop_selection"]["selected_scenarios"] == []
    assert hazop["policy"]["operating_mode_taken_from_explicit_runtime_input"] is True
    assert hazop["policy"]["operating_mode_inferred"] is False
    assert hazop["policy"]["provider_release_created"] is False
    assert hazop["policy"]["frequency_inference_performed"] is False
    assert hazop["policy"]["facility_qra_claim"] is False
