"""Fail-closed audit for HAZOP scenario identity through facility accounting.

The campaign and facility ledgers may contain both generic realtime rows and
HAZOP-bound rows.  This audit does not infer a missing scenario ID.  It only
confirms that an explicitly supplied ``hazop_scenario_id`` is preserved across
events, cases, risk atoms, and provider evidence requests.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.hazop_scenario_trace_audit.v1"


def _rows(value: Any, key: str) -> list[Mapping[str, Any]]:
    rows = value.get(key, ()) if isinstance(value, Mapping) else ()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _campaign_payload(campaign_result: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = campaign_result.get("campaign")
    if isinstance(nested, Mapping):
        return nested
    return campaign_result


def audit_hazop_scenario_trace(
    campaign_result: Mapping[str, Any],
    *,
    facility_evidence_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit explicit HAZOP scenario IDs without promoting any QRA claim."""
    if not isinstance(campaign_result, Mapping):
        raise TypeError("campaign_result must be a mapping")
    campaign = _campaign_payload(campaign_result)
    events = _rows(campaign, "events")
    cases = _rows(campaign, "cases")
    atoms = _rows(campaign, "risk_atoms")
    event_scenario: dict[str, str | None] = {}
    errors: list[str] = []
    hazop_expected = (
        str(campaign_result.get("schema_version", "")).startswith("prism.hazop_")
        or str(campaign.get("schema_version", "")).startswith("prism.hazop_")
        or str(campaign_result.get("status", "")).startswith("HAZOP_")
    )

    for index, event in enumerate(events):
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            errors.append(f"events[{index}] has no event id")
            continue
        event_id = event_id.strip()
        scenario_id = event.get("hazop_scenario_id")
        if scenario_id is not None:
            if not isinstance(scenario_id, str) or not scenario_id.strip():
                errors.append(f"event {event_id} has an invalid hazop_scenario_id")
                scenario_id = None
            else:
                scenario_id = scenario_id.strip()
        previous = event_scenario.get(event_id, "__missing__")
        if previous != "__missing__" and previous != scenario_id:
            errors.append(f"event {event_id} has conflicting HAZOP scenario IDs")
        event_scenario[event_id] = scenario_id

    traceable_case_count = 0
    traceable_atom_count = 0
    for label, rows, counter_name in (
        ("case", cases, "case"),
        ("risk atom", atoms, "atom"),
    ):
        for index, row in enumerate(rows):
            event_id = row.get("event_id")
            scenario_id = row.get("hazop_scenario_id")
            expected = event_scenario.get(event_id) if isinstance(event_id, str) else None
            if scenario_id is not None:
                if not isinstance(scenario_id, str) or not scenario_id.strip():
                    errors.append(f"{label}s[{index}] has an invalid hazop_scenario_id")
                elif expected is None:
                    errors.append(
                        f"{label}s[{index}] declares HAZOP scenario {scenario_id!r} without a matching event"
                    )
                elif scenario_id.strip() != expected:
                    errors.append(
                        f"{label} {event_id} HAZOP scenario ID does not match event identity"
                    )
                else:
                    if counter_name == "case":
                        traceable_case_count += 1
                    else:
                        traceable_atom_count += 1
            elif hazop_expected and expected is not None:
                errors.append(f"{label} {event_id} dropped the event HAZOP scenario ID")

    request_count = 0
    traceable_request_count = 0
    if facility_evidence_request is not None:
        request_rows = _rows(facility_evidence_request, "case_requests")
        request_count = len(request_rows)
        for index, request in enumerate(request_rows):
            event_id = request.get("event_id")
            expected = event_scenario.get(event_id) if isinstance(event_id, str) else None
            request_id = request.get("hazop_scenario_id")
            exact = request.get("exact_match_required")
            exact_id = exact.get("hazop_scenario_id") if isinstance(exact, Mapping) else None
            if expected is not None:
                if request_id != expected or exact_id != expected:
                    errors.append(
                        f"provider request {index} does not preserve event {event_id} HAZOP scenario ID"
                    )
                else:
                    traceable_request_count += 1
            elif request_id is not None or exact_id is not None:
                errors.append(
                    f"provider request {index} declares a HAZOP scenario without a matching event"
                )

    traceable_event_count = sum(value is not None for value in event_scenario.values())
    if errors:
        status = "HAZOP_SCENARIO_TRACE_BLOCKED"
    elif hazop_expected and traceable_event_count:
        status = "HAZOP_SCENARIO_TRACE_COMPLETE"
    else:
        status = "NO_HAZOP_SCENARIO_ID_DECLARED"
    return {
        "schema_version": SCHEMA,
        "status": status,
        "event_count": len(event_scenario),
        "traceable_event_count": traceable_event_count,
        "traceable_case_count": traceable_case_count,
        "traceable_risk_atom_count": traceable_atom_count,
        "provider_request_count": request_count,
        "traceable_provider_request_count": traceable_request_count,
        "errors": errors,
        "policy": {
            "hazop_scenario_id_inferred": False,
            "frequency_inference_performed": False,
            "facility_qra_promotion": False,
            "physical_validation_claim": False,
        },
        "interpretation": (
            "Explicit HAZOP scenario identity is preserved through the facility boundary."
            if status == "HAZOP_SCENARIO_TRACE_COMPLETE"
            else "Missing or conflicting identity remains fail-closed; no scenario or frequency is inferred."
        ),
    }


__all__ = ["SCHEMA", "audit_hazop_scenario_trace"]
