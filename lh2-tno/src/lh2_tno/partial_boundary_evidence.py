"""Audit partial LH2 boundary evidence without promoting it to a release.

Operational procedures often contain useful clues such as a pressure alarm,
an XV command, or a statement that a PSV should operate.  Those clues are
not a provider-owned accident history.  This module records the distinction
explicitly so an operator can attach the same source document later when the
missing setpoint, capacity, termination, and mass ledger are available.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import re
from typing import Any, Callable


SCHEMA = "prism.partial_lh2_boundary_evidence.v1"


def _anchor_text(value: Any) -> str:
    return re.sub(r"[\s\-_/]+", "", str(value or "")).casefold()


def audit_text_anchors(
    pages: Sequence[str],
    anchors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Check declared page/anchor pairs without inferring engineering data."""

    if not isinstance(pages, Sequence) or isinstance(pages, (str, bytes)):
        raise TypeError("pages must be a sequence of page text")
    if not isinstance(anchors, Sequence) or isinstance(anchors, (str, bytes)):
        raise TypeError("anchors must be a sequence")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(anchors):
        if not isinstance(raw, Mapping):
            raise ValueError(f"anchors[{index}] must be an object")
        page = raw.get("page")
        anchor = raw.get("anchor")
        if not isinstance(page, int) or page < 1:
            raise ValueError(f"anchors[{index}].page must be a positive integer")
        if not isinstance(anchor, str) or not anchor.strip():
            raise ValueError(f"anchors[{index}].anchor must be nonempty")
        page_text = pages[page - 1] if page <= len(pages) else ""
        found = _anchor_text(anchor) in _anchor_text(page_text)
        result.append(
            {
                "page": page,
                "anchor": anchor,
                "kind": raw.get("kind"),
                "context": raw.get("context"),
                "anchor_found": found,
                "status": "ANCHOR_FOUND" if found else "ANCHOR_NOT_FOUND",
            }
        )
    return result


def _sha256(path: Any) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_partial_boundary_evidence(
    documents: Sequence[Mapping[str, Any]],
    *,
    page_loader: Callable[[Any], Sequence[str]],
) -> dict[str, Any]:
    """Return a fail-closed inventory of partial operational evidence.

    ``page_loader`` is injected to keep the core testable; the CLI supplies a
    PyPDF reader.  The function deliberately does not accept release mass,
    duration, frequency, or relief-capacity values.
    """

    if not isinstance(documents, Sequence) or isinstance(documents, (str, bytes)):
        raise TypeError("documents must be a sequence")
    if not callable(page_loader):
        raise TypeError("page_loader must be callable")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw in enumerate(documents):
        if not isinstance(raw, Mapping):
            raise ValueError(f"documents[{index}] must be an object")
        path = raw.get("path")
        if path is None or not hasattr(path, "is_file") or not path.is_file():
            errors.append(f"documents[{index}] source file is missing")
            continue
        try:
            pages = list(page_loader(path))
            anchors = raw.get("anchors", ())
            findings = audit_text_anchors(pages, anchors)
            rows.append(
                {
                    "document_id": raw.get("document_id"),
                    "role": raw.get("role"),
                    "source_file": str(path),
                    "source_sha256": _sha256(path),
                    "page_count": len(pages),
                    "anchor_findings": findings,
                    "all_declared_anchors_found": bool(findings)
                    and all(item["anchor_found"] for item in findings),
                }
            )
        except Exception as error:  # pragma: no cover - parser-specific errors
            errors.append(f"documents[{index}] could not be read: {error}")
    found_kinds = {
        item.get("kind")
        for row in rows
        for item in row.get("anchor_findings", ())
        if item.get("anchor_found") and item.get("kind")
    }
    return {
        "schema_version": SCHEMA,
        "status": "PARTIAL_OPERATIONAL_BOUNDARY_EVIDENCE"
        if rows and not errors
        else "PARTIAL_OPERATIONAL_BOUNDARY_EVIDENCE_WITH_READ_ERRORS",
        "documents": rows,
        "document_count": len(rows),
        "anchor_count": sum(len(row["anchor_findings"]) for row in rows),
        "found_anchor_count": sum(
            sum(1 for item in row["anchor_findings"] if item["anchor_found"])
            for row in rows
        ),
        "found_evidence_kinds": sorted(found_kinds),
        "errors": errors,
        "supports": {
            "operating_mode_procedure": "operating_mode" in found_kinds,
            "pressure_trigger_observation": "pressure_trigger" in found_kinds,
            "isolation_or_vent_command_observation": "isolation_command" in found_kinds,
            "provider_release_duration": False,
            "provider_termination_boundary": False,
            "relief_setpoint_certified": False,
            "relief_capacity_certified": False,
            "discharge_complete": False,
            "mass_balance": False,
            "annual_frequency": False,
        },
        "promotion_gates": {
            "provider_packet_promoted": False,
            "frequency_applied": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
        "blocking_reasons": [
            "operational procedure evidence is not a provider-owned accident history",
            "no provider-owned release duration or termination event is present",
            "no reviewed relief setpoint and capacity are present",
            "no provider mass ledger or residual tolerance is present",
            "no accident count and exposure denominator are present for frequency",
        ],
        "interpretation": (
            "The source is useful for procedure, alarm, and command provenance. "
            "It cannot close a PRISM release-boundary case or assign a frequency."
        ),
    }


__all__ = ["SCHEMA", "audit_text_anchors", "audit_partial_boundary_evidence"]
