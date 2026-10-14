from __future__ import annotations

from pathlib import Path

import pytest

from lh2_tno.external_document_evidence import (
    ExternalDocumentEvidenceError,
    audit_external_document_evidence,
)


def test_external_pdf_documents_are_provenance_only(tmp_path: Path) -> None:
    piston = tmp_path / "NASA cryogenic piston pump.pdf"
    centrifugal = tmp_path / "NASA LH2 centrifugal pump.pdf"
    piston.write_bytes(b"piston report")
    centrifugal.write_bytes(b"centrifugal report")

    report = audit_external_document_evidence([piston, centrifugal])

    assert report["status"] == "CANDIDATE_EQUIPMENT_PHYSICAL_EVIDENCE_NO_PROMOTION"
    assert report["document_count"] == 2
    assert report["physical_validation_claim"] is False
    assert report["provider_release_packet_claim"] is False
    assert report["frequency_inference_performed"] is False
    assert {row["equipment_family"] for row in report["documents"]} == {
        "cryogenic_piston_pump",
        "lh2_centrifugal_pump",
    }


def test_external_document_audit_rejects_non_pdf(tmp_path: Path) -> None:
    source = tmp_path / "observations.csv"
    source.write_text("x,y\n1,2\n", encoding="utf-8")

    with pytest.raises(ExternalDocumentEvidenceError, match="no readable PDF"):
        audit_external_document_evidence([source])
