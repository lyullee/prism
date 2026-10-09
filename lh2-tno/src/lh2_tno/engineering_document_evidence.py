"""Audit engineering documents without promoting them to a provider packet.

P&ID drawings, GA drawings, operating procedures, and emergency procedures are
useful preparation evidence for a digital-twin model.  They are not accident
time histories by themselves.  This module records immutable file metadata and
coarse document classes while keeping state binding, frequency, provider
release, and facility-QRA gates closed.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA = "prism.engineering_document_evidence.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classify_document(relative_path: str) -> dict[str, Any]:
    """Return a generic evidence class derived only from the file name/path."""

    value = relative_path.casefold()
    if "p&id" in value or "p & id" in value or "p_and_id" in value:
        return {
            "document_class": "pid_topology_candidate",
            "candidate_evidence": ["equipment_topology", "port_and_line_labels"],
        }
    if any(token in value for token in ("ga", "준공", "도면", "drawing")):
        return {
            "document_class": "engineering_drawing_candidate",
            "candidate_evidence": ["equipment_geometry", "layout_candidate"],
        }
    if any(token in value for token in ("비상", "emergency", "대응", "훈련", "시나리오")):
        return {
            "document_class": "emergency_procedure_candidate",
            "candidate_evidence": ["emergency_action", "isolation_action_candidate"],
        }
    if any(token in value for token in ("운전절차", "운영", "operation", "하역")):
        return {
            "document_class": "operating_procedure_candidate",
            "candidate_evidence": ["normal_sequence", "operator_action_candidate"],
        }
    if any(token in value for token in ("시험", "평가", "검사", "test", "inspection", "guide")):
        return {
            "document_class": "test_or_inspection_procedure_candidate",
            "candidate_evidence": ["measurement_context", "instrument_candidate"],
        }
    if any(token in value for token in ("연구", "개발", "r&d", "proposal")):
        return {
            "document_class": "project_reference_candidate",
            "candidate_evidence": ["project_scope_context"],
        }
    return {
        "document_class": "unclassified_document",
        "candidate_evidence": [],
    }


def _pdf_page_count(path: Path) -> tuple[int | None, str, str | None]:
    """Use Poppler when available; never fail the audit if it is absent."""

    executable = shutil.which("pdfinfo")
    if executable is None:
        return None, "PAGE_COUNT_UNAVAILABLE", "pdfinfo executable not found"
    try:
        completed = subprocess.run(
            [executable, str(path)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except Exception as exc:  # pragma: no cover - platform/runtime dependent
        return None, "PAGE_COUNT_ERROR", f"{type(exc).__name__}: {exc}"
    if completed.returncode != 0:
        return None, "PAGE_COUNT_ERROR", completed.stderr.strip() or "pdfinfo failed"
    match = re.search(r"^Pages:\s*(\d+)\s*$", completed.stdout, flags=re.MULTILINE)
    if match is None:
        return None, "PAGE_COUNT_UNPARSED", "pdfinfo output did not contain a page count"
    return int(match.group(1)), "PAGE_COUNT_READ", None


def audit_document(path: Path, root: Path) -> dict[str, Any]:
    relative_path = path.relative_to(root).as_posix()
    classification = classify_document(relative_path)
    pages, page_status, page_error = _pdf_page_count(path)
    record: dict[str, Any] = {
        "relative_path": relative_path,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "suffix": path.suffix.casefold(),
        **classification,
        "page_count": pages,
        "page_count_status": page_status,
        "status": "READ_METADATA",
        "raw_text_copied": False,
        "accident_release_packet": False,
        "qualified_provider_packet": False,
    }
    if page_error:
        record["page_count_error"] = page_error
        record["status"] = "READ_METADATA_WITH_PAGE_ERROR"
    return record


def audit_root(source_root: str | Path) -> dict[str, Any]:
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise ValueError(f"source_root is not a directory: {root}")
    files = sorted(path for path in root.rglob("*.pdf") if path.is_file())
    records = [audit_document(path, root) for path in files]
    classes = Counter(item["document_class"] for item in records)
    candidate_evidence = Counter(
        evidence
        for item in records
        for evidence in item.get("candidate_evidence", [])
    )
    page_statuses = Counter(item["page_count_status"] for item in records)
    return {
        "schema_version": SCHEMA,
        "status": "ENGINEERING_DOCUMENT_SCREENING_ONLY",
        "source_root": str(root),
        "source_file_count": len(records),
        "aggregate": {
            "document_class_count": dict(sorted(classes.items())),
            "candidate_evidence_count": dict(sorted(candidate_evidence.items())),
            "page_count_status_count": dict(sorted(page_statuses.items())),
            "accident_release_packet_count": 0,
            "qualified_provider_packet_count": 0,
        },
        "promotion_gates": {
            "equipment_topology_candidate_allowed": any(
                item["document_class"] == "pid_topology_candidate" for item in records
            ),
            "state_snapshot_binding_allowed": False,
            "frequency_applied": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_created": False,
            "facility_qra_claim": False,
            "reason": (
                "Engineering PDFs are preparation evidence only. Exact equipment IDs, "
                "port coordinates, reviewed units, calibration/quality records, and an "
                "accident-only provider history are required before state or QRA promotion."
            ),
        },
        "files": records,
    }


def public_summary(report: dict[str, Any], source_root_label: str = "<engineering-document-root>") -> dict[str, Any]:
    """Remove the local absolute path while preserving an auditable inventory."""

    return {
        "schema_version": report["schema_version"],
        "status": report["status"],
        "source_root": source_root_label,
        "source_file_count": report["source_file_count"],
        "aggregate": report["aggregate"],
        "promotion_gates": report["promotion_gates"],
        "files": [
            {
                key: item.get(key)
                for key in (
                    "relative_path",
                    "sha256",
                    "size_bytes",
                    "suffix",
                    "document_class",
                    "candidate_evidence",
                    "page_count",
                    "page_count_status",
                    "status",
                    "raw_text_copied",
                    "accident_release_packet",
                    "qualified_provider_packet",
                )
            }
            for item in report.get("files", [])
        ],
    }
