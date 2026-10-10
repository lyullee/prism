import json
from pathlib import Path

import pytest

from lh2_tno.field_manifest_rebaseline import (
    FieldManifestRebaselineError,
    rebaseline_field_manifest,
)


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    root.mkdir()
    files = {
        "source_boundary": "event_id,mass_flow_kg_s,phase,release_height_m\ne,1,gas,1\n",
        "weather": "event_id,wind_speed_m_s,wind_direction\ne,1,north\n",
        "obstacle_geometry": '{"event_id":"e","obstacles_present":false}',
        "receptor_observations": "event_id,sensor_id,time_s,observed_vol_pct\ne,s,0,1\n",
        "common_clock": '{"event_id":"e","common_clock_id":"clock"}',
    }
    rows = []
    for channel, content in files.items():
        path = root / f"{channel}.json" if channel in {"obstacle_geometry", "common_clock"} else root / f"{channel}.csv"
        path.write_text(content, encoding="utf-8")
        rows.append({"channel": channel, "path": str(path), "sha256": "0" * 64})
    payload = {
        "schema": "degali.field-evidence-manifest-execution.v1",
        "field_evidence_manifest": {
            "schema": "degali.field-evidence-manifest.v1",
            "manifest_id": "old",
            "event_id": "e",
            "dataset_id": "d",
            "audit_root": str(root),
            "scope": "lh2_free_field",
            "channel_artifacts": rows,
            "evidence_readiness": {"status": "accepted", "promotion_allowed": False},
            "promotion_allowed": False,
        },
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_rebaseline_requires_explicit_acknowledgement(tmp_path):
    with pytest.raises(FieldManifestRebaselineError, match="acknowledgement"):
        rebaseline_field_manifest(_bundle(tmp_path))


def test_rebaseline_records_previous_and_current_hashes_without_promotion(tmp_path):
    report = rebaseline_field_manifest(_bundle(tmp_path), acknowledged=True)
    nested = report["field_evidence_manifest"]
    assert report["rebaseline"]["status"] == "HASHES_REBASED_TO_CURRENT_FILES"
    assert nested["rebaseline"]["previous_channel_sha256"]["weather"] == "0" * 64
    assert len(nested["rebaseline"]["current_channel_sha256"]["weather"]) == 64
    assert nested["promotion_allowed"] is False
    assert nested["evidence_readiness"]["promotion_allowed"] is False
