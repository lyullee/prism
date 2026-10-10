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
    if not isinstance(meta, Mapping):
        return None
    evidence = dict(meta)
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
            packet_rows.append({
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
            })
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
