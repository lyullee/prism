import hashlib
import json
from pathlib import Path

import pytest

from lh2_tno.validation_evidence import build_restricted_pool_record


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package(tmp_path: Path, *, water_rmse: float = 0.137) -> tuple[Path, Path]:
    root = tmp_path / "review"
    for relative, content in {
        "data/dynamic_validation_protocol.json": "{}\n",
        "data/source_manifest.json": "{}\n",
        "data/observation.csv": "time,radius\n0,0\n",
        "src/dynamiclh2poolx/dynamic_pool.py": "# pool\n",
        "src/dynamiclh2poolx/spreading.py": "# spreading\n",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    provenance = {
        "protocol_sha256": _sha(root / "data/dynamic_validation_protocol.json"),
        "source_manifest_sha256": _sha(root / "data/source_manifest.json"),
        "dynamic_pool_py_sha256": _sha(root / "src/dynamiclh2poolx/dynamic_pool.py"),
        "spreading_py_sha256": _sha(root / "src/dynamiclh2poolx/spreading.py"),
        "source_observations": ["data/observation.csv", "data/source_manifest.json"],
    }
    raw = {
        "schema_version": "1.0",
        "decision": "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE",
        "scope": "declared ground-reaching inflow",
        "c2_juel_holdout": {
            "water_trial_4": {"rmse_m": water_rmse, "video_band_coverage": 1.0},
            "aluminium_trial_6": {"rmse_m": 0.102, "video_band_coverage": 1.0},
        },
        "c3_hse_test6": {"maximum_absolute_unledgered_residual_kg": 8.2e-13},
        "excluded_claims": ["atmospheric dispersion", "jet impact"],
        "provenance": provenance,
    }
    evidence = root / "data/stage_c_evidence.json"
    evidence.write_text(json.dumps(raw), encoding="utf-8")
    return evidence, root


def test_restricted_evidence_verifies_hashes_and_holdout_gates(tmp_path):
    evidence, root = _package(tmp_path)
    record = build_restricted_pool_record(evidence, root)
    assert record.decision == "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE"
    assert record.metrics["water_trial_4_radius_rmse_m"] == pytest.approx(0.137)
    assert len(record.verified_files) == 5
    assert record.physical_validation_claim is False
    assert record.full_chain_validation_claim is False


def test_restricted_evidence_rejects_tampered_model_source(tmp_path):
    evidence, root = _package(tmp_path)
    (root / "src/dynamiclh2poolx/dynamic_pool.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_restricted_pool_record(evidence, root)


def test_restricted_evidence_can_report_declared_protocol_drift_without_claiming_validation(tmp_path):
    evidence, root = _package(tmp_path)
    (root / "data/dynamic_validation_protocol.json").write_text("changed\n", encoding="utf-8")
    record = build_restricted_pool_record(evidence, root, allow_provenance_drift=True)
    assert record.provenance_status == "DECLARED_EVIDENCE_WITH_SOURCE_HASH_DRIFT"
    assert record.hash_mismatches == ("data/dynamic_validation_protocol.json",)
    assert record.full_chain_validation_claim is False


def test_restricted_evidence_rejects_holdout_outside_gate(tmp_path):
    evidence, root = _package(tmp_path, water_rmse=0.151)
    with pytest.raises(ValueError, match="RMSE"):
        build_restricted_pool_record(evidence, root)
