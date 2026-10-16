from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.latest_ijhe_audit_verification import verify_latest_ijhe_audit


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_latest_ijhe_audit_verification_passes_without_opening_qualification(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [
            {"status": "PASS"},
            {"status": "BLOCKED"},
        ],
        "blocking_reasons": ["provider"],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {
            "facility_ir_fn_available": False,
            "physical_validation_claim": False,
        },
    }
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE; 2 checks, 1 BLOCKED",
        "latest_ijhe_completion_audit_check_count": 2,
        "latest_ijhe_completion_audit_blocking_reason_count": 1,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["check_count"] == 2
    assert result["pass_check_count"] == 1
    assert result["blocked_check_count"] == 1
    assert result["complete_facility_qra_claim"] is False


def test_latest_ijhe_audit_verification_blocks_count_drift(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"status": "PASS"}],
        "blocking_reasons": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {
            "facility_ir_fn_available": False,
            "physical_validation_claim": False,
        },
    }
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 99,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("check count" in reason for reason in result["blocking_reasons"])
