"""Explicitly rebaseline a provider qualification request to a new packet.

Provider qualification requests are identity- and digest-bound.  When an
external model is re-exported, its source or result digest can change even
when the event identity and physical fields are unchanged.  This module
records that change only after an explicit acknowledgement.  It never creates
qualification evidence and never opens a frequency or facility-QRA gate.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "prism.provider_qualification_request_rebaseline.v1"
REQUEST_SCHEMA = "prism.native_full_scope_provider_qualification_requests.v1"
_DIGEST = re.compile(r"^[0-9a-fA-F]{64}$")


class ProviderRequestRebaselineError(ValueError):
    """Raised when a provider request cannot be safely rebaselined."""


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    try:
        import json

        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ProviderRequestRebaselineError(f"invalid JSON: {source}") from error
    if not isinstance(value, Mapping):
        raise ProviderRequestRebaselineError("JSON value must be an object")
    return dict(value)


def _digest(value: Any, field: str) -> str:
    text = str(value or "")
    if not _DIGEST.fullmatch(text):
        raise ProviderRequestRebaselineError(f"{field} must be a 64-character SHA-256 digest")
    return text.lower()


def _current_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "event_id",
        "component_id",
        "port_id",
        "event_kind",
        "input_origin",
        "termination_basis",
        "termination_provenance",
        "duration_s",
        "available_mass_kg",
        "cumulative_mass_out_kg",
        "provider_source_digest",
        "provider_result_digest",
    )
    missing = [key for key in required if key not in packet]
    if missing:
        raise ProviderRequestRebaselineError(
            "current packet is missing required fields: " + ", ".join(missing)
        )
    result = {key: copy.deepcopy(packet[key]) for key in required}
    result["provider_source_digest"] = _digest(
        packet["provider_source_digest"], "provider_source_digest"
    )
    result["provider_result_digest"] = _digest(
        packet["provider_result_digest"], "provider_result_digest"
    )
    return result


def _find_request(catalog: Mapping[str, Any], event_id: str) -> tuple[int, int, dict[str, Any]]:
    rows = catalog.get("requests")
    if not isinstance(rows, list):
        raise ProviderRequestRebaselineError("catalog.requests must be a list")
    matches: list[tuple[int, int, dict[str, Any]]] = []
    for row_index, row_value in enumerate(rows):
        if not isinstance(row_value, Mapping) or row_value.get("event_id") != event_id:
            continue
        requests = row_value.get("requests")
        if not isinstance(requests, list):
            continue
        for request_index, request_value in enumerate(requests):
            if isinstance(request_value, Mapping) and request_value.get("request_id") == event_id:
                matches.append((row_index, request_index, dict(request_value)))
    if len(matches) != 1:
        raise ProviderRequestRebaselineError(
            f"event_id must identify exactly one nested request: {event_id!r}; found {len(matches)}"
        )
    return matches[0]


def rebaseline_provider_request_catalog(
    catalog: Mapping[str, Any] | str | Path,
    current_packet: Mapping[str, Any] | str | Path,
    *,
    event_id: str,
    acknowledged: bool = False,
    additional_blockers: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return a copy of a request catalog bound to ``current_packet``.

    ``acknowledged`` is mandatory so a caller cannot silently erase digest
    drift.  The old request and old packet digests are retained under
    ``rebaseline.previous_request``.  The output remains open and diagnostic;
    a qualification sidecar is never synthesized.
    """
    if not acknowledged:
        raise ProviderRequestRebaselineError(
            "explicit acknowledgement is required to rebaseline provider request digests"
        )
    if isinstance(catalog, (str, Path)):
        source_catalog = _read_json(catalog)
        catalog_source = str(Path(catalog).resolve())
    else:
        source_catalog = dict(catalog)
        catalog_source = None
    if source_catalog.get("schema_version") != REQUEST_SCHEMA:
        raise ProviderRequestRebaselineError(
            f"unsupported provider request catalog schema: {source_catalog.get('schema_version')!r}"
        )
    if isinstance(current_packet, (str, Path)):
        packet = _read_json(current_packet)
        packet_source = str(Path(current_packet).resolve())
    else:
        packet = dict(current_packet)
        packet_source = None
    current = _current_packet(packet)
    if current["event_id"] != event_id:
        raise ProviderRequestRebaselineError(
            f"current packet event_id does not match requested event: {current['event_id']!r}"
        )

    row_index, request_index, old_request = _find_request(source_catalog, event_id)
    old_packet = old_request.get("current_packet")
    if not isinstance(old_packet, Mapping):
        raise ProviderRequestRebaselineError("request.current_packet must be an object")
    for key in ("event_id", "component_id", "port_id", "event_kind"):
        if old_packet.get(key) != current.get(key):
            raise ProviderRequestRebaselineError(
                f"request identity mismatch for {key}: {old_packet.get(key)!r} != {current.get(key)!r}"
            )
    previous_source = _digest(old_packet.get("provider_source_digest"), "previous provider_source_digest")
    previous_result = _digest(old_packet.get("provider_result_digest"), "previous provider_result_digest")

    updated = copy.deepcopy(source_catalog)
    updated_row = updated["requests"][row_index]
    updated_request = updated_row["requests"][request_index]
    updated_request["current_packet"] = current
    updated_request["packet_path"] = packet_source or updated_request.get("packet_path")
    updated_request["blocking_reasons"] = list(dict.fromkeys([
        *(updated_request.get("blocking_reasons") or []),
        *[str(reason) for reason in additional_blockers],
    ]))
    sidecar = updated_request.get("qualification_sidecar_required")
    if isinstance(sidecar, Mapping):
        sidecar = dict(sidecar)
        sidecar["provider_source_digests"] = [current["provider_source_digest"]]
        sidecar["provider_result_digests"] = [current["provider_result_digest"]]
        updated_request["qualification_sidecar_required"] = sidecar
    acceptance = updated_request.get("acceptance")
    if isinstance(acceptance, Mapping):
        acceptance = dict(acceptance)
        acceptance["qualification_sidecar_digest_bound"] = True
        acceptance["frequency_inference_allowed"] = False
        acceptance["facility_qra_allowed"] = False
        updated_request["acceptance"] = acceptance
    updated_request["status"] = "OPEN"
    updated_request["rebaseline"] = {
        "schema_version": SCHEMA,
        "status": "DIGESTS_REBASED_TO_CURRENT_PACKET",
        "acknowledged": True,
        "previous_request": {
            "provider_source_digest": previous_source,
            "provider_result_digest": previous_result,
        },
        "current_request": {
            "provider_source_digest": current["provider_source_digest"],
            "provider_result_digest": current["provider_result_digest"],
        },
        "packet_source": packet_source,
        "independent_reverification": False,
        "qualification_sidecar_created": False,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "physical_validation_claim": False,
        "reason": "external provider packet was explicitly re-exported; prior digest binding is preserved for review",
    }
    updated["status"] = "OPEN_PROVIDER_QUALIFICATION_REQUESTS"
    updated["qualified_provider_packet_count"] = 0
    updated["frequency_inference_allowed"] = False
    updated["facility_qra_allowed"] = False
    updated["physical_validation_claim"] = False
    updated["rebaseline"] = {
        "schema_version": SCHEMA,
        "status": "DIGESTS_REBASED_TO_CURRENT_PACKET",
        "acknowledged": True,
        "catalog_source": catalog_source,
        "event_id": event_id,
        "previous_provider_source_digest": previous_source,
        "previous_provider_result_digest": previous_result,
        "current_provider_source_digest": current["provider_source_digest"],
        "current_provider_result_digest": current["provider_result_digest"],
        "independent_reverification": False,
        "qualification_sidecar_created": False,
        "promotion_allowed": False,
    }
    return {
        "schema_version": SCHEMA,
        "status": updated["status"],
        "event_id": event_id,
        "previous_request": old_request,
        "current_request": updated_request,
        "rebaseline": updated["rebaseline"],
        "catalog": updated,
    }


__all__ = ["SCHEMA", "ProviderRequestRebaselineError", "rebaseline_provider_request_catalog"]
