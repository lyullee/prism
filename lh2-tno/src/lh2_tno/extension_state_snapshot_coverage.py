"""Audit state-snapshot coverage for non-native extension campaigns.

The native 24-event campaign has a canonical ``EquipmentStateSnapshot``
ledger.  The vertical-handoff and inventory-depletion campaigns are separate
diagnostic extensions and historically carried release/provider fields only.
This module makes that evidence gap explicit on an event-by-event basis.  It
intentionally never reconstructs an equipment state from release mass, flow,
pressure, or a result digest.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


EXTENSION_STATE_SNAPSHOT_COVERAGE_SCHEMA = "prism.extension_state_snapshot_coverage.v1"


def _record_path(value: Mapping[str, Any] | None) -> str | None:
    if isinstance(value, Mapping) and isinstance(value.get("_record_path"), str):
        return value["_record_path"]
    return None


def _case_identity_rows(result: Mapping[str, Any], event_id: str) -> list[Mapping[str, Any]]:
    cases = result.get("cases", [])
    if not isinstance(cases, list):
        return []
    return [
        row
        for row in cases
        if isinstance(row, Mapping) and str(row.get("event_id", "")) == event_id
    ]


def _identity_summary(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    identities = [
        row.get("provider_packet_identity")
        for row in cases
        if isinstance(row.get("provider_packet_identity"), Mapping)
    ]
    component_ids = sorted({
        str(identity.get("component_id"))
        for identity in identities
        if identity.get("component_id")
    })
    source_digests = sorted({
        str(digest)
        for identity in identities
        for digest in (identity.get("provider_source_digests") or [])
        if digest
    })
    result_digests = sorted({
        str(digest)
        for identity in identities
        for digest in (identity.get("provider_result_digests") or [])
        if digest
    })
    return {
        "provider_packet_identity_present": bool(identities),
        "provider_packet_identity_count": len(identities),
        "provider_component_ids": component_ids,
        "provider_source_digests": source_digests,
        "provider_result_digests": result_digests,
    }


def _event_rows(
    result: Mapping[str, Any],
    *,
    source_family: str,
    state_rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    events = result.get("events", [])
    if not isinstance(events, list):
        return []
    rows: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping) or not event.get("id"):
            continue
        event_id = str(event["id"])
        cases = _case_identity_rows(result, event_id)
        identity = _identity_summary(cases)
        state = state_rows.get(event_id)
        if state is None:
            status = "UNBOUND"
            reason = (
                "no canonical EquipmentStateSnapshot record exists for this extension event; "
                "release values and result digests are not used to reconstruct equipment state"
            )
            state_path = None
        else:
            status = str(state.get("status", "UNBOUND"))
            reason = str(state.get("reason") or "state snapshot audit supplied no reason")
            state_path = state.get("record")
        if not identity["provider_packet_identity_present"]:
            reason += "; extension result has no provider_packet_identity/provider state handoff"
        rows.append({
            "source_family": source_family,
            "source_record": _record_path(result),
            "state_snapshot_record": state_path,
            "event_id": event_id,
            "component_id": event.get("model_component_id") or event.get("component_id"),
            "status": status,
            "snapshot_bound": status == "BOUND_AND_ECHOED",
            "provider_identity": identity,
            "reason": reason,
            "policy": "release_boundary_is_not_a_state_snapshot",
        })
    return rows


def build_extension_state_snapshot_coverage(
    *,
    extension_results: Mapping[str, Mapping[str, Any]],
    state_snapshot_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an explicit event-level ledger for extension state coverage.

    ``extension_results`` maps a stable family label (for example
    ``vertical_handoff``) to a rebound campaign result.  An optional audit may
    contain canonical state rows keyed by event ID when a future provider
    export supplies them.
    """
    state_rows: dict[str, Mapping[str, Any]] = {}
    if isinstance(state_snapshot_audit, Mapping):
        raw_rows = state_snapshot_audit.get("rows", [])
        if isinstance(raw_rows, list):
            for row in raw_rows:
                if isinstance(row, Mapping) and row.get("event_id"):
                    state_rows[str(row["event_id"])] = row

    rows: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    for source_family, result in extension_results.items():
        if not isinstance(result, Mapping):
            continue
        family_rows = _event_rows(
            result,
            source_family=str(source_family),
            state_rows=state_rows,
        )
        rows.extend(family_rows)
        source_counts[str(source_family)] = len(family_rows)

    bound_rows = [row for row in rows if row["snapshot_bound"]]
    unbound_rows = [row for row in rows if not row["snapshot_bound"]]
    identity_missing = [
        row["event_id"]
        for row in rows
        if not row["provider_identity"]["provider_packet_identity_present"]
    ]
    status = (
        "EXTENSION_STATE_SNAPSHOT_COVERAGE_COMPLETE"
        if rows and len(bound_rows) == len(rows)
        else "EXTENSION_STATE_SNAPSHOT_COVERAGE_INCOMPLETE"
        if rows
        else "NO_EXTENSION_EVENTS"
    )
    return {
        "schema_version": EXTENSION_STATE_SNAPSHOT_COVERAGE_SCHEMA,
        "status": status,
        "policy": {
            "canonical_state_required": True,
            "provider_echo_required": True,
            "release_values_may_reconstruct_state": False,
            "result_digest_may_reconstruct_state": False,
            "diagnostic_only": True,
            "facility_qra_claim": False,
        },
        "source_families": source_counts,
        "event_count": len(rows),
        "bound_event_count": len(bound_rows),
        "unbound_event_count": len(unbound_rows),
        "provider_identity_missing_event_count": len(identity_missing),
        "provider_identity_missing_event_ids": identity_missing,
        "missing_event_ids": [row["event_id"] for row in unbound_rows],
        "rows": rows,
        "source_record_paths": {
            str(source_family): _record_path(result)
            for source_family, result in extension_results.items()
            if isinstance(result, Mapping)
        },
        "state_snapshot_audit_record_path": _record_path(state_snapshot_audit),
        "interpretation": (
            "Extension events remain unbound until a canonical EquipmentStateSnapshot payload "
            "is supplied and echoed by the provider. A release boundary, flow history, or result "
            "digest is evidence of the release calculation only and cannot be promoted to state."
        ),
    }


__all__ = [
    "EXTENSION_STATE_SNAPSHOT_COVERAGE_SCHEMA",
    "build_extension_state_snapshot_coverage",
]
