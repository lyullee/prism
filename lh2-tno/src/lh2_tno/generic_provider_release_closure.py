"""Aggregate provider release-boundary evidence for a generic LH2 campaign.

The facility campaign already carries release packets into consequence and
IR/F-N calculations.  This module audits the upstream evidence separately so
that a complete computational chain is not mistaken for a qualified provider
release boundary.  It never repairs a packet, infers a duration, assigns a
frequency, or opens a facility-QRA gate.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from .provider_release_closure import (
    ProviderReleaseClosureError,
    audit_provider_release_closure,
)


SCHEMA = "prism.generic_provider_release_closure_audit.v1"


_COMMON_CLOSURE_REQUEST_FIELDS = (
    {
        "field": "input_origin",
        "accepted": "reviewed_measurement or reviewed_model",
        "reason": "synthetic input cannot qualify a provider boundary",
    },
    {
        "field": "termination_basis",
        "accepted": "reviewed_isolation_success or inventory_depletion",
        "reason": "a fixed horizon or pressure-equalization stop is not a physical release end",
    },
    {
        "field": "termination_provenance",
        "accepted": "provider-owned method, version and evidence identifier",
        "reason": "the end of the release must be reproducible and attributable",
    },
    {
        "field": "provider_result_digest",
        "accepted": "SHA-256 bound to the termination evidence",
        "reason": "a sidecar must refer to this exact provider result",
    },
    {
        "field": "provider_mass_balance",
        "accepted": "initial mass, released mass, final/residual mass and residual tolerance",
        "reason": "the release cannot be promoted without inventory closure",
    },
    {
        "field": "independent_validation_reference",
        "accepted": "reviewed validation record or an explicit validation gap",
        "reason": "closure readiness does not by itself establish physical validation",
    },
)


def _family_closure_request_fields(event_id: Any, event_kind: Any) -> list[dict[str, str]]:
    """Return evidence fields tailored to the equipment boundary.

    This is a request template only.  It never infers an isolation time,
    inventory threshold or failure probability from the event name.
    """

    token = f"{event_id or ''} {event_kind or ''}".lower()
    if "transfer-line" in token or "pipe" in token:
        return [
            {
                "field": "inlet_isolation_time_s",
                "accepted": "reviewed provider clock with isolation success/failure state",
                "reason": "pipe release duration depends on upstream inflow after the opening",
            },
            {
                "field": "upstream_downstream_state_history",
                "accepted": "provider history for both sides of the line",
                "reason": "a line opening cannot use a tank or valve surrogate for its boundary",
            },
        ]
    if "transfer-valve" in token or "valve" in token:
        return [
            {
                "field": "valve_opening_and_travel_history",
                "accepted": "reviewed failed-opening or failed-closure history",
                "reason": "valve event duration must belong to the valve boundary",
            },
            {
                "field": "connected_inventory_and_isolation_state",
                "accepted": "provider-owned connected inventory and isolation response",
                "reason": "a valve packet cannot borrow a pipe termination basis",
            },
        ]
    if "pump" in token:
        return [
            {
                "field": "pump_trip_or_seal_failure_history",
                "accepted": "reviewed pump failure state and clock",
                "reason": "pump release duration depends on the pump failure mode",
            },
            {
                "field": "connected_inventory_and_isolation_state",
                "accepted": "provider-owned connected inventory and isolation response",
                "reason": "upstream service must be closed at the pump boundary",
            },
        ]
    if "vaporizer" in token:
        return [
            {
                "field": "process_side_state_history",
                "accepted": "reviewed vaporizer process-side state and boundary history",
                "reason": "vaporizer failure must retain its own phase and inventory basis",
            },
            {
                "field": "connected_inventory_and_isolation_state",
                "accepted": "provider-owned connected inventory and isolation response",
                "reason": "the downstream gas boundary cannot define the upstream liquid release",
            },
        ]
    if "reliquefier" in token:
        return [
            {
                "field": "reliquefier_failure_mode_and_endpoint_history",
                "accepted": "reviewed failure mode with every affected endpoint",
                "reason": "reliquefier cases may have more than one provider outlet",
            },
            {
                "field": "connected_inventory_and_isolation_state",
                "accepted": "provider-owned connected inventory and isolation response",
                "reason": "the endpoint history must close against the affected inventory",
            },
        ]
    return [
        {
            "field": "equipment_specific_failure_and_boundary_history",
            "accepted": "reviewed provider history for the declared equipment boundary",
            "reason": "the event family is not allowed to inherit a different equipment model",
        }
    ]


def _closure_request(
    packet: Mapping[str, Any],
    *,
    event_id: Any,
    event_kind: Any,
    blocking_reasons: Sequence[str],
) -> dict[str, Any]:
    """Build an actionable evidence request for one open provider packet."""

    fields = [
        *(_COMMON_CLOSURE_REQUEST_FIELDS),
        *_family_closure_request_fields(event_id, event_kind),
    ]
    current = {
        "event_id": packet.get("event_id", event_id),
        "component_id": packet.get("component_id"),
        "port_id": packet.get("port_id"),
        "event_kind": packet.get("event_kind", event_kind),
        "input_origin": packet.get("input_origin"),
        "termination_basis": packet.get("termination_basis"),
        "termination_provenance": packet.get("termination_provenance"),
        "duration_s": packet.get("duration_s"),
        "available_mass_kg": packet.get("available_mass_kg"),
        "cumulative_mass_out_kg": packet.get("cumulative_mass_out_kg"),
        "provider_source_digest": packet.get("provider_source_digest"),
        "provider_result_digest": packet.get("provider_result_digest"),
    }
    return {
        "request_schema": "prism.provider_release_closure_request.v1",
        "request_id": str(packet.get("event_id", event_id)),
        "status": "OPEN",
        "current_packet": current,
        "blocking_reasons": list(dict.fromkeys(str(item) for item in blocking_reasons)),
        "required_evidence": fields,
        "qualification_sidecar_required": {
            "schema_version": "prism.provider_qualification_evidence.v1",
            "status": "qualified_actual",
            "provider_origin": ["native_provider", "reviewed_actual"],
            "evidence_id": "nonempty reviewed evidence identifier",
            "provider_source_digests": [packet.get("provider_source_digest")],
            "provider_result_digests": [packet.get("provider_result_digest")],
            "exact_digest_binding": True,
        },
        "acceptance": {
            "exact_event_component_port_match": True,
            "termination_evidence_digest_bound": True,
            "qualification_sidecar_digest_bound": True,
            "provider_owned_clock_and_mass_ledger": True,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
        },
    }


class GenericProviderReleaseClosureError(ValueError):
    """Raised when campaign packet evidence is malformed."""


def _read(value: Mapping[str, Any] | str | Path, label: str) -> tuple[Mapping[str, Any], Path | None]:
    source: Path | None = None
    if isinstance(value, (str, Path)):
        source = Path(value).resolve()
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GenericProviderReleaseClosureError(f"cannot read {label}: {error}") from error
    if not isinstance(value, Mapping):
        raise GenericProviderReleaseClosureError(f"{label} must be an object")
    return value, source


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise GenericProviderReleaseClosureError("packet evidence rows must be an array")
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise GenericProviderReleaseClosureError(f"packet evidence rows[{index}] must be an object")
        result.append(row)
    return result


def _path_for(raw: Any, *, root: Path | None, source: Path | None) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise GenericProviderReleaseClosureError("resolved_packet_paths must contain non-empty strings")
    path = Path(raw)
    if not path.is_absolute():
        base = root if root is not None else (source.parent if source is not None else None)
        if base is None:
            raise GenericProviderReleaseClosureError(
                "relative packet paths require packet_root or a packet-evidence file path"
            )
        path = base / path
    path = path.resolve()
    if not path.is_file():
        raise GenericProviderReleaseClosureError(f"resolved provider packet is missing: {path}")
    return path


def _provider_termination_evidence(
    packet_path: Path,
    packet: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]] | None:
    """Load the exporter ledger paired with a resolved packet, if present.

    Exporters keep positive-inventory threshold metadata in ``verification.json``
    so the strict release contract does not confuse a provider residual with
    zero inventory.  The digest check below binds that sidecar to the packet;
    an unrelated verification file is ignored and the packet remains open.
    """
    path = packet_path.parent / "verification.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None
    meta = value.get("provider_run_meta")
    if isinstance(meta, Mapping):
        evidence = dict(meta)
    elif isinstance(packet.get("provider_meta"), Mapping):
        # DynamicVaporizer stores the releasable-inventory ledger in the
        # resolved packet while its verification record carries only the
        # generic execution status.  Bind that provider-owned ledger to the
        # packet itself instead of treating the remaining upstream reserve as
        # an unaccounted zero-mass depletion.
        provider_meta = dict(packet["provider_meta"])
        if provider_meta.get("release_mode") == "instantaneous_inventory":
            evidence = {
                "termination_basis": "inventory_depletion_releasable_mass",
                "available_mass_kg": packet.get("available_mass_kg"),
                "cumulative_mass_out_kg": packet.get("cumulative_mass_out_kg"),
                "available_mass_definition": provider_meta.get(
                    "available_mass_definition"
                ),
                "remaining_releasable_mass_kg": (
                    float(packet.get("available_mass_kg", 0.0))
                    - float(packet.get("cumulative_mass_out_kg", 0.0))
                ),
                "provider_residual_mass_kg": provider_meta.get("residual_mass_kg"),
            }
        elif provider_meta.get("termination_basis") == "inventory_depletion_positive_threshold":
            evidence = {
                "termination_basis": "inventory_depletion_positive_threshold",
                "available_mass_kg": packet.get("available_mass_kg"),
                "cumulative_mass_out_kg": packet.get("cumulative_mass_out_kg"),
                "threshold_mass_kg": provider_meta.get("depletion_threshold_kg"),
                "remaining_mass_kg": provider_meta.get("remaining_mass_kg"),
                "max_abs_mass_residual_kg": provider_meta.get(
                    "max_abs_mass_residual_kg"
                ),
            }
        else:
            return None
    else:
        # Some exporter envelopes keep provider_meta in the raw response
        # under ``data`` while the resolved packet deliberately contains only
        # the strict atmospheric boundary fields.
        response_path = packet_path.parent / "provider_response.json"
        try:
            response_value = json.loads(response_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        response_data = (
            response_value.get("data")
            if isinstance(response_value, Mapping)
            else None
        )
        response_meta = (
            response_data.get("provider_meta")
            if isinstance(response_data, Mapping)
            else None
        )
        if not isinstance(response_meta, Mapping):
            return None
        if response_meta.get("release_mode") == "instantaneous_inventory":
            evidence = {
                "termination_basis": "inventory_depletion_releasable_mass",
                "available_mass_kg": packet.get("available_mass_kg"),
                "cumulative_mass_out_kg": packet.get("cumulative_mass_out_kg"),
                "available_mass_definition": response_meta.get(
                    "available_mass_definition"
                ),
                "remaining_releasable_mass_kg": (
                    float(response_meta.get("remaining_releasable_mass_kg"))
                    if response_meta.get("remaining_releasable_mass_kg") is not None
                    else float(packet.get("available_mass_kg", 0.0))
                    - float(packet.get("cumulative_mass_out_kg", 0.0))
                ),
                "provider_residual_mass_kg": response_meta.get("residual_mass_kg"),
            }
        elif response_meta.get("termination_basis") == "inventory_depletion_positive_threshold":
            evidence = {
                "termination_basis": "inventory_depletion_positive_threshold",
                "available_mass_kg": packet.get("available_mass_kg"),
                "cumulative_mass_out_kg": packet.get("cumulative_mass_out_kg"),
                "threshold_mass_kg": response_meta.get("depletion_threshold_kg"),
                "remaining_mass_kg": response_meta.get("remaining_mass_kg"),
                "max_abs_mass_residual_kg": response_meta.get(
                    "max_abs_mass_residual_kg"
                ),
            }
        else:
            return None
    digest = value.get("provider_result_digest")
    if isinstance(digest, str):
        evidence["provider_result_digest"] = digest
    return path, evidence


def _event_row(
    evidence: Mapping[str, Any],
    *,
    index: int,
    root: Path | None,
    source: Path | None,
) -> dict[str, Any]:
    event_id = evidence.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise GenericProviderReleaseClosureError(f"packet evidence row[{index}].event_id is required")
    raw_evidence = evidence.get("evidence")
    if not isinstance(raw_evidence, Mapping):
        raise GenericProviderReleaseClosureError(f"packet evidence row[{index}].evidence must be an object")
    raw_paths = raw_evidence.get("resolved_packet_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise GenericProviderReleaseClosureError(
            f"packet evidence row[{index}].evidence.resolved_packet_paths must be a non-empty array"
        )
    packet_rows: list[dict[str, Any]] = []
    event_reasons: list[str] = []
    for packet_index, raw_path in enumerate(raw_paths):
        try:
            packet_path = _path_for(raw_path, root=root, source=source)
            packet_value = json.loads(packet_path.read_text(encoding="utf-8"))
            sidecar = None
            if isinstance(packet_value, Mapping):
                sidecar = _provider_termination_evidence(packet_path, packet_value)
            audit = audit_provider_release_closure(
                packet_path,
                termination_evidence=sidecar[1] if sidecar is not None else None,
            )
            packet_status = audit["status"]
            reasons = list(audit.get("blocking_reasons", ()))
            packet_row = {
                "packet_index": packet_index,
                "path": str(packet_path),
                "status": packet_status,
                "packet_count": audit.get("packet_count"),
                "closure_status_counts": audit.get("closure_status_counts", {}),
                "blocking_reasons": reasons,
                "termination_evidence_path": (
                    str(sidecar[0]) if sidecar is not None else None
                ),
                "termination_evidence_used": bool(sidecar is not None),
            }
            if reasons and isinstance(packet_value, Mapping):
                packet_row["closure_request"] = _closure_request(
                    packet_value,
                    event_id=event_id,
                    event_kind=packet_value.get("event_kind"),
                    blocking_reasons=reasons,
                )
            packet_rows.append(packet_row)
            event_reasons.extend(f"packet[{packet_index}]: {reason}" for reason in reasons)
        except (GenericProviderReleaseClosureError, ProviderReleaseClosureError, OSError, ValueError) as error:
            reason = f"packet[{packet_index}] audit failed: {error}"
            packet_rows.append({
                "packet_index": packet_index,
                "path": str(raw_path),
                "status": "CLOSURE_EVIDENCE_OPEN",
                "packet_count": None,
                "closure_status_counts": {},
                "blocking_reasons": [reason],
            })
            event_reasons.append(reason)
    event_reasons = list(dict.fromkeys(event_reasons))
    return {
        "event_index": index,
        "event_id": event_id,
        "component_id": evidence.get("component_id"),
        "packet_path_count": len(packet_rows),
        "packet_rows": packet_rows,
        "closure_status": (
            "CLOSURE_READY_FOR_QUALIFICATION" if not event_reasons else "CLOSURE_EVIDENCE_OPEN"
        ),
        "blocking_reasons": event_reasons,
    }


def audit_generic_provider_release_closure(
    packet_evidence: Mapping[str, Any] | str | Path,
    *,
    packet_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a fail-closed, event-level closure audit for packet evidence."""
    value, source = _read(packet_evidence, "packet evidence")
    root = Path(packet_root).resolve() if packet_root is not None else None
    raw_rows = _rows(value.get("rows"))
    event_rows = [
        _event_row(row, index=index, root=root, source=source)
        for index, row in enumerate(raw_rows)
    ]
    status_counts = Counter(row["closure_status"] for row in event_rows)
    def _core_reason(reason: str) -> str:
        # Event and packet prefixes are useful in the detailed rows but make
        # aggregate gap counts noisy.  Remove only those generated prefixes.
        while reason.startswith("packet[") and "]: " in reason:
            reason = reason.split("]: ", 1)[1]
        return reason

    gap_counts = Counter(
        _core_reason(reason)
        for row in event_rows
        for reason in row["blocking_reasons"]
    )
    packet_path_count = sum(row["packet_path_count"] for row in event_rows)
    provider_packet_count = sum(
        int(packet.get("packet_count") or 0)
        for row in event_rows
        for packet in row["packet_rows"]
    )
    packet_ready_path_count = sum(
        packet.get("status") == "CLOSURE_READY_FOR_QUALIFICATION"
        for row in event_rows
        for packet in row["packet_rows"]
    )
    provider_packet_ready_count = sum(
        int(packet.get("packet_count") or 0)
        for row in event_rows
        for packet in row["packet_rows"]
        if packet.get("status") == "CLOSURE_READY_FOR_QUALIFICATION"
    )
    return {
        "schema_version": SCHEMA,
        "status": (
            "CLOSURE_READY_FOR_QUALIFICATION"
            if event_rows and not any(row["blocking_reasons"] for row in event_rows)
            else "CLOSURE_EVIDENCE_OPEN"
        ),
        "source_schema_version": value.get("schema_version"),
        "event_count": len(event_rows),
        "event_closure_status_counts": dict(sorted(status_counts.items())),
        "closure_ready_event_count": status_counts.get("CLOSURE_READY_FOR_QUALIFICATION", 0),
        "closure_open_event_count": status_counts.get("CLOSURE_EVIDENCE_OPEN", 0),
        "packet_path_count": packet_path_count,
        "provider_packet_count": provider_packet_count,
        "closure_ready_packet_path_count": packet_ready_path_count,
        "closure_ready_provider_packet_count": provider_packet_ready_count,
        "event_rows": event_rows,
        "closure_gap_counts": dict(sorted(gap_counts.items())),
        "qualified_provider_packet_count": 0,
        "frequency_from_provider_packet": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "promotion_gates": {
            "closure_ready": False,
            "qualified_provider_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "diagnostic_only": True,
        },
        "diagnostic_only": True,
    }


__all__ = [
    "SCHEMA",
    "GenericProviderReleaseClosureError",
    "audit_generic_provider_release_closure",
]
