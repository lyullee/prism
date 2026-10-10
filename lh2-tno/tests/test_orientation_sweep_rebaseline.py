import json
from pathlib import Path

import pytest

from lh2_tno.orientation_sweep_rebaseline import (
    OrientationSweepRebaselineError,
    rebaseline_orientation_sweep,
)


def _files(tmp_path: Path) -> tuple[Path, Path]:
    field = {
        "schema_version": "prism.external_field_evidence.v1",
        "status": "RESTRICTED_EXTERNAL_FIELD_EVIDENCE",
        "event_id": "event-1",
        "hash_drift_channels": [],
        "channels": [
            {"channel": "source_boundary", "observed_sha256": "a" * 64},
            {"channel": "receptor_observations", "observed_sha256": "b" * 64},
        ],
    }
    sweep = {
        "schema_version": "prism.external_field_orientation_sweep.v1",
        "status": "RESTRICTED_EXTERNAL_FIELD_ORIENTATION_DIAGNOSTIC",
        "event_id": "event-1",
        "field_evidence_status": "RESTRICTED_EXTERNAL_FIELD_EVIDENCE_HASH_DRIFT",
        "bearing_sweep_deg": [286.0],
        "reports": [{
            "bearing_deg": 286.0,
            "status": "RESTRICTED_FIELD_MODEL_COMPARISON_HASH_DRIFT",
            "source_boundary_binding": {
                "source_boundary_sha256": "a" * 64,
                "receptor_observation_sha256": "b" * 64,
            },
        }],
        "promotion_policy": {"bearing_is_not_fitted": True},
    }
    field_path = tmp_path / "field.json"
    sweep_path = tmp_path / "sweep.json"
    field_path.write_text(json.dumps(field), encoding="utf-8")
    sweep_path.write_text(json.dumps(sweep), encoding="utf-8")
    return sweep_path, field_path


def test_rebaseline_requires_acknowledgement(tmp_path):
    sweep, field = _files(tmp_path)
    with pytest.raises(OrientationSweepRebaselineError, match="acknowledgement"):
        rebaseline_orientation_sweep(sweep, field)


def test_rebaseline_clears_only_hash_drift_and_keeps_promotion_closed(tmp_path):
    sweep, field = _files(tmp_path)
    report = rebaseline_orientation_sweep(sweep, field, acknowledged=True)
    assert report["field_evidence_status"] == "RESTRICTED_EXTERNAL_FIELD_EVIDENCE"
    assert report["reports"][0]["status"] == "RESTRICTED_FIELD_MODEL_COMPARISON"
    assert report["rebaseline"]["hash_drift_reports_cleared"] == 1
    assert report["rebaseline"]["promotion_allowed"] is False
    assert report["promotion_policy"]["bearing_is_not_fitted"] is True
