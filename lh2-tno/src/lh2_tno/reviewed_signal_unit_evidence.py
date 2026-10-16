"""Audit a reviewed signal-unit map against an engineering procedure.

This is an evidence gate for process-state ingestion.  A mapped unit does not
make a sensor calibrated, does not resolve pressure basis, and does not create
an accident event.  The audit therefore reports partial coverage explicitly
and keeps state-snapshot promotion fail-closed until quality, location and
adapter evidence are also present.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "prism.reviewed_signal_unit_evidence.v1"
_ALLOWED_QUANTITIES = {
    "pressure",
    "temperature",
    "differential_pressure",
    "level_fraction",
}
_ALLOWED_UNITS = {"Pa", "kPa", "MPa", "bar", "K", "degC", "%", "1"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_tag(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").strip().upper())


def _decode_pdf_pages(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except Exception as error:  # pragma: no cover - environment-specific
        raise ValueError(f"pypdf is required to check document anchors: {error}") from error
    try:
        return [(page.extract_text() or "") for page in PdfReader(str(path)).pages]
    except Exception as error:  # pragma: no cover - malformed external document
        raise ValueError(f"cannot read source document: {error}") from error


def _anchor_match(text: str, anchor: str) -> bool:
    # OCR inserts spaces/hyphens into tags and decimal expressions.  Remove
    # separators only for locating the declared anchor; the reported evidence
    # remains the caller's exact page/anchor declaration.
    left = re.sub(r"[\s\-_/]+", "", text).lower()
    right = re.sub(r"[\s\-_/]+", "", anchor).lower()
    return bool(right) and right in left


def _load_unit_map(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, (str, Path)):
        value = json.loads(Path(value).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("unit map must be an object")
    signals = value.get("signal_units")
    if not isinstance(signals, Mapping) or not signals:
        raise ValueError("unit map.signal_units must be a nonempty object")
    result: dict[str, Any] = {}
    for raw_tag, raw in signals.items():
        tag = _normalise_tag(raw_tag)
        if not tag:
            raise ValueError("unit map contains an empty tag")
        if isinstance(raw, str):
            unit = raw
            source_unit = raw
            comparison_unit = None
            quantity = None
            pressure_basis = None
            evidence = []
        elif isinstance(raw, Mapping):
            unit = raw.get("unit")
            source_unit = raw.get("source_unit", unit)
            comparison_unit = raw.get("comparison_unit")
            quantity = raw.get("quantity")
            pressure_basis = raw.get("pressure_basis")
            evidence = raw.get("evidence")
        else:
            raise ValueError(f"unit map entry {raw_tag} must be a string or object")
        if not isinstance(source_unit, str) or source_unit not in _ALLOWED_UNITS:
            raise ValueError(f"unit map entry {raw_tag} has unsupported source_unit")
        if unit is not None and (not isinstance(unit, str) or unit not in _ALLOWED_UNITS):
            raise ValueError(f"unit map entry {raw_tag} has unsupported unit")
        if unit is not None and unit != source_unit:
            raise ValueError(
                f"unit map entry {raw_tag} has conflicting legacy unit and source_unit"
            )
        if comparison_unit is not None and (
            not isinstance(comparison_unit, str) or comparison_unit not in _ALLOWED_UNITS
        ):
            raise ValueError(f"unit map entry {raw_tag} has unsupported comparison_unit")
        if quantity is not None and quantity not in _ALLOWED_QUANTITIES:
            raise ValueError(f"unit map entry {raw_tag} has unsupported quantity")
        if pressure_basis is not None and pressure_basis not in {"absolute", "gauge", "unresolved"}:
            raise ValueError(f"unit map entry {raw_tag} has unsupported pressure_basis")
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)) or not evidence:
            raise ValueError(f"unit map entry {raw_tag} requires page evidence")
        result[tag] = {
            "tag": tag,
            # Keep ``unit`` as the source-unit compatibility field.  The
            # explicit role fields are what new adapters should consume.
            "unit": source_unit,
            "source_unit": source_unit,
            "comparison_unit": comparison_unit,
            "quantity": quantity,
            "pressure_basis": pressure_basis,
            "evidence": list(evidence),
        }
    return result


def _timeseries_headers(timeseries_audit: Mapping[str, Any] | None) -> set[str]:
    headers: set[str] = set()
    if not isinstance(timeseries_audit, Mapping):
        return headers
    for workbook in timeseries_audit.get("files", []):
        if not isinstance(workbook, Mapping):
            continue
        for sheet in workbook.get("sheets", []):
            if not isinstance(sheet, Mapping):
                continue
            signals = sheet.get("signals")
            if isinstance(signals, Sequence) and not isinstance(signals, (str, bytes)):
                for signal in signals:
                    if not isinstance(signal, Mapping):
                        continue
                    if signal.get("category") in {
                        "pressure",
                        "temperature",
                        "differential_pressure",
                        "level",
                        "flow",
                        "hydrogen_fraction",
                    }:
                        token = _normalise_tag(signal.get("header"))
                        if token:
                            headers.add(token)
                continue
            # Public summaries omit signal rows.  In that case retain only
            # recognizable engineering-tag prefixes and discard step/action
            # metadata before comparing map coverage.
            for header in sheet.get("headers", []):
                token = _normalise_tag(header)
                if token.startswith(("PT", "TT", "DPT", "DP", "LT", "FT")):
                    headers.add(token)
    return headers


def audit_reviewed_signal_unit_evidence(
    unit_map: Mapping[str, Any] | str | Path,
    *,
    source_document: str | Path,
    timeseries_audit: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """Verify explicit signal units and page anchors, preserving partial scope."""
    entries = _load_unit_map(unit_map)
    document = Path(source_document)
    if not document.is_file():
        raise ValueError(f"source_document is missing: {document}")
    declared_digest = None
    if isinstance(unit_map, Mapping):
        source_evidence = unit_map.get("source_evidence")
        if isinstance(source_evidence, Mapping):
            declared_digest = source_evidence.get("sha256")
    digest = _sha256(document)
    digest_match = declared_digest is None or declared_digest == digest
    pages = _decode_pdf_pages(document)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for tag, entry in entries.items():
        evidence_rows: list[dict[str, Any]] = []
        for index, evidence in enumerate(entry["evidence"]):
            if not isinstance(evidence, Mapping):
                errors.append(f"{tag}: evidence[{index}] is not an object")
                continue
            page_number = evidence.get("page")
            anchor = evidence.get("anchor")
            if not isinstance(page_number, int) or page_number < 1 or page_number > len(pages):
                errors.append(f"{tag}: evidence[{index}] page is outside source document")
                found = False
            elif not isinstance(anchor, str) or not anchor.strip():
                errors.append(f"{tag}: evidence[{index}] anchor is missing")
                found = False
            else:
                found = _anchor_match(pages[page_number - 1], anchor)
                if not found:
                    errors.append(f"{tag}: declared anchor not found on page {page_number}: {anchor}")
            evidence_rows.append({
                "page": page_number,
                "anchor": anchor,
                "anchor_found": found,
                "context": evidence.get("context"),
            })
        rows.append({
            **{
                key: entry[key]
                for key in (
                    "tag",
                    "unit",
                    "source_unit",
                    "comparison_unit",
                    "quantity",
                    "pressure_basis",
                )
            },
            "evidence": evidence_rows,
            "status": "REVIEWED_ANCHOR_FOUND" if evidence_rows and all(item["anchor_found"] for item in evidence_rows) else "REVIEW_REQUIRED",
        })
    if not digest_match:
        errors.append("source document SHA-256 differs from declared evidence")
    headers = _timeseries_headers(
        json.loads(Path(timeseries_audit).read_text(encoding="utf-8"))
        if isinstance(timeseries_audit, (str, Path))
        else timeseries_audit
    )
    mapped_tags = set(entries)
    observed_mapped = sorted(mapped_tags & headers)
    mapped_not_observed = sorted(mapped_tags - headers)
    observed_unmapped = sorted(headers - mapped_tags)
    valid_rows = [row for row in rows if row["status"] == "REVIEWED_ANCHOR_FOUND"]
    complete_signal_coverage = bool(headers) and not observed_unmapped and not mapped_not_observed
    status = (
        "REVIEWED_SIGNAL_UNIT_EVIDENCE_COMPLETE"
        if digest_match and not errors and complete_signal_coverage
        else "REVIEWED_SIGNAL_UNIT_EVIDENCE_PARTIAL"
        if digest_match and not errors
        else "REVIEWED_SIGNAL_UNIT_EVIDENCE_BLOCKED"
    )
    return {
        "schema_version": SCHEMA,
        "status": status,
        "source_document": str(document),
        "source_document_sha256": digest,
        "declared_source_document_sha256": declared_digest,
        "source_document_digest_match": digest_match,
        "signal_count": len(rows),
        "reviewed_signal_count": len(valid_rows),
        "observed_header_count": len(headers),
        "observed_mapped_signal_count": len(observed_mapped),
        "mapped_but_not_observed_tags": mapped_not_observed,
        "observed_unmapped_tags": observed_unmapped,
        "complete_signal_coverage": complete_signal_coverage,
        "signals": rows,
        "errors": list(dict.fromkeys(errors)),
        "promotion_gates": {
            "unit_evidence_accepted_for_mapped_tags": digest_match and not errors,
            "state_snapshot_binding_allowed": False,
            "numeric_state_binding_allowed": False,
            "pressure_basis_resolved_for_all_pressure_tags": not any(
                row.get("quantity") == "pressure"
                and row.get("pressure_basis") not in {"absolute", "gauge"}
                for row in valid_rows
            ),
            "calibration_quality_evidence_supplied": False,
            "sensor_frequency_learning_used": False,
            "frequency_applied": False,
            "provider_packet_created": False,
            "facility_qra_claim": False,
        },
        "policy": {
            "unit_from_declared_document_anchor_only": True,
            "source_unit_vs_comparison_unit_distinguished": True,
            "comparison_unit_used_for_runtime_conversion": False,
            "unit_inference_from_numeric_range_performed": False,
            "pressure_basis_inference_performed": False,
            "raw_dpt_value_reinterpreted_as_level_percent": False,
            "normal_timeseries_promoted_to_accident_evidence": False,
            "state_snapshot_adapter_executed": False,
            "frequency_inference_performed": False,
            "provider_release_created": False,
        },
    }


__all__ = ["SCHEMA", "audit_reviewed_signal_unit_evidence"]
