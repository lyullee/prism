"""Audit explicit observed-state to provider-release component bindings.

Observed telemetry is useful for calibrating a digital twin, but it is not an
accident source.  This module requires an explicit reviewed mapping from an
observed component and source stream to a PRISM facility component and one or
more accepted provider events.  It reports the missing link without creating
an accident, frequency, release duration, or facility QRA result.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.observed_state_release_binding_audit.v1"
MANIFEST_SCHEMA = "prism.observed_state_release_binding_manifest.v1"


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        result.append(row)
    return result


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    values = [str(item).strip() for item in value]
    if any(not item for item in values):
        raise ValueError(f"{label} cannot contain empty values")
    return values


def audit_observed_state_release_binding(
    observed_state_evidence: Mapping[str, Any],
    provider_packet_input_audit: Mapping[str, Any],
    binding_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed binding report for observed state and releases."""
    if not isinstance(observed_state_evidence, Mapping):
        raise ValueError("observed_state_evidence must be an object")
    if not isinstance(provider_packet_input_audit, Mapping):
        raise ValueError("provider_packet_input_audit must be an object")
    if not isinstance(binding_manifest, Mapping):
        raise ValueError("binding_manifest must be an object")
    if binding_manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"binding manifest schema_version must be {MANIFEST_SCHEMA}")

    source_rows = _rows(observed_state_evidence.get("source_rows", []), "observed_state_evidence.source_rows")
    observed_components: dict[str, dict[str, Any]] = {}
    observed_sources: dict[str, str] = {}
    for row in source_rows:
        component_id = str(row.get("component_id") or "").strip()
        source_id = str(row.get("source_id") or "").strip()
        if not component_id or not source_id:
            raise ValueError("observed source rows require component_id and source_id")
        if source_id in observed_sources:
            raise ValueError(f"observed source_id is duplicated: {source_id}")
        observed_sources[source_id] = component_id
        observed_components.setdefault(component_id, {"source_ids": [], "sample_count": 0})
        observed_components[component_id]["source_ids"].append(source_id)
        observed_components[component_id]["sample_count"] += int(row.get("sample_count") or 0)

    accepted_evidence = provider_packet_input_audit.get("provider_packet_evidence", [])
    accepted_rows = _rows(accepted_evidence, "provider_packet_input_audit.provider_packet_evidence")
    provider_by_event: dict[str, Mapping[str, Any]] = {}
    for row in accepted_rows:
        event_id = str(row.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("accepted provider evidence requires event_id")
        if event_id in provider_by_event:
            # Distinct branch packets may share an event ID.  Keep the first
            # row for component checking and count all rows in the report.
            continue
        provider_by_event[event_id] = row

    bindings = _rows(binding_manifest.get("bindings", []), "binding_manifest.bindings")
    seen_observed: set[str] = set()
    rows: list[dict[str, Any]] = []
    matched_components: set[str] = set()
    bound_events: set[str] = set()
    for index, binding in enumerate(bindings):
        observed_component_id = str(binding.get("observed_component_id") or "").strip()
        facility_component_id = str(binding.get("facility_component_id") or "").strip()
        binding_id = str(binding.get("binding_id") or f"binding-{index + 1}")
        reasons: list[str] = []
        if not observed_component_id or not facility_component_id:
            reasons.append("observed_component_id and facility_component_id are required")
        source_ids = _string_list(binding.get("source_ids", []), f"binding {binding_id}.source_ids")
        event_ids = _string_list(binding.get("provider_event_ids", []), f"binding {binding_id}.provider_event_ids")
        observed = observed_components.get(observed_component_id)
        if observed is None:
            reasons.append("observed component is not present in the evidence ledger")
        else:
            missing_sources = sorted(set(source_ids) - set(observed["source_ids"]))
            if missing_sources:
                reasons.append(f"source_ids are not owned by observed component: {missing_sources}")
        if binding.get("review_status") not in {"reviewed", "field_confirmed"}:
            reasons.append("binding review_status must be reviewed or field_confirmed")
        event_rows: list[Mapping[str, Any]] = []
        for event_id in event_ids:
            provider = provider_by_event.get(event_id)
            if provider is None:
                reasons.append(f"no accepted provider packet has event_id {event_id}")
                continue
            event_rows.append(provider)
            if provider.get("component_id") != facility_component_id:
                reasons.append(f"provider event {event_id} component_id disagrees with binding")
        if not event_ids:
            reasons.append("at least one provider_event_id is required to bind state to release")
        if reasons:
            status = "STATE_MAPPING_UNQUALIFIED"
        elif observed_component_id in seen_observed:
            status = "STATE_MAPPING_DUPLICATE"
            reasons.append("observed component has more than one binding row")
        else:
            status = "STATE_AND_PROVIDER_RELEASE_BOUND"
            seen_observed.add(observed_component_id)
            matched_components.add(observed_component_id)
            bound_events.update(event_ids)
        rows.append({
            "binding_id": binding_id,
            "observed_component_id": observed_component_id,
            "facility_component_id": facility_component_id,
            "source_ids": source_ids,
            "provider_event_ids": event_ids,
            "provider_event_count_found": len(event_rows),
            "status": status,
            "blocking_reasons": list(dict.fromkeys(reasons)),
        })

    for component_id, observed in sorted(observed_components.items()):
        if component_id in matched_components:
            continue
        rows.append({
            "binding_id": None,
            "observed_component_id": component_id,
            "facility_component_id": None,
            "source_ids": list(observed["source_ids"]),
            "provider_event_ids": [],
            "provider_event_count_found": 0,
            "status": "UNMAPPED_OBSERVED_COMPONENT",
            "blocking_reasons": [
                "no reviewed state-to-facility-component/provider-event binding exists"
            ],
        })

    unbound_components = sorted(set(observed_components) - matched_components)
    blocking_reasons: list[str] = []
    if unbound_components:
        blocking_reasons.append(
            f"{len(unbound_components)} observed component(s) are not bound to a provider release"
        )
    if not accepted_rows:
        blocking_reasons.append("provider packet input audit contains no accepted provider evidence")
    if not bindings:
        blocking_reasons.append("binding manifest contains no reviewed bindings")
    if matched_components and not unbound_components and not blocking_reasons:
        status = "STATE_AND_PROVIDER_RELEASE_BOUND_DIAGNOSTIC"
    elif matched_components:
        status = "PARTIAL_STATE_TO_RELEASE_BINDING"
    else:
        status = "NO_STATE_TO_RELEASE_BINDING"
    return {
        "schema": SCHEMA,
        "status": status,
        "observed_state_status": observed_state_evidence.get("status"),
        "observed_component_count": len(observed_components),
        "mapped_component_count": len(matched_components),
        "unmapped_component_count": len(unbound_components),
        "provider_packet_evidence_count": len(accepted_rows),
        "bound_provider_event_count": len(bound_events),
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "policy": {
            "state_data_are_not_accident_sources": True,
            "frequency_is_not_assigned": True,
            "provider_packet_promotion_is_not_created": True,
            "facility_ir_fn_promotion": "requires qualified case coverage and independent validation gates",
            "diagnostic_only": True,
        },
    }


__all__ = ["MANIFEST_SCHEMA", "SCHEMA", "audit_observed_state_release_binding"]
