"""Regression tests for the actual-source SLABx-LH2 numerical gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_ffi_test6_actual_source_numerical_gate.py"
SPEC = importlib.util.spec_from_file_location("ffi_test6_actual_source_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SOURCE = dict(MODULE.EXPECTED_SOURCE)
MONITORED = tuple(MODULE.MONITORED)


def _write_record(tmp_path: Path, *, delta: float) -> Path:
    record_path = tmp_path / "provenance.json"
    refinement_path = tmp_path / "refinement.json"
    base = {
        "H2_vol_pct_at_30_m": 4.0,
        "centre_height_m_at_30_m": 2.0,
        "cloud_depth_m_at_30_m": 8.0,
        "temperature_K_at_30_m": 268.0,
        "MAE_vol_pct": 1.9,
        "RMSE_vol_pct": 4.5,
    }
    changed = dict(base)
    changed[MONITORED[0]] += delta
    refinement = {
        "schema_version": "prism.slabx_lh2_ffi_test6_actual_source_refinement.v1",
        "scope": "actual FFI Test 6 HorizontalJet source; no sensor fitting",
        "levels": [
            {"n_field_steps": 40, **base},
            {"n_field_steps": 80, **changed},
        ],
    }
    record = {
        "schema_version": MODULE.SCHEMA,
        "scope": "actual FFI Test 6 HorizontalJet source; no sensor fitting",
        "source": SOURCE,
    }
    record_path.write_text(json.dumps(record), encoding="utf-8")
    refinement_path.write_text(json.dumps(refinement), encoding="utf-8")
    return record_path


def test_actual_source_gate_remains_open_when_refinement_exceeds_tolerance(tmp_path: Path):
    result = MODULE.audit(_write_record(tmp_path, delta=0.1))

    assert result["status"] == "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_OPEN"
    assert result["accepted"] is False
    assert result["physical_validation_claim"] is False
    assert result["facility_qra_claim"] is False
    assert result["last_pair_relative_changes"][MONITORED[0]] >= 0.02
    assert result["worst_quantity"] == MONITORED[0]
    assert result["worst_relative_change"] == result["last_pair_relative_changes"][MONITORED[0]]


def test_actual_source_gate_accepts_only_when_all_monitored_values_converge(tmp_path: Path):
    result = MODULE.audit(_write_record(tmp_path, delta=0.001))

    assert result["status"] == "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_ACCEPTED"
    assert result["accepted"] is True
    assert result["blocking_reasons"] == []
    assert result["worst_quantity"] == MONITORED[0]
    assert result["worst_relative_change"] < 0.02
    assert result["physical_validation_claim"] is False
    assert result["facility_qra_claim"] is False


def test_actual_source_gate_rejects_source_identity_mismatch(tmp_path: Path):
    record_path = _write_record(tmp_path, delta=0.001)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["source"]["rate_kg_s"] = 0.8
    record_path.write_text(json.dumps(record), encoding="utf-8")

    result = MODULE.audit(record_path)

    assert result["accepted"] is False
    assert any("rate_kg_s" in reason for reason in result["blocking_reasons"])
