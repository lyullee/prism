import hashlib
import json
from pathlib import Path

import pytest

from lh2_tno.external_field_evidence import build_external_field_evidence_record
from lh2_tno.field_model_comparison import (
    FieldModelComparisonError,
    build_field_model_comparison_record,
)


EVENT = "trial-01"
CLOCK = "clock-01"
GEOMETRY = "geometry-01"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _field_bundle(tmp_path: Path, *, hash_drift: bool = False) -> tuple[dict, Path]:
    source = tmp_path / "source.csv"
    source.write_text(
        "event_id,mass_flow_kg_s,phase,release_height_m\n"
        f"{EVENT},0.02,LH2,0.5\n",
        encoding="utf-8",
    )
    weather = tmp_path / "weather.csv"
    weather.write_text(
        "event_id,wind_speed_m_s,wind_direction\n"
        f"{EVENT},2.0,315\n",
        encoding="utf-8",
    )
    receptors = tmp_path / "receptors.csv"
    receptors.write_text(
        "event_id,receptor_geometry_id,sensor_id,common_clock_id,time_s,x_m,y_m,height_m,observed_vol_pct\n"
        f"{EVENT},{GEOMETRY},S01,{CLOCK},11.0,1.0,0.0,0.8,1.0\n"
        f"{EVENT},{GEOMETRY},S01,{CLOCK},12.0,1.0,0.0,0.8,2.0\n"
        f"{EVENT},{GEOMETRY},S02,{CLOCK},11.0,2.0,0.0,0.8,0.5\n"
        f"{EVENT},{GEOMETRY},S02,{CLOCK},12.0,2.0,0.0,0.8,1.5\n",
        encoding="utf-8",
    )
    obstacle = tmp_path / "obstacle.json"
    obstacle.write_text(
        json.dumps({
            "event_id": EVENT,
            "obstacles_present": False,
            "coordinate_reference": "source-relative metres; z above concrete pad",
        }),
        encoding="utf-8",
    )
    clock = tmp_path / "clock.json"
    clock.write_text(json.dumps({"event_id": EVENT, "common_clock_id": CLOCK}), encoding="utf-8")
    channels = [
        ("source_boundary", source),
        ("weather", weather),
        ("obstacle_geometry", obstacle),
        ("receptor_observations", receptors),
        ("common_clock", clock),
    ]
    manifest = {
        "schema": "degali.field-evidence-manifest.v1",
        "event_id": EVENT,
        "dataset_id": "dataset-01",
        "scope": "lh2_free_field",
        "channel_artifacts": [
            {
                "channel": name,
                "path": str(path),
                "sha256": ("0" * 64 if hash_drift and name == "source_boundary" else _sha(path)),
            }
            for name, path in channels
        ],
        "evidence_readiness": {"status": "accepted", "promotion_allowed": False},
        "promotion_allowed": False,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    field = build_external_field_evidence_record(manifest_path, verify_hashes=False)
    return field, receptors


def _prediction(field: dict, *, mode: str = "measured_source_replay", delay: float = 1.0) -> dict:
    return {
        "schema_version": "prism.external_field_model_prediction.v1",
        "event_id": field["event_id"],
        "common_clock_id": field["common_clock"]["common_clock_id"],
        "receptor_geometry_id": "geometry-01",
        "coordinate_reference": "source-relative metres; z above concrete pad",
        "geometry_tolerance_m": 1e-6,
        "time_tolerance_s": 1e-6,
        "time_alignment": {
            "method": "exact",
            "transport_delay_s": delay,
            "prediction_time_offset_s": 0.0,
        },
        "source_boundary_binding": {
            "mode": mode,
            "source_boundary_sha256": field["source_boundary_sha256"],
            "receptor_source_channel_sha256": field["receptor_observation_sha256"],
            "provider_release_contract_verified": mode == "independent_model",
        },
        "receptors": [
            {
                "id": "S01",
                "position_enu_m": [1.0, 0.0, 0.8],
                "concentration_history": [
                    {"time_s": 10.0, "h2_volume_percent": 1.0},
                    {"time_s": 11.0, "h2_volume_percent": 2.0},
                ],
            },
            {
                "id": "S02",
                "position_enu_m": [2.0, 0.0, 0.8],
                "concentration_history": [
                    {"time_s": 10.0, "h2_volume_percent": 0.5},
                    {"time_s": 11.0, "h2_volume_percent": 1.5},
                ],
            },
        ],
    }


def test_field_model_comparison_joins_clock_geometry_and_delay(tmp_path):
    field, _ = _field_bundle(tmp_path)
    report = build_field_model_comparison_record(field, _prediction(field))

    assert report["status"] == "RESTRICTED_FIELD_MODEL_COMPARISON"
    assert report["matching"]["matched_row_count"] == 4
    assert report["metrics"]["rmse_vol_pct"] == pytest.approx(0.0)
    assert report["independent_physical_validation_review_eligible"] is False
    assert report["physical_validation_claim"] is False
    assert report["facility_qra_claim"] is False


def test_measured_source_replay_is_explicitly_not_independent(tmp_path):
    field, _ = _field_bundle(tmp_path)
    prediction = _prediction(field, mode="measured_source_replay")
    report = build_field_model_comparison_record(field, prediction)
    assert report["source_boundary_binding"]["mode"] == "measured_source_replay"
    assert report["independent_physical_validation_review_eligible"] is False
    assert report["promotion_policy"]["measured_source_replay_is_not_independent_validation"] is True


def test_hash_drift_keeps_comparison_restricted(tmp_path):
    field, _ = _field_bundle(tmp_path, hash_drift=True)
    report = build_field_model_comparison_record(field, _prediction(field))
    assert report["status"] == "RESTRICTED_FIELD_MODEL_COMPARISON_HASH_DRIFT"
    assert report["independent_physical_validation_review_eligible"] is False
    assert report["physical_validation_claim"] is False


def test_geometry_mismatch_fails_closed(tmp_path):
    field, _ = _field_bundle(tmp_path)
    prediction = _prediction(field)
    prediction["receptors"][0]["position_enu_m"] = [1.2, 0.0, 0.8]
    with pytest.raises(FieldModelComparisonError, match="outside geometry tolerance"):
        build_field_model_comparison_record(field, prediction)


def test_no_matching_prediction_times_is_blocked(tmp_path):
    field, _ = _field_bundle(tmp_path)
    prediction = _prediction(field, delay=0.0)
    for receptor in prediction["receptors"]:
        receptor["concentration_history"] = [
            {"time_s": 0.0, "h2_volume_percent": 0.0},
            {"time_s": 1.0, "h2_volume_percent": 0.0},
        ]
    report = build_field_model_comparison_record(field, prediction)
    assert report["status"] == "BLOCKED_NO_MATCHED_SAMPLES"
    assert report["matching"]["matched_row_count"] == 0
    assert report["physical_validation_claim"] is False
