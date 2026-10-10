"""Fail-closed audit for a batch of provider release/qualification records.

The facility case coverage audit answers whether already-promoted evidence
matches a requested case.  This module covers the earlier file boundary: it
checks every release packet against its qualification sidecar, retains a
machine-readable rejection reason, and only emits a catalog row after the
strict promotion helper succeeds.  It never assigns a frequency, executes
consequence physics, or treats a diagnostic packet as actual evidence.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from .provider_packet_promotion import (
    ProviderPacketPromotionError,
    build_provider_packet_evidence_from_records,
)


SCHEMA = "prism.provider_packet_input_audit.v1"


def _load_json(value: Any, *, base_dir: Path | None = None, label: str) -> Any:
    if not isinstance(value, (str, Path)):
        return value
    path = Path(value)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderPacketPromotionError(f"cannot read {label}: {error}") from error


def _record_value(record: Mapping[str, Any], key: str, *, base_dir: Path | None) -> Any:
    """Resolve an inline object or an explicit ``<key>_path`` value."""
    if key in record:
        return record[key]
    path_key = f"{key}_path"
    if path_key in record:
        return _load_json(record[path_key], base_dir=base_dir, label=path_key)
    return None


def audit_provider_packet_inputs(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | Path,
) -> dict[str, Any]:
    """Audit a provider packet manifest without changing its records.

    A manifest may be an array or ``{"records": [...]}``.  Each row contains
    either inline ``release``/``qualification`` objects or their corresponding
    ``release_path``/``qualification_path``.  Paths are resolved relative to
    the manifest file when ``manifest`` is a path.  A rejected row remains in
    ``records`` with its exact error; it is never silently dropped.
    """
    base_dir: Path | None = None
    raw: Any = manifest
    if isinstance(manifest, (str, Path)):
        path = Path(manifest)
        base_dir = path.parent
        raw = _load_json(path, label="provider packet manifest")
    if isinstance(raw, Mapping):
        raw = raw.get("records", raw.get("provider_packet_inputs"))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("provider packet manifest must contain a records array")

    rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    accepted_identities: set[tuple[Any, ...]] = set()
    accepted_event_ids: set[str] = set()
    duplicate_event_ids: set[str] = set()
    rejected_count = 0
    for index, raw_record in enumerate(raw):
        record_id = f"record-{index + 1}"
        if isinstance(raw_record, Mapping):
            record_id = str(raw_record.get("record_id") or record_id)
        entry: dict[str, Any] = {
            "record_id": record_id,
            "status": "REJECTED_INPUT",
            "event_id": None,
            "component_id": None,
            "evidence_id": None,
            "blocking_reasons": [],
        }
        if not isinstance(raw_record, Mapping):
            entry["blocking_reasons"] = ["record must be a JSON object"]
            rows.append(entry)
            rejected_count += 1
            continue
        try:
            release = _record_value(raw_record, "release", base_dir=base_dir)
            qualification = _record_value(raw_record, "qualification", base_dir=base_dir)
            if release is None:
                raise ProviderPacketPromotionError("release or release_path is required")
            if qualification is None:
                raise ProviderPacketPromotionError(
                    "qualification or qualification_path is required"
                )
            evidence = build_provider_packet_evidence_from_records(
                release, qualification
            )
            entry.update({
                "status": "QUALIFIED_PROVIDER_PACKET_EVIDENCE",
                "event_id": evidence.event_id,
                "component_id": evidence.component_id,
                "evidence_id": evidence.evidence_id,
                "port_ids": list(evidence.port_ids),
                "provider_source_digests": list(evidence.provider_source_digests),
                "provider_result_digests": list(evidence.provider_result_digests),
                "provider_qualification_schema": evidence.provider_qualification_schema,
                "provider_export_schema": evidence.provider_export_schema,
                "qualification_status": evidence.status,
            })
            identity = (
                evidence.event_id,
                evidence.component_id,
                tuple(evidence.port_ids),
                tuple(evidence.provider_source_digests),
                tuple(evidence.provider_result_digests),
            )
            if identity in accepted_identities:
                duplicate_event_ids.add(evidence.event_id)
                entry["status"] = "REJECTED_DUPLICATE_EVENT"
                entry["blocking_reasons"] = [
                    "an identical provider packet identity was accepted already"
                ]
                rejected_count += 1
            else:
                accepted_identities.add(identity)
                accepted_event_ids.add(evidence.event_id)
                evidence_rows.append(evidence.model_dump(mode="json"))
        except (ProviderPacketPromotionError, TypeError, ValueError) as error:
            entry["blocking_reasons"] = [str(error)]
            rejected_count += 1
        rows.append(entry)

    accepted_count = len(evidence_rows)
    if accepted_count == 0:
        status = "NO_PROVIDER_PACKET_INPUT"
    elif rejected_count:
        status = "PARTIAL_PROVIDER_PACKET_CATALOG"
    else:
        status = "QUALIFIED_PROVIDER_PACKET_CATALOG"
    blockers: list[str] = []
    if not raw:
        blockers.append("provider packet manifest contains no records")
    if rejected_count:
        blockers.append(f"{rejected_count} provider packet input record(s) were rejected")
    if duplicate_event_ids:
        blockers.append("provider packet input contains duplicate event_id values")
    return {
        "schema": SCHEMA,
        "status": status,
        "input_record_count": len(raw),
        "accepted_provider_packet_count": accepted_count,
        "accepted_provider_event_count": len(accepted_event_ids),
        "rejected_record_count": rejected_count,
        "duplicate_event_ids": sorted(duplicate_event_ids),
        "blocking_reasons": blockers,
        "provider_packet_evidence": evidence_rows,
        "records": rows,
        "promotion_policy": {
            "frequency_is_not_assigned": True,
            "synthetic_input_is_not_promoted": True,
            "qualification_sidecar_is_required": True,
            "strict_release_contract_is_required": True,
            "distinct_packets_per_event_allowed": True,
            "facility_ir_fn_promotion": "requires exact facility case coverage and independent validation gates",
        },
    }


__all__ = ["SCHEMA", "audit_provider_packet_inputs"]
