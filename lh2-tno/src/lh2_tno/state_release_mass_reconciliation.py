"""Reconcile legacy state-to-release mass mismatches with explicit rebaselines.

The authoritative campaign must not be silently rewritten when an external
equipment model is re-exported from a different initialization.  This helper
links a legacy mismatch to a separately recorded provider-state rebaseline and
reports whether the new packet closes the numeric boundary.  It never replaces
the authoritative campaign and never promotes a provider or facility QRA.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


RECONCILIATION_SCHEMA = "prism.state_release_mass_reconciliation.v1"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None


def _close(left: Any, right: Any, *, rel_tol: float, abs_tol: float) -> bool:
    a = _number(left)
    b = _number(right)
    return a is not None and b is not None and math.isclose(
        a, b, rel_tol=rel_tol, abs_tol=abs_tol
    )


def build_state_release_mass_reconciliation(
    authoritative_audit: Mapping[str, Any],
    rebaseline_records: Sequence[Mapping[str, Any]],
    *,
    relative_tolerance: float = 1e-6,
    absolute_tolerance: float = 1e-9,
) -> dict[str, Any]:
    """Return an explicit, diagnostic-only reconciliation ledger."""

    if relative_tolerance < 0.0 or not math.isfinite(relative_tolerance):
        raise ValueError("relative_tolerance must be finite and non-negative")
    if absolute_tolerance < 0.0 or not math.isfinite(absolute_tolerance):
        raise ValueError("absolute_tolerance must be finite and non-negative")
    rows = authoritative_audit.get("mismatch_rows")
    if not isinstance(rows, list):
        raise ValueError("authoritative_audit.mismatch_rows must be a list")
    records_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for record in rebaseline_records:
        if not isinstance(record, Mapping):
            raise ValueError("rebaseline records must contain objects")
        event_id = record.get("event_id")
        if isinstance(event_id, str) and event_id:
            records_by_event.setdefault(event_id, []).append(record)

    reconciliation_rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("authoritative mismatch rows must contain objects")
        event_id = row.get("event_id") or row.get("case_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("authoritative mismatch row lacks event_id/case_id")
        candidates = records_by_event.get(event_id, [])
        matched = None
        for candidate in candidates:
            if (
                _close(
                    candidate.get("state_snapshot_previous_mass_kg"),
                    row.get("state_mass_kg"),
                    rel_tol=relative_tolerance,
                    abs_tol=absolute_tolerance,
                )
                and candidate.get("state_snapshot_release_mass_match") is True
                and _close(
                    candidate.get("state_snapshot_provider_mass_kg"),
                    candidate.get("provider_available_mass_kg"),
                    rel_tol=relative_tolerance,
                    abs_tol=absolute_tolerance,
                )
            ):
                matched = candidate
                break
        resolved = matched is not None
        if not resolved:
            unresolved.append(event_id)
        reconciliation_rows.append({
            "event_id": event_id,
            "authoritative_state_mass_kg": row.get("state_mass_kg"),
            "authoritative_provider_initial_mass_kg": row.get("provider_initial_mass_kg"),
            "legacy_relative_difference": row.get("relative_difference"),
            "rebaseline_found": resolved,
            "rebaseline_previous_mass_kg": (
                matched.get("state_snapshot_previous_mass_kg") if matched else None
            ),
            "rebaseline_provider_mass_kg": (
                matched.get("state_snapshot_provider_mass_kg") if matched else None
            ),
            "rebaseline_provider_result_digest": (
                matched.get("provider_result_digest") if matched else None
            ),
            "status": "RESOLVED_BY_EXPLICIT_REBASELINE" if resolved else "OPEN",
        })

    status = (
        "MASS_STATE_CONSISTENCY_RECONCILED_DIAGNOSTIC_ONLY"
        if rows and not unresolved
        else "MASS_STATE_CONSISTENCY_REVIEW_REQUIRED"
        if unresolved
        else "MASS_STATE_CONSISTENCY_NO_LEGACY_MISMATCH"
    )
    return {
        "schema_version": RECONCILIATION_SCHEMA,
        "status": status,
        "authoritative_audit_status": authoritative_audit.get("status"),
        "authoritative_audit_case_count": authoritative_audit.get("case_count"),
        "authoritative_mismatch_count": len(rows),
        "rebaseline_record_count": len(rebaseline_records),
        "resolved_mismatch_count": len(rows) - len(unresolved),
        "unresolved_mismatch_count": len(unresolved),
        "unresolved_event_ids": unresolved,
        "rows": reconciliation_rows,
        "authoritative_campaign_replaced": False,
        "provider_packet_promoted": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "promotion_allowed": False,
        "interpretation": (
            "A resolved row has an explicit provider-state rebaseline whose previous mass "
            "matches the authoritative mismatch and whose new snapshot matches its provider. "
            "The authoritative campaign remains unchanged until a full catalog rebaseline "
            "is reviewed and rebound."
        ),
    }


__all__ = [
    "RECONCILIATION_SCHEMA",
    "build_state_release_mass_reconciliation",
]
