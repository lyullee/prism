import hashlib
import json
from pathlib import Path

import pytest

from lh2_tno.external_field_evidence import (
    ExternalFieldEvidenceError,
    build_external_field_evidence_record,
)


EVENT_ID = "field-trial-01"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path) -> Path:
    source = tmp_path / "source.csv"
    source.write_text(
        "event_id,time_s,mass_flow_kg_s,phase,release_height_m\n"
        f"{EVENT_ID},0,0.02,LH2,0.5\n"
        f"{EVENT_ID},1,0.02,LH2,0.5\n"
        f"{EVENT_ID},2,0,LH2,0.5\n",
        encoding="utf-8",
    )
    weather = tmp_path / "weather.csv"
    weather.write_text(
        "event_id,wind_speed_m_s,wind_direction\n"
        f"{EVENT_ID},1.7,NW\n",
        encoding="utf-8",
    )
    receptors = tmp_path / "receptors.csv"
    receptors.write_text(
        "event_id,sensor_id,time_s,observed_vol_pct\n"
        f"{EVENT_ID},S01,10.0,0.02\n",
        encoding="utf-8",
    )
    obstacle = tmp_path / "obstacle.json"
    obstacle.write_text(
        json.dumps(
            {
                "event_id": EVENT_ID,
                "obstacles_present": False,
                "promotion_status": "conditional_open_pad_only",
            }
        ),
        encoding="utf-8",
    )
    clock = tmp_path / "clock.json"
    clock.write_text(
        json.dumps(
            {
                "event_id": EVENT_ID,
                "common_clock_id": "clock-01",
                "event_clock_origin": "00:00:00",
                "source_window": {"start_s": 0.0, "end_s": 1.0},
                "xensor_window": {"start_index": 0, "end_index": 1},
                "synchronization_method": "shared timestamps",
            }
        ),
        encoding="utf-8",
    )
    channels = [
        ("source_boundary", source),
        ("weather", weather),
        ("obstacle_geometry", obstacle),
        ("receptor_observations", receptors),
        ("common_clock", clock),
    ]
    manifest = {
        "schema": "degali.field-evidence-manifest.v1",
        "manifest_id": "manifest-01",
        "event_id": EVENT_ID,
        "dataset_id": "dataset-01",
        "scope": "lh2_free_field",
        "channel_artifacts": [
            {"channel": name, "path": str(path), "sha256": _hash(path)}
            for name, path in channels
        ],
        "evidence_readiness": {"status": "accepted", "promotion_allowed": False},
        "promotion_allowed": False,
    }
    wrapper = tmp_path / "field-evidence-manifest.json"
    wrapper.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    return wrapper


def test_external_field_bundle_verifies_identity_and_keeps_promotion_closed(tmp_path):
    report = build_external_field_evidence_record(_bundle(tmp_path))

    assert report["status"] == "RESTRICTED_EXTERNAL_FIELD_EVIDENCE"
    assert report["event_id"] == EVENT_ID
    assert report["source_boundary"]["row_count"] == 3
    assert report["source_boundary"]["observed_source_term"]["observed_window_duration_s"] == 2.0
    assert report["source_boundary"]["observed_source_term"]["integrated_mass_left_hold_kg"] == pytest.approx(0.04)
    assert report["source_boundary"]["observed_source_term"]["termination_evidence_present"] is False
    assert report["weather"]["row_count"] == 1
    assert report["receptor_observations"]["row_count"] == 1
    assert report["model_comparison_ready"] is False
    assert report["physical_validation_claim"] is False
    assert report["facility_qra_claim"] is False
    assert all(row["hash_verified"] for row in report["channels"])


def test_external_field_bundle_rejects_hash_drift(tmp_path):
    manifest_path = _bundle(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["channel_artifacts"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ExternalFieldEvidenceError, match="hash mismatch"):
        build_external_field_evidence_record(manifest_path)


def test_external_field_bundle_rejects_promotion_claim(tmp_path):
    manifest_path = _bundle(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["promotion_allowed"] = True
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ExternalFieldEvidenceError, match="promotion_allowed=false"):
        build_external_field_evidence_record(manifest_path)


def test_external_field_bundle_records_hash_drift_when_enforcement_is_disabled(tmp_path):
    manifest_path = _bundle(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["channel_artifacts"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = build_external_field_evidence_record(manifest_path, verify_hashes=False)

    assert report["status"] == "RESTRICTED_EXTERNAL_FIELD_EVIDENCE_HASH_DRIFT"
    assert report["hash_verification_enforced"] is False
    assert report["hash_drift_channels"] == ["source_boundary"]
    assert report["channels"][0]["hash_verified"] is False
