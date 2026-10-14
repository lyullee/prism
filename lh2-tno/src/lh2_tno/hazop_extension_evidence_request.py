"""Create an explicit evidence request for HAZOP-unbound extension events.

The request is intentionally administrative: it never fills an operating mode,
creates a scenario, assigns a frequency, or launches a provider calculation.
It turns a fail-closed HAZOP selection audit into a row-by-row list of inputs
needed before a namespaced extension can enter the live QRA path.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.hazop_extension_mode_binding_evidence_request.v1"
SELECTION_SCHEMA = "prism.hazop_event_selection_binding_audit.v1"


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def build_hazop_extension_mode_binding_request(
    selection_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed request for every unbound frequency event."""

    if selection_audit.get("schema_version") != SELECTION_SCHEMA:
        raise ValueError(f"selection_audit must be {SELECTION_SCHEMA}")
    event_rows = _rows(selection_audit.get("event_rows"), "selection_audit.event_rows")
    unbound = [row for row in event_rows if row.get("status") != "BOUND"]
    requests: list[dict[str, Any]] = []
    for row in unbound:
        event_id = str(row.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("unbound HAZOP event row has no event_id")
        requests.append(
            {
                "event_id": event_id,
                "component_id": row.get("frequency_event_component_id"),
                "release_mode": row.get("frequency_event_release_mode"),
                "scenario_families": list(row.get("scenario_families") or []),
                "status": "OPEN",
                "required_evidence": [
                    "operating_mode from the runtime input frame",
                    "reviewed HAZOP scenario ID and deviation/guideword",
                    "P&ID or equipment tag identifying the affected boundary",
                    "source frame digest and effective timestamp",
                    "reviewer/source provenance for the mode-to-scenario decision",
                ],
                "policy": {
                    "operating_mode_inferred": False,
                    "scenario_inferred": False,
                    "frequency_assignment_performed": False,
                    "provider_release_created": False,
                    "facility_qra_claim": False,
                },
            }
        )
    status = "OPEN_HAZOP_EXTENSION_MODE_EVIDENCE" if requests else "NO_HAZOP_EXTENSION_MODE_GAP"
    return {
        "schema_version": SCHEMA,
        "status": status,
        "source_selection_audit_schema": selection_audit.get("schema_version"),
        "source_selection_audit_status": selection_audit.get("status"),
        "source_frequency_event_count": selection_audit.get("frequency_event_count"),
        "source_bound_event_count": selection_audit.get("bound_event_count"),
        "source_unbound_event_count": selection_audit.get("unbound_event_count"),
        "request_count": len(requests),
        "requests": requests,
        "mode_inference_performed": False,
        "scenario_inference_performed": False,
        "frequency_assignment_performed": False,
        "provider_release_created": False,
        "facility_qra_claim": False,
        "interpretation": (
            "Every HAZOP-unbound extension event remains excluded from automatic scenario "
            "selection until an explicit operating mode and reviewed HAZOP identity are supplied."
        ),
    }


__all__ = ["SCHEMA", "SELECTION_SCHEMA", "build_hazop_extension_mode_binding_request"]
