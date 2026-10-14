import json
from pathlib import Path

import pytest

from lh2_tno.dynamiclh2poolx_evidence_audit import (
    DynamicLH2PoolXEvidenceAuditError,
    audit_dynamiclh2poolx_evidence,
)


def _json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "dynamic"
    for relative in (
        "src/dynamiclh2poolx/dynamic_pool.py",
        "src/dynamiclh2poolx/spreading.py",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "juel3155_radius_observations.csv").write_text(
        "source_record_id,trial,role\nwater,3,calibration\nwater,4,holdout\n",
        encoding="utf-8",
    )
    (data / "hse_rr985_test6_radius.csv").write_text(
        "source_record_id,time_s,observed_radius_m\nhse,1,0.2\n", encoding="utf-8"
    )
    _json(data / "stage_c_protocol.json", {"protocol_id": "p"})
    _json(data / "dynamic_validation_protocol.json", {"protocol_id": "p"})
    _json(data / "source_manifest.json", {"manifest_id": "m", "records": []})
    _json(data / "stage_c_evidence.json", {
        "schema_version": "1.0",
        "protocol_id": "p",
        "decision": "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE",
        "component_checks": {"c0": True, "c1": True, "c2": True, "c3": True},
        "c0": {"relative_unledgered_residual": 1e-12},
        "c1": {"spatial_refinement": {
            "liquid_mass_relative_change": 0.01,
            "cumulative_evaporation_relative_change": 0.001,
        }},
        "c2_juel_holdout": {
            "water_trial_4": {"n": 1, "rmse_m": 0.1, "video_band_coverage": 1.0},
            "aluminium_trial_6": {"n": 1, "rmse_m": 0.1, "video_band_coverage": 1.0},
            "calibration_trials": [3, 5],
            "holdout_trials": [4, 6],
        },
        "c3_hse_test6": {"end_of_release_radius_m": 0.9},
        "provenance": {},
    })
    return root


def test_dynamiclh2poolx_audit_records_restricted_component_evidence(tmp_path):
    root = _fixture_root(tmp_path)
    report = audit_dynamiclh2poolx_evidence(root)
    assert report["status"] == "RESTRICTED_COMPONENT_EVIDENCE_CURRENT_SOURCE_REPLAY_WITH_EXTERNAL_EVIDENCE_DRIFT"
    assert report["hash_mismatch_count"] == 4
    assert report["observations"]["holdout_row_count"] == 2
    assert report["observations"]["holdout_is_disjoint"] is True
    assert report["claims"]["restricted_component_evidence"] is True
    assert report["claims"]["independent_physical_validation_claim"] is False
    assert report["claims"]["facility_qra_claim"] is False


def test_dynamiclh2poolx_audit_fails_closed_on_bad_decision(tmp_path):
    root = _fixture_root(tmp_path)
    path = root / "data" / "stage_c_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["decision"] = "PASS_ALL_LH2_PHYSICS"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = audit_dynamiclh2poolx_evidence(root)
    assert report["status"] == "BLOCKED_DYNAMICLH2POOLX_EVIDENCE"
    assert report["claims"]["restricted_component_evidence"] is False
    assert report["claims"]["independent_physical_validation_claim"] is False
    assert report["blocking_reasons"]


def test_dynamiclh2poolx_audit_requires_implementation_files(tmp_path):
    root = _fixture_root(tmp_path)
    (root / "src/dynamiclh2poolx/spreading.py").unlink()
    with pytest.raises(DynamicLH2PoolXEvidenceAuditError, match="spreading_py"):
        audit_dynamiclh2poolx_evidence(root)
