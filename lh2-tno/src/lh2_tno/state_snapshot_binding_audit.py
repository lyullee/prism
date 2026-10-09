"""Audit whether equipment state snapshots survive the accident boundary.

The audit is deliberately stricter than checking a digest field.  A digest
without the canonical snapshot payload is recorded as ``DECLARED_DIGEST_ONLY``
because it cannot be independently reconstructed or reviewed.  A row is
``BOUND_AND_ECHOED`` only when the snapshot payload is present, its digest is
valid, and the provider echoes the same digest.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot

STATE_SNAPSHOT_BINDING_AUDIT_SCHEMA = "prism.state_snapshot_binding_audit.v1"


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _classify(
    *,
    source: str,
    event_id: Any,
    component_id: Any,
    request: Mapping[str, Any] | None = None,
    verification: Mapping[str, Any] | None = None,
    provider_response: Mapping[str, Any] | None = None,
    record_path: Any = None,
) -> dict[str, Any]:
    request = request or {}
    verification = verification or {}
    provider_response = provider_response or {}
    snapshot = _as_mapping(request.get("state_snapshot")) or _as_mapping(
        verification.get("state_snapshot")
    )
    declared = request.get("state_snapshot_digest")
    handoff = _as_mapping(verification.get("state_snapshot_handoff"))
    echo = (
        provider_response.get("provider_state_snapshot_digest")
        or verification.get("provider_echo_digest")
        or (handoff.get("provider_echo_digest") if handoff is not None else None)
    )
    if handoff is not None:
        snapshot_present = handoff.get("present") is True
        declared = handoff.get("digest", declared)
        echo = handoff.get("provider_echo_digest", echo)
    computed = None
    status = "UNBOUND"
    reason = "no canonical equipment state snapshot or state digest was recorded"
    if snapshot is not None:
        try:
            parsed = EquipmentStateSnapshot.from_mapping(snapshot)
            computed = parsed.digest()
        except (TypeError, ValueError) as error:
            status = "MALFORMED_SNAPSHOT"
            reason = f"canonical state snapshot failed validation: {error}"
        else:
            if declared != computed:
                status = "DIGEST_MISMATCH"
                reason = "declared state_snapshot_digest does not match the snapshot payload"
            elif echo is None:
                status = "SNAPSHOT_REQUESTED_NO_PROVIDER_ECHO"
                reason = "canonical snapshot was requested but provider echo digest is absent"
            elif not (
                echo == computed
                or (
                    isinstance(echo, Sequence)
                    and not isinstance(echo, (str, bytes))
                    and bool(echo)
                    and all(item == computed for item in echo)
                )
            ):
                status = "DIGEST_MISMATCH"
                reason = "provider echo digest does not match the canonical snapshot"
            else:
                status = "BOUND_AND_ECHOED"
                reason = "canonical snapshot was validated at the request boundary and echoed by the provider"
    elif declared is not None or verification.get("state_snapshot_digest_match") is True:
        status = "DECLARED_DIGEST_ONLY"
        reason = "a state digest or provider match flag exists without a reviewable snapshot payload"
    elif handoff is not None and handoff.get("present") is False:
        status = "UNBOUND"
        reason = "verification explicitly records that no state snapshot was present"
    return {
        "source": source,
        "record": record_path,
        "event_id": event_id,
        "component_id": component_id,
        "status": status,
        "snapshot_present": snapshot is not None,
        "snapshot_schema_version": snapshot.get("schema_version") if snapshot else None,
        "declared_digest": declared,
        "computed_digest": computed,
        "provider_echo_digest": echo,
        "digest_match": status == "BOUND_AND_ECHOED",
        "reason": reason,
    }


def _campaign_rows(campaign: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    routes = campaign.get("event_routes", [])
    if not isinstance(routes, list):
        return rows
    for route in routes:
        if not isinstance(route, Mapping):
            continue
        event_id = route.get("event_id")
        branches = route.get("branches", [])
        if not isinstance(branches, list):
            continue
        for branch in branches:
            if not isinstance(branch, Mapping):
                continue
            request = _as_mapping(branch.get("request")) or {}
            release = (
                _as_mapping(request.get("resolved_liquid_release"))
                or _as_mapping(request.get("resolved_release"))
                or _as_mapping(request.get("resolved_release_set"))
                or {}
            )
            rows.append(_classify(
                source="campaign",
                event_id=event_id or request.get("event_id"),
                component_id=request.get("component_id") or release.get("component_id"),
                request=request,
                provider_response=release,
                record_path=campaign.get("_record_path"),
            ))
    return rows


def build_state_snapshot_binding_audit(
    campaign_result: Mapping[str, Any] | None = None,
    diagnostic_records: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Return a fail-closed state handoff ledger for campaign and diagnostics."""
    rows = _campaign_rows(campaign_result) if campaign_result is not None else []
    for record in diagnostic_records:
        if not isinstance(record, Mapping):
            continue
        request = _as_mapping(record.get("request")) or {}
        provider_response = _as_mapping(record.get("provider_response")) or {}
        rows.append(_classify(
            source="diagnostic_record",
            event_id=record.get("event_id") or request.get("event_id"),
            component_id=record.get("component_id") or request.get("component_id"),
            request=request,
            verification=record,
            provider_response=provider_response,
            record_path=record.get("_record_path"),
        ))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    bound = counts.get("BOUND_AND_ECHOED", 0)
    mismatches = counts.get("DIGEST_MISMATCH", 0) + counts.get("MALFORMED_SNAPSHOT", 0)
    if not rows:
        status = "NO_STATE_SNAPSHOT_RECORDS"
    elif bound == len(rows) and mismatches == 0:
        status = "STATE_SNAPSHOT_BOUND_AND_ECHOED"
    elif bound > 0 and mismatches == 0:
        status = "PARTIAL_STATE_SNAPSHOT_BINDING"
    elif mismatches > 0:
        status = "STATE_SNAPSHOT_BINDING_ERROR"
    else:
        status = "NO_STATE_SNAPSHOT_BOUND"
    return {
        "schema_version": STATE_SNAPSHOT_BINDING_AUDIT_SCHEMA,
        "status": status,
        "policy": {
            "canonical_schema": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
            "digest_only_is_binding": False,
            "provider_echo_required": True,
            "diagnostic_only": True,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
        "record_count": len(rows),
        "bound_count": bound,
        "echo_match_count": bound,
        "digest_mismatch_count": mismatches,
        "declared_digest_only_count": counts.get("DECLARED_DIGEST_ONLY", 0),
        "unbound_count": counts.get("UNBOUND", 0),
        "snapshot_requested_no_echo_count": counts.get("SNAPSHOT_REQUESTED_NO_PROVIDER_ECHO", 0),
        "status_counts": counts,
        "rows": rows,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "Only a validated canonical equipment state payload with a matching provider echo "
            "counts as bound. This ledger does not qualify the model, assign frequency, or promote facility risk."
        ),
    }


__all__ = [
    "STATE_SNAPSHOT_BINDING_AUDIT_SCHEMA",
    "build_state_snapshot_binding_audit",
]
