from __future__ import annotations

import csv
import json
from pathlib import Path

from lh2_tno.preslhy_slabx_window_audit import (
    PRESLHY_SLABX_WINDOW_SCHEMA,
    PreslhySlabxWindowAuditError,
    audit_preslhy_slabx_window_comparison,
)


def _write_bundle(root: Path, *, accepted: int = 1) -> Path:
    root.mkdir()
    (root / "provenance.json").write_text(
        json.dumps(
            {
                "purpose": "unfitted native-SLABx reconstruction of public PRESLHY E3.5 horizontal releases",
                "trials": [10],
                "final_level": 640,
                "meteorology": {"coordinate_frame": "mean-wind"},
                "observation_operator": "window mean",
            }
        ),
        encoding="utf-8",
    )
    with (root / "sensor_predictions_final.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "trial", "serial", "observed_window_mean_vol_pct", "slabx_window_mean_vol_pct",
                "evaluable", "observed_lfl", "slabx_lfl",
            ],
        )
        writer.writeheader()
        writer.writerow({"trial": 10, "serial": "A", "observed_window_mean_vol_pct": 2.0,
                         "slabx_window_mean_vol_pct": 1.5, "evaluable": 1, "observed_lfl": 0, "slabx_lfl": 0})
        writer.writerow({"trial": 10, "serial": "B", "observed_window_mean_vol_pct": 78.0,
                         "slabx_window_mean_vol_pct": "", "evaluable": 0, "observed_lfl": 1, "slabx_lfl": 0})
    with (root / "refinement_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["trial", "n_field_steps"])
        writer.writeheader()
        writer.writerow({"trial": 10, "n_field_steps": 640})
    with (root / "numerical_gate.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["trial", "accepted"])
        writer.writeheader()
        writer.writerow({"trial": 10, "accepted": accepted})
    return root


def test_audit_records_digest_bound_restricted_component_evidence(tmp_path: Path):
    report = audit_preslhy_slabx_window_comparison(_write_bundle(tmp_path / "bundle"))
    assert report["schema_version"] == PRESLHY_SLABX_WINDOW_SCHEMA
    assert report["status"] == "RESTRICTED_PRESLHY_SLABX_WINDOW_COMPARISON"
    assert report["metrics"]["evaluable_sensor_row_count"] == 1
    assert report["metrics"]["accepted_numerical_gate_count"] == 1
    assert report["physical_validation_claim"] is False
    assert len(report["source_files"]) == 4
    assert all(len(item["sha256"]) == 64 for item in report["source_files"])


def test_audit_fails_closed_when_no_resolution_gate_is_accepted(tmp_path: Path):
    report = audit_preslhy_slabx_window_comparison(
        _write_bundle(tmp_path / "bundle", accepted=0)
    )
    assert report["status"] == "BLOCKED_PRESLHY_SLABX_WINDOW_COMPARISON"
    assert "no trial passed" in " ".join(report["blocking_reasons"])


def test_audit_requires_complete_output_bundle(tmp_path: Path):
    root = tmp_path / "missing"
    root.mkdir()
    try:
        audit_preslhy_slabx_window_comparison(root)
    except PreslhySlabxWindowAuditError as error:
        assert "missing PRESLHY-SLABx output" in str(error)
    else:
        raise AssertionError("missing output bundle must fail closed")
