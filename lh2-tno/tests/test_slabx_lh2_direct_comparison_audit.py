from __future__ import annotations

import csv
import json
from pathlib import Path

from lh2_tno.slabx_lh2_direct_comparison_audit import (
    audit_slabx_lh2_direct_comparison,
)


def _write_fixture(tmp_path: Path, *, bad_lfl: bool = False) -> tuple[Path, Path, Path, Path]:
    predictions = tmp_path / "sensor_predictions.csv"
    prediction_fields = [
        "test", "sensor", "radius_m", "height_m", "sensor_bearing_deg",
        "model_axis_bearing_deg", "x_downwind_m", "y_crosswind_m",
        "averaging_time_s", "observed_time_mean_vol_pct",
        "SLABx_time_mean_vol_pct", "residual_vol_pct", "observed_LFL", "SLABx_LFL",
    ]
    prediction_rows = []
    for index in range(30):
        observed = 8.0 if index == 0 else 0.2
        predicted = 7.5 if index == 0 else 0.1
        if bad_lfl and index == 1:
            observed = 4.1
        prediction_rows.append({
            "test": "4",
            "sensor": f"OC_{index + 1:02d}",
            "radius_m": "30",
            "height_m": "0.1",
            "sensor_bearing_deg": "45",
            "model_axis_bearing_deg": "90",
            "x_downwind_m": "21.2",
            "y_crosswind_m": "-21.2",
            "averaging_time_s": "275",
            "observed_time_mean_vol_pct": str(observed),
            "SLABx_time_mean_vol_pct": str(predicted),
            "residual_vol_pct": str(predicted - observed),
            "observed_LFL": str(int(observed >= 4.0)),
            "SLABx_LFL": str(int(predicted >= 4.0)),
        })
    with predictions.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=prediction_fields)
        writer.writeheader()
        writer.writerows(prediction_rows)

    refinement = tmp_path / "refinement.csv"
    refinement_fields = [
        "n_field_steps", "substeps", "n_sensor_height_pairs", "bias_vol_pct",
        "MAE_vol_pct", "RMSE_vol_pct", "observed_LFL_pairs", "predicted_LFL_pairs",
        "TP", "FN", "FP",
    ]
    bias = (-0.5 + -0.1 * 29) / 30
    mae = (0.5 + 0.1 * 29) / 30
    rmse = ((0.5**2 + 0.1**2 * 29) / 30) ** 0.5
    refinement_rows = [
        {"n_field_steps": "320", "substeps": "32", "n_sensor_height_pairs": "30",
         "bias_vol_pct": str(bias), "MAE_vol_pct": str(mae), "RMSE_vol_pct": str(rmse),
         "observed_LFL_pairs": "1", "predicted_LFL_pairs": "1", "TP": "1", "FN": "0", "FP": "0"},
        {"n_field_steps": "640", "substeps": "64", "n_sensor_height_pairs": "30",
         "bias_vol_pct": str(bias), "MAE_vol_pct": str(mae), "RMSE_vol_pct": str(rmse),
         "observed_LFL_pairs": "1", "predicted_LFL_pairs": "1", "TP": "1", "FN": "0", "FP": "0"},
    ]
    with refinement.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=refinement_fields)
        writer.writeheader()
        writer.writerows(refinement_rows)

    readme = tmp_path / "README.md"
    readme.write_text(
        "No sensor value, source rate, or concentration coefficient is fitted.\n",
        encoding="utf-8",
    )
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"test": 4}), encoding="utf-8")
    return predictions, refinement, readme, provenance


def test_direct_comparison_audit_passes_and_keeps_promotion_closed(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    report = audit_slabx_lh2_direct_comparison(
        paths[0], paths[1], readme_path=paths[2], provenance_path=paths[3]
    )
    assert report["status"] == "DIRECT_COMPONENT_COMPARISON_REVIEW_READY"
    assert report["metrics"]["row_count"] == 30
    assert report["metrics"]["observed_LFL_pairs"] == 1
    assert report["metrics"]["TP"] == 1
    assert report["claims"]["direct_component_comparison_evidence"] is True
    assert report["claims"]["independent_physical_validation_claim"] is False
    assert report["claims"]["facility_qra_claim"] is False


def test_direct_comparison_audit_blocks_changed_lfl_classification(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path, bad_lfl=True)
    report = audit_slabx_lh2_direct_comparison(paths[0], paths[1], readme_path=paths[2])
    assert report["status"] == "BLOCKED_DIRECT_COMPONENT_COMPARISON"
    assert any("LFL" in reason for reason in report["blocking_reasons"])
