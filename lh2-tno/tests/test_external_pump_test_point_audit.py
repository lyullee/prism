from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from lh2_tno.external_pump_test_point_audit import (
    ExternalPumpTestPointAuditError,
    audit_external_pump_test_points,
)


def _manifest(piston: Path, centrifugal: Path) -> dict:
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    return {
        "documents": [
            {
                "document_id": "piston",
                "path": str(piston),
                "sha256": digest(piston),
                "equipment_family": "cryogenic_piston_pump",
            },
            {
                "document_id": "centrifugal",
                "path": str(centrifugal),
                "sha256": digest(centrifugal),
                "equipment_family": "lh2_centrifugal_pump",
            },
        ],
        "test_points": [
            {
                "point_id": "piston-flow",
                "document_id": "piston",
                "pdf_page": 3,
                "source_locator": "summary design point",
                "variable": "design_flow",
                "value": 55.0,
                "unit": "US_gpm",
                "test_condition": "boiling hydrogen design point",
                "configuration_id": "NASA-piston-five-cylinder",
                "model_binding_status": "candidate_only",
                "holdout_role": "reported_point_not_holdout",
            },
            {
                "point_id": "centrifugal-flow",
                "document_id": "centrifugal",
                "pdf_page": 7,
                "source_locator": "summary scaled design point",
                "variable": "design_flow",
                "value": 15.7,
                "unit": "US_gpm",
                "test_condition": "LH2 configuration 2 scaled design speed",
                "configuration_id": "NASA-CR-187117-config-2",
                "model_binding_status": "candidate_only",
                "holdout_role": "reported_point_not_holdout",
            },
        ],
        "model_binding": {
            "prism_component_id": "liquid-transfer-pump-01",
            "configuration_match_status": "UNREVIEWED",
            "holdout_status": "NOT_STARTED",
        },
    }


def test_reviewed_points_are_hash_bound_but_not_promoted(tmp_path: Path) -> None:
    piston = tmp_path / "NASA piston.pdf"
    centrifugal = tmp_path / "NASA centrifugal.pdf"
    piston.write_bytes(b"piston")
    centrifugal.write_bytes(b"centrifugal")

    report = audit_external_pump_test_points(_manifest(piston, centrifugal))

    assert report["status"] == "TEST_POINTS_EXTRACTED_CONFIGURATION_REVIEW_REQUIRED"
    assert report["test_point_count"] == 2
    assert report["documents"][0]["digest_match"] is True
    assert report["physical_validation_claim"] is False
    assert report["facility_qra_claim"] is False
    assert report["promotion_allowed"] is False
    assert any("configuration" in reason for reason in report["blocking_reasons"])


def test_test_point_manifest_rejects_unknown_document(tmp_path: Path) -> None:
    piston = tmp_path / "NASA piston.pdf"
    centrifugal = tmp_path / "NASA centrifugal.pdf"
    piston.write_bytes(b"piston")
    centrifugal.write_bytes(b"centrifugal")
    value = _manifest(piston, centrifugal)
    value["test_points"][0]["document_id"] = "missing"

    with pytest.raises(ExternalPumpTestPointAuditError, match="unknown document"):
        audit_external_pump_test_points(value)


def test_digest_drift_stays_blocked(tmp_path: Path) -> None:
    piston = tmp_path / "NASA piston.pdf"
    centrifugal = tmp_path / "NASA centrifugal.pdf"
    piston.write_bytes(b"piston")
    centrifugal.write_bytes(b"centrifugal")
    value = _manifest(piston, centrifugal)
    value["documents"][0]["sha256"] = "0" * 64

    report = audit_external_pump_test_points(value)

    assert report["status"] == "TEST_POINTS_EXTRACTED_CONFIGURATION_REVIEW_REQUIRED"
    assert "document digest mismatch: piston" in report["blocking_reasons"]
    assert report["promotion_allowed"] is False
