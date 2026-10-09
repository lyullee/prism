"""Merge mechanism-coverage matrices from disjoint diagnostic campaigns.

The merged matrix is an accounting artifact.  It combines generated events
and execution statuses by accident family but never changes a partial row to
``EXECUTED`` and never creates a missing event.  This lets the IJHE audit use
the same facility scope view as the facility risk ledger.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import canonical_digest


def _status(rows: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(row.get("status", "UNCOMPUTED")) for row in rows}
    generated = sum(int(row.get("generated_event_count", 0) or 0) for row in rows)
    if not rows:
        return "NO_EVENT_GENERATED"
    effective = statuses - {"NOT_APPLICABLE"}
    if generated == 0 and not effective:
        return "NOT_APPLICABLE"
    if generated == 0:
        return "NO_EVENT_GENERATED"
    if effective == {"EXECUTED"}:
        return "EXECUTED"
    if effective == {"FAILED"}:
        return "FAILED"
    return "PARTIAL"


def merge_scope_matrices(
    matrices: Sequence[Mapping[str, Any]],
    *,
    facility_id: str,
    required_families: Sequence[str],
) -> dict[str, Any]:
    """Return one fail-closed facility mechanism matrix."""
    if not matrices:
        raise ValueError("at least one scope matrix is required")
    if not facility_id.strip():
        raise ValueError("facility_id must be nonempty")
    families = tuple(dict.fromkeys(str(family) for family in required_families if str(family).strip()))
    if not families:
        raise ValueError("required_families must be nonempty")
    by_family: dict[str, list[Mapping[str, Any]]] = {family: [] for family in families}
    source_records: list[dict[str, Any]] = []
    alignment_record: Mapping[str, Any] | None = None
    for index, matrix in enumerate(matrices):
        if not isinstance(matrix, Mapping):
            raise ValueError(f"scope matrix {index} must be an object")
        rows = matrix.get("rows")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ValueError(f"scope matrix {index} has no rows array")
        source_records.append({
            "facility_id": matrix.get("facility_id"),
            "status": matrix.get("status", matrix.get("campaign_status")),
            "digest": canonical_digest(matrix),
            "record_index": index,
        })
        if alignment_record is None and isinstance(matrix.get("provider_worklist_alignment"), Mapping):
            alignment_record = matrix["provider_worklist_alignment"]
        for row in rows:
            if not isinstance(row, Mapping) or not row.get("family"):
                raise ValueError(f"scope matrix {index} contains an invalid family row")
            family = str(row["family"])
            if family in by_family:
                by_family[family].append(row)

    merged_rows: list[dict[str, Any]] = []
    blocking: list[str] = []
    for family in families:
        source_rows = by_family[family]
        event_ids: list[str] = []
        for row in source_rows:
            values = row.get("event_ids", ())
            if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                event_ids.extend(str(value) for value in values)
        status = _status(source_rows)
        generated = sum(int(row.get("generated_event_count", 0) or 0) for row in source_rows)
        case_count = sum(int(row.get("case_count", 0) or 0) for row in source_rows)
        executed_count = sum(int(row.get("executed_case_count", 0) or 0) for row in source_rows)
        uncomputed_count = sum(int(row.get("uncomputed_case_count", 0) or 0) for row in source_rows)
        frequency = sum(
            float(row.get("generated_initiation_frequency_per_year", 0.0) or 0.0)
            for row in source_rows
        )
        merged = {
            "family": family,
            "status": status,
            "source_matrix_count": len(source_rows),
            "event_ids": sorted(dict.fromkeys(event_ids)),
            "generated_event_count": generated,
            "case_count": case_count,
            "executed_case_count": executed_count,
            "uncomputed_case_count": uncomputed_count,
            "generated_initiation_frequency_per_year": frequency,
            "fully_validated_case_count": sum(
                int(row.get("fully_validated_case_count", 0) or 0) for row in source_rows
            ),
            "operator_limited_case_count": sum(
                int(row.get("operator_limited_case_count", 0) or 0) for row in source_rows
            ),
            "failed_case_count": sum(
                int(row.get("failed_case_count", 0) or 0) for row in source_rows
            ),
            "frequency_rows_are_not_additive_across_families": True,
            "source_statuses": sorted({str(row.get("status")) for row in source_rows}),
        }
        merged_rows.append(merged)
        if status not in {"EXECUTED", "NOT_APPLICABLE"}:
            blocking.append(f"{family}: {status}")

    provider_alignment = None
    if alignment_record is not None:
        provider_alignment = dict(alignment_record)
        provider_alignment["scope"] = "first source worklist only"
        provider_alignment["facility_merge_additional_campaigns"] = max(0, len(matrices) - 1)
        provider_alignment["facility_merge_alignment_claim"] = False
        provider_alignment["interpretation"] = (
            "The retained ALIGNED record applies only to the source worklist campaign; "
            "additional namespaced diagnostic campaigns are tracked separately."
        )

    return {
        "schema_version": "prism.major_accident_scope.v1",
        "facility_id": facility_id,
        "scope": "outdoor_major_accidents",
        "required_families": list(families),
        "rows": merged_rows,
        "provider_worklist_alignment": provider_alignment,
        "source_matrices": source_records,
        "source_matrix_count": len(source_records),
        "declared_scope_numerically_complete": all(
            row["status"] in {"EXECUTED", "NOT_APPLICABLE"} for row in merged_rows
        ),
        "facility_total_risk_available": False,
        "matrix_complete": not blocking,
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "physical_validation_claim": False,
        "diagnostic_only": True,
        "interpretation": (
            "Disjoint mechanism matrices were merged by family for facility accounting. "
            "Rows remain PARTIAL/NO_EVENT_GENERATED when any supplied campaign is incomplete; "
            "family frequency rows are coverage views and must not be summed across families."
        ),
    }


__all__ = ["merge_scope_matrices"]
