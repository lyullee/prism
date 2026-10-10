"""Bind verified equipment-state snapshots into an existing campaign result.

Native LH2 packet generation stores the canonical state snapshot on the
request.  Some historical result ledgers were produced before that field was
copied into their compact provider identity.  This module repairs that
serialization boundary only when the request and the state-binding audit
agree on event, component, provider-result digest and snapshot digest.

It never reconstructs a state from release values.  Missing or ambiguous
identity is an error when a complete binding is requested.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from .state_snapshot import EquipmentStateSnapshot


def _sequence(value: Any) -> tuple[Any, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(value)


def _provider_result_digests(request: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("resolved_release", "resolved_liquid_release"):
        release = request.get(key)
        if isinstance(release, Mapping) and isinstance(
            release.get("provider_result_digest"), str
        ):
            values.append(str(release["provider_result_digest"]))
    release_set = request.get("resolved_release_set")
    if isinstance(release_set, Mapping):
        releases = release_set.get("releases")
        if not isinstance(releases, Sequence) or isinstance(releases, (str, bytes)):
            raise ValueError("resolved_release_set.releases must be an array")
        for release in releases:
            if isinstance(release, Mapping) and isinstance(
                release.get("provider_result_digest"), str
            ):
                values.append(str(release["provider_result_digest"]))
    if not values:
        raise ValueError("state-bound request has no provider result digest")
    return tuple(values)


def _request_branches(campaign: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    routes = campaign.get("event_routes")
    if not isinstance(routes, list):
        raise ValueError("campaign.event_routes must be an array")
    index: dict[str, list[Mapping[str, Any]]] = {}
    for route in routes:
        if not isinstance(route, Mapping) or not isinstance(route.get("event_id"), str):
            raise ValueError("every campaign route must contain event_id")
        branches = route.get("branches")
        if not isinstance(branches, list):
            raise ValueError(f"route branches must be an array: {route['event_id']}")
        requests = [
            branch.get("request")
            for branch in branches
            if isinstance(branch, Mapping) and isinstance(branch.get("request"), Mapping)
        ]
        index[str(route["event_id"])] = [request for request in requests if request is not None]
    return index


def _audit_rows(audit: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    rows = audit.get("rows")
    if not isinstance(rows, list):
        raise ValueError("state snapshot audit rows must be an array")
    index: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("event_id"), str):
            raise ValueError("state snapshot audit rows must contain event_id")
        index.setdefault(str(row["event_id"]), []).append(row)
    return index


def _snapshot_for_identity(
    *,
    event_id: str,
    identity: Mapping[str, Any],
    requests: Sequence[Mapping[str, Any]],
    audit_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    component_id = identity.get("component_id")
    result_digests = tuple(str(value) for value in _sequence(identity.get("provider_result_digests")))
    if not isinstance(component_id, str) or not component_id.strip():
        raise ValueError(f"{event_id}: provider identity has no component_id")
    if not result_digests:
        raise ValueError(f"{event_id}: provider identity has no provider_result_digests")

    candidates: list[Mapping[str, Any]] = []
    for request in requests:
        if request.get("component_id") != component_id:
            continue
        try:
            request_digests = _provider_result_digests(request)
        except ValueError:
            continue
        if request_digests == result_digests:
            candidates.append(request)
    if len(candidates) != 1:
        raise ValueError(
            f"{event_id}: expected one exact state-bound request for component/digests; "
            f"found {len(candidates)}"
        )
    request = candidates[0]
    raw_snapshot = request.get("state_snapshot")
    if not isinstance(raw_snapshot, Mapping):
        raise ValueError(f"{event_id}: exact request has no canonical state_snapshot")
    snapshot = EquipmentStateSnapshot.from_mapping(raw_snapshot)
    digest = snapshot.digest()
    declared_digest = request.get("state_snapshot_digest")
    provider_digest = request.get("provider_state_snapshot_digest")
    if declared_digest != digest or provider_digest != digest:
        raise ValueError(f"{event_id}: request state snapshot digest does not close")
    provider_digests = request.get("provider_state_snapshot_digests")
    if provider_digests is not None:
        provider_digests = tuple(str(value) for value in _sequence(provider_digests))
        if not provider_digests or any(value != digest for value in provider_digests):
            raise ValueError(f"{event_id}: provider state snapshot digest list does not close")

    matching_audit = [
        row
        for row in audit_rows
        if row.get("status") == "BOUND_AND_ECHOED"
        and row.get("component_id") == component_id
        and row.get("declared_digest") == digest
        and (
            row.get("provider_result_digest") is None
            and len(result_digests) > 1
            or row.get("provider_result_digest") in result_digests
        )
    ]
    if len(matching_audit) != 1:
        raise ValueError(
            f"{event_id}: expected one exact BOUND_AND_ECHOED audit row; "
            f"found {len(matching_audit)}"
        )
    result: dict[str, Any] = {
        "state_snapshot": snapshot.to_mapping(),
        "state_snapshot_digest": digest,
        "provider_state_snapshot_digest": digest,
    }
    if provider_digests is not None and len(provider_digests) > 1:
        result["provider_state_snapshot_digests"] = list(provider_digests)
    return result


def bind_campaign_result_state_snapshots(
    result: Mapping[str, Any],
    campaign: Mapping[str, Any],
    state_snapshot_audit: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a result with exact audited state identities copied into rows."""
    if not isinstance(result, Mapping) or not isinstance(campaign, Mapping):
        raise ValueError("result and campaign must be mappings")
    if not isinstance(state_snapshot_audit, Mapping):
        raise ValueError("state_snapshot_audit must be a mapping")
    if state_snapshot_audit.get("status") != "STATE_SNAPSHOT_BOUND_AND_ECHOED":
        raise ValueError("state snapshot audit is not BOUND_AND_ECHOED")
    routes = _request_branches(campaign)
    audit = _audit_rows(state_snapshot_audit)
    output = deepcopy(dict(result))
    bound_cases = 0
    bound_atoms = 0
    bound_events: set[str] = set()
    missing: list[str] = []

    def bind_rows(key: str, *, atom_rows: bool) -> None:
        nonlocal bound_cases, bound_atoms
        rows = output.get(key, [])
        if not isinstance(rows, list):
            raise ValueError(f"result.{key} must be an array")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"result.{key} rows must be objects")
            identity = row.get("provider_packet_identity")
            event_id = row.get("event_id")
            if not isinstance(identity, Mapping) or not isinstance(event_id, str):
                continue
            candidates = routes.get(event_id, [])
            audit_candidates = audit.get(event_id, [])
            if not candidates or not audit_candidates:
                missing.append(str(event_id))
                continue
            patch = _snapshot_for_identity(
                event_id=event_id,
                identity=identity,
                requests=candidates,
                audit_rows=audit_candidates,
            )
            identity.update(patch)
            bound_events.add(event_id)
            if atom_rows:
                bound_atoms += 1
            else:
                bound_cases += 1

    bind_rows("cases", atom_rows=False)
    bind_rows("uncomputed_cases", atom_rows=False)
    bind_rows("risk_atoms", atom_rows=True)
    if missing:
        raise ValueError(
            "state snapshot result binding lacks exact audited identity for event(s): "
            + ", ".join(sorted(set(missing)))
        )
    expected_events = set(routes)
    if bound_events != expected_events:
        raise ValueError(
            "state snapshot result binding did not cover every campaign event: "
            f"{len(bound_events)}/{len(expected_events)}"
        )
    report = {
        "schema_version": "prism.state_snapshot_result_binding.v1",
        "status": "STATE_SNAPSHOT_RESULT_BOUND_AND_ECHOED",
        "event_count": len(bound_events),
        "bound_case_count": bound_cases,
        "bound_risk_atom_count": bound_atoms,
        "audit_event_count": len(audit),
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "Exact canonical equipment-state snapshots were copied from state-bound campaign "
            "requests into compact result identities after provider echo audit. No state was "
            "reconstructed from release values."
        ),
    }
    return output, report


__all__ = ["bind_campaign_result_state_snapshots"]
