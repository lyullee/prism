"""Audit manually reviewed pump test points without opening QRA gates.

The NASA reports in the inspection-centre folder are useful independent model
comparison sources, but their plotted or tabulated observations must be bound
to an exact pump configuration before they can support validation.  This
module records that binding work explicitly.  It never fits a model, infers a
unit, creates a release packet, or promotes facility QRA evidence.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


AUDIT_SCHEMA = "prism.external_pump_test_point_audit.v1"


class ExternalPumpTestPointAuditError(ValueError):
    """Raised when a reviewed pump test-point manifest is unsafe or incomplete."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExternalPumpTestPointAuditError(f"{field} must be a non-empty string")
    return value.strip()


def _positive(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ExternalPumpTestPointAuditError(f"{field} must be positive")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ExternalPumpTestPointAuditError(f"{field} must be numeric") from error
    if not math.isfinite(number) or number <= 0.0:
        raise ExternalPumpTestPointAuditError(f"{field} must be positive and finite")
    return number


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows(value: Any, field: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value or not all(isinstance(row, Mapping) for row in value):
        raise ExternalPumpTestPointAuditError(f"{field} must be a non-empty array of objects")
    return list(value)


def audit_external_pump_test_points(
    manifest: Mapping[str, Any],
    *,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a human-reviewed point manifest and keep validation fail-closed.

    ``manifest`` must contain explicit document hashes and source locators for
    each point.  ``configuration_match_status`` and ``holdout_status`` are
    deliberately reported, never inferred.  A complete manifest still has
    ``physical_validation_claim=False`` because an independent comparison
    result and reviewer decision are separate evidence.
    """

    documents = _rows(manifest.get("documents"), "documents")
    points = _rows(manifest.get("test_points"), "test_points")
    document_index: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for row in documents:
        document_id = _text(row.get("document_id"), "documents.document_id")
        if document_id in document_index:
            raise ExternalPumpTestPointAuditError(f"duplicate document_id: {document_id}")
        path = Path(_text(row.get("path"), f"document[{document_id}].path")).expanduser()
        expected = _text(row.get("sha256"), f"document[{document_id}].sha256").lower()
        if len(expected) != 64:
            raise ExternalPumpTestPointAuditError(f"document[{document_id}].sha256 must be SHA-256")
        actual = None
        if not path.is_file():
            blockers.append(f"document missing: {path}")
        else:
            actual = _sha256(path)
            if actual != expected:
                blockers.append(f"document digest mismatch: {document_id}")
        document_index[document_id] = {
            "document_id": document_id,
            "path": str(path),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "digest_match": actual == expected if actual else False,
            "equipment_family": _text(row.get("equipment_family"), f"document[{document_id}].equipment_family"),
        }

    point_rows: list[dict[str, Any]] = []
    seen_points: set[str] = set()
    for row in points:
        point_id = _text(row.get("point_id"), "test_points.point_id")
        if point_id in seen_points:
            raise ExternalPumpTestPointAuditError(f"duplicate point_id: {point_id}")
        seen_points.add(point_id)
        document_id = _text(row.get("document_id"), f"point[{point_id}].document_id")
        if document_id not in document_index:
            raise ExternalPumpTestPointAuditError(f"point[{point_id}] references unknown document")
        page = _positive(row.get("pdf_page"), f"point[{point_id}].pdf_page")
        variable = _text(row.get("variable"), f"point[{point_id}].variable")
        unit = _text(row.get("unit"), f"point[{point_id}].unit")
        locator = _text(row.get("source_locator"), f"point[{point_id}].source_locator")
        condition = _text(row.get("test_condition"), f"point[{point_id}].test_condition")
        value = _positive(row.get("value"), f"point[{point_id}].value")
        configuration = _text(row.get("configuration_id"), f"point[{point_id}].configuration_id")
        point_rows.append({
            "point_id": point_id,
            "document_id": document_id,
            "pdf_page": int(page),
            "source_locator": locator,
            "variable": variable,
            "value": value,
            "unit": unit,
            "test_condition": condition,
            "configuration_id": configuration,
            "model_binding_status": _text(row.get("model_binding_status"), f"point[{point_id}].model_binding_status"),
            "holdout_role": _text(row.get("holdout_role"), f"point[{point_id}].holdout_role"),
        })

    mapping = manifest.get("model_binding")
    if not isinstance(mapping, Mapping):
        raise ExternalPumpTestPointAuditError("model_binding must be an object")
    configuration_status = _text(mapping.get("configuration_match_status"), "model_binding.configuration_match_status")
    holdout_status = _text(mapping.get("holdout_status"), "model_binding.holdout_status")
    prism_component_id = mapping.get("prism_component_id")
    comparison_result = mapping.get("independent_holdout_result")
    if configuration_status != "MATCHED_REVIEWED":
        blockers.append("exact PRISM pump configuration and port are not reviewed as matched")
    if holdout_status != "COMPLETED_REVIEWED":
        blockers.append("independent no-fit holdout comparison is not completed and reviewed")
    if comparison_result is None:
        blockers.append("independent holdout result is absent")

    report_status = (
        "INDEPENDENT_PUMP_HOLDOUT_CANDIDATE_READY"
        if not blockers
        else "TEST_POINTS_EXTRACTED_CONFIGURATION_REVIEW_REQUIRED"
    )
    root = str(Path(source_root).resolve()) if source_root is not None else None
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": report_status,
        "source_root": root,
        "document_count": len(document_index),
        "test_point_count": len(point_rows),
        "documents": list(document_index.values()),
        "test_points": point_rows,
        "model_binding": {
            "prism_component_id": prism_component_id,
            "configuration_match_status": configuration_status,
            "holdout_status": holdout_status,
            "independent_holdout_result_present": comparison_result is not None,
        },
        "physical_validation_claim": False,
        "provider_release_packet_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_allowed": False,
        "blocking_reasons": blockers,
        "interpretation": (
            "The reviewed points are provenance-bound candidate inputs for a pump-model comparison. "
            "They do not establish a facility accident release, failure frequency, or full-chain physical validation."
        ),
    }


__all__ = ["AUDIT_SCHEMA", "ExternalPumpTestPointAuditError", "audit_external_pump_test_points"]
