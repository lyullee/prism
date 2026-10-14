import json
from pathlib import Path

import pytest

from lh2_tno.external_provider_validation import (
    ExternalProviderValidationError,
    audit_external_provider_validation,
)
from lh2_tno.validation_evidence_matrix import build_validation_evidence_matrix


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manifest(tmp_path: Path) -> Path:
    source = _write(tmp_path / "source.json", {
        "dataset_doi": "10.0000/example",
        "status": "source-review-only",
    })
    return _write(tmp_path / "manifest.json", {
        "schema_version": "prism.external_provider_validation_manifest.v1",
        "evidence": [{
            "evidence_id": "source-1",
            "kind": "boundary",
            "path": str(source),
            "source_origin": "public_external_dataset",
            "supports": ["boundary comparison"],
            "does_not_support": ["provider release"],
            "blocking_reasons": ["no exact packet identity"],
            "metrics": {"case_count": 1},
            "provider_packet_match": False,
        }],
    })


def test_external_provider_validation_is_fail_closed_and_hashes_sources(tmp_path: Path):
    provider_root = tmp_path / "provider"
    provider_root.mkdir()
    _write(provider_root / "resolved_release.json", {
        "provider_export_schema": "prism.resolved_release.v1",
        "input_origin": "model_prediction",
        "component_id": "synthetic-component",
        "termination_basis": "inventory_depletion",
    })
    report = audit_external_provider_validation(
        _manifest(tmp_path), provider_artifact_root=provider_root
    )
    assert report["status"] == "RESTRICTED_PROVIDER_COMPONENT_EVIDENCE"
    assert report["summary"]["promotion_blocked_count"] == 1
    assert report["summary"]["actual_origin_provider_artifact_count"] == 0
    assert report["summary"]["synthetic_or_model_prediction_provider_artifact_count"] == 1
    row = report["evidence"][0]
    assert len(row["source"]["sha256"]) == 64
    assert row["promotion"]["provider_packet_match"] is False
    assert row["promotion"]["promotion_status"] == "PROMOTION_BLOCKED"
    assert report["facility_qra_claim"] is False


def test_external_provider_validation_rejects_unsafe_match_declaration(tmp_path: Path):
    manifest = json.loads(_manifest(tmp_path).read_text(encoding="utf-8"))
    manifest["evidence"][0]["provider_packet_match"] = True
    path = _write(tmp_path / "unsafe.json", manifest)
    with pytest.raises(ExternalProviderValidationError, match="provider_packet_match"):
        audit_external_provider_validation(path)


def test_validation_matrix_records_restricted_external_provider_domain(tmp_path: Path):
    pool = _write(tmp_path / "pool.json", {
        "decision": "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE",
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
    })
    equipment = _write(tmp_path / "equipment.json", {
        "status": "RESTRICTED_EQUIPMENT_OBSERVATION_EVIDENCE",
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "dataset": {},
        "independent_validation": {"summary": {}},
    })
    facility = _write(tmp_path / "facility.json", {
        "status": "PARTIAL_FACILITY_SCOPE",
        "facility_total_risk_available": False,
        "qualified_facility_qra_available": False,
        "complete_facility_qra_claim": False,
        "conditional_diagnostic_facility_coverage": {},
    })
    intake = audit_external_provider_validation(_manifest(tmp_path))
    intake_path = _write(tmp_path / "intake.json", intake)
    matrix = build_validation_evidence_matrix(
        pool,
        equipment,
        facility,
        external_provider_validation_path=intake_path,
    )
    domain = next(
        row for row in matrix["evidence_domains"]
        if row["id"] == "external_provider_validation_component_evidence"
    )
    assert domain["promotion_blocked_count"] == 1
    assert domain["provider_packet_match_count"] == 0
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["restricted_external_provider_component_evidence"]["allowed"] is True
    assert claims["qualified_facility_qra"]["allowed"] is False
