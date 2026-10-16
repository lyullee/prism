from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_header_bound_center_manifest_uses_only_explicit_raw_units() -> None:
    manifest = json.loads(
        (ROOT / "examples/inspection_center_header_bound_state_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["schema_version"] == "prism.observed_state_input_manifest.v1"
    assert manifest["source_root"] == "<inspection-center-data-root>"
    assert all(row["origin"] == "model_prediction" for row in manifest["sources"])
    bindings = [
        (signal["column"], signal["unit"])
        for source in manifest["sources"]
        for signal in source["signals"].values()
    ]
    assert sorted(bindings) == sorted(
        [("PT1101", "MPa"), ("PT1105A", "MPa"), ("PT1206", "MPa"),
         ("TT1106", "degC"), ("TT1116", "degC")]
    )
    # Differential-pressure channels are deliberately excluded until their
    # raw unit and quantity meaning are reviewed by the source owner.
    assert not any(column.startswith("DPT") for column, _ in bindings)


def test_header_bound_operating_modes_are_explicit_and_complete() -> None:
    modes = json.loads(
        (ROOT / "examples/inspection_center_header_bound_operating_modes.json").read_text(
            encoding="utf-8"
        )
    )
    assert modes["schema_version"] == "prism.explicit_operating_mode_input.v1"
    assert modes["inference_performed"] is False
    assert modes["sensor_frequency_learning_used"] is False
    assert set(modes["source_to_mode"]) == {
        "inspection-center-intake-10-runs-header-bound",
        "inspection-center-storage-vent-10-runs-header-bound",
        "inspection-center-supply-10-runs-header-bound",
    }
