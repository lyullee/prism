"""Audit external equipment documents without promoting them to QRA evidence.

The inspection-centre folder contains two NASA LH2 pump test reports.  They are
useful candidate sources for an independent pump-model comparison, but a PDF
report is not an accident-release packet and cannot provide an initiating
frequency or a facility risk total.  This module records provenance and keeps
that boundary explicit.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable


AUDIT_SCHEMA = "prism.external_document_evidence_audit.v1"


class ExternalDocumentEvidenceError(ValueError):
    """Raised when an external document cannot be audited safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ExternalDocumentEvidenceError(f"cannot read external document: {path}") from error
    return digest.hexdigest()


def _classify(path: Path) -> dict[str, Any]:
    name = path.name.lower()
    if "피스톤" in name or "piston" in name:
        equipment_family = "cryogenic_piston_pump"
        title = "NASA preliminary piston pump study for cryogenic fluids"
    elif "원심" in name or "centrifugal" in name:
        equipment_family = "lh2_centrifugal_pump"
        title = "NASA hydrogen test of a small low-specific-speed centrifugal pump stage"
    else:
        equipment_family = "unclassified_external_equipment"
        title = "external equipment document"
    return {
        "equipment_family": equipment_family,
        "document_title": title,
        "evidence_class": "candidate_independent_equipment_model_source",
        "observed_scope": [
            "pump performance and/or cavitation test observations",
            "equipment-model comparison input after unit and configuration review",
        ],
        "not_observed_or_not_promoted": [
            "facility-specific accidental release packet",
            "release duration, isolation state and inventory depletion ledger",
            "SLABx-LH2 atmospheric consequence comparison",
            "initiating-event frequency or sensor-derived failure rate",
            "facility IR/F-N result",
        ],
    }


def audit_external_document_evidence(paths: Iterable[str | Path]) -> dict[str, Any]:
    """Return a provenance-only audit for external equipment documents.

    The audit intentionally does not parse a document into a provider packet.
    Every supplied file must be a readable PDF, and the returned record keeps
    physical-validation and QRA promotion false until a separate comparison
    record binds the document to a model, equipment identity, units, test
    points, uncertainty and independent holdout result.
    """

    resolved_paths = [Path(item).resolve() for item in paths]
    if not resolved_paths:
        raise ExternalDocumentEvidenceError("at least one external document is required")
    documents: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen: set[str] = set()
    for path in resolved_paths:
        key = str(path).casefold()
        if key in seen:
            blockers.append(f"duplicate document path: {path}")
            continue
        seen.add(key)
        if not path.is_file():
            blockers.append(f"document is missing: {path}")
            continue
        if path.suffix.lower() != ".pdf":
            blockers.append(f"document is not a PDF: {path}")
            continue
        classification = _classify(path)
        documents.append({
            "path": str(path),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
            **classification,
        })
    if not documents:
        raise ExternalDocumentEvidenceError("no readable PDF documents were supplied")
    blockers.extend([
        "document content has not been bound to a PRISM provider event/component/port",
        "independent model comparison and holdout result are not present in this audit",
        "document evidence does not establish a release duration, isolation or inventory ledger",
    ])
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": "CANDIDATE_EQUIPMENT_PHYSICAL_EVIDENCE_NO_PROMOTION",
        "diagnostic_only": True,
        "document_count": len(documents),
        "documents": documents,
        "physical_validation_claim": False,
        "provider_release_packet_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "document_is_not_provider_release_packet": True,
            "document_is_not_frequency_evidence": True,
            "comparison_required_before_physical_validation": True,
            "comparison_must_be_independent_and_holdout_scored": True,
            "facility_qra_requires_complete_case_coverage": True,
        },
        "required_follow_up": [
            "extract test-point tables with source page/figure references and engineering units",
            "bind each test point to an exact pump configuration and PRISM equipment port",
            "run a no-fit model replay plus independent holdout comparison with uncertainty",
            "keep accident release, frequency and facility IR/F-N gates closed until separate evidence exists",
        ],
        "blocking_reasons": blockers,
    }


__all__ = [
    "AUDIT_SCHEMA",
    "ExternalDocumentEvidenceError",
    "audit_external_document_evidence",
]
