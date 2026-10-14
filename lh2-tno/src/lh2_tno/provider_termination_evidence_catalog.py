"""Build a portable catalog of provider-owned release termination evidence.

The catalog is deliberately narrower than provider qualification.  It records
only explicit provider stopping rules and mass residual diagnostics so the
facility release-boundary audit can consume them without treating a positive
threshold as zero inventory or inferring a frequency.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "prism.provider_termination_evidence_catalog.v1"


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _storage_rows(catalog_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events_dir = catalog_dir / "events"
    if not events_dir.is_dir():
        raise ValueError(f"storage catalog events directory is missing: {events_dir}")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for event_dir in sorted(path for path in events_dir.iterdir() if path.is_dir()):
        packet_path = event_dir / "resolved_release.json"
        verification_path = event_dir / "verification.json"
        try:
            packet = _read_json(packet_path)
            verification = _read_json(verification_path)
            meta = verification.get("provider_run_meta")
            if not isinstance(meta, Mapping):
                errors.append(f"{event_dir.name}: provider_run_meta is missing")
                continue
            event_id = packet.get("event_id")
            digest = packet.get("provider_result_digest")
            if not isinstance(event_id, str) or not event_id:
                errors.append(f"{event_dir.name}: packet event_id is missing")
                continue
            if not isinstance(digest, str) or not digest:
                errors.append(f"{event_dir.name}: packet provider_result_digest is missing")
                continue
            verification_digest = verification.get("provider_result_digest")
            if verification_digest != digest or meta.get("provider_result_digest", digest) not in {digest, None}:
                errors.append(f"{event_id}: packet and verification digests do not agree")
                continue
            row = {
                "event_id": event_id,
                "component_id": packet.get("component_id"),
                "provider_result_digest": digest,
                "termination_basis": meta.get("termination_basis"),
                "available_mass_kg": meta.get("available_mass_kg"),
                "cumulative_mass_out_kg": meta.get("cumulative_mass_out_kg"),
                "threshold_mass_kg": meta.get("threshold_mass_kg"),
                "remaining_mass_kg": meta.get("remaining_mass_kg"),
                "max_abs_mass_residual_kg": meta.get("max_abs_mass_residual_kg"),
                "duration_s": meta.get("duration_s"),
                "operator_limited": meta.get("operator_limited"),
                "physical_validation_claim": meta.get("physical_validation_claim"),
                "source": {
                    "packet": str(packet_path),
                    "verification": str(verification_path),
                    "provider_run_meta_status": meta.get("status"),
                },
            }
            rows.append(row)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            errors.append(f"{event_dir.name}: {error}")
    return rows, errors


def _inventory_rows(
    provider_responses: Mapping[str, Any],
    resolved_releases: Mapping[str, Any],
    *,
    source_paths: Mapping[str, str] | None = None,
    source_event_prefix: str = "equipment-inventory-campaign/",
    target_event_prefix: str = "generic-lh2-full-scope-example/inventory-depletion/",
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for source_event_id, response in sorted(provider_responses.items()):
        if not isinstance(response, Mapping):
            errors.append(f"{source_event_id}: provider response is not an object")
            continue
        data = response.get("data")
        release = resolved_releases.get(source_event_id)
        if not isinstance(data, Mapping) or not isinstance(release, Mapping):
            errors.append(f"{source_event_id}: provider response or resolved release is missing")
            continue
        result_digest = release.get("provider_result_digest")
        if not isinstance(result_digest, str) or not result_digest:
            errors.append(f"{source_event_id}: provider result digest is missing")
            continue
        if not source_event_id.startswith(source_event_prefix):
            errors.append(f"{source_event_id}: unexpected inventory event prefix")
            continue
        suffix = source_event_id.removeprefix(source_event_prefix)
        event_id = f"{target_event_prefix}{suffix}"
        available = data.get("available_mass_kg")
        released = data.get("cumulative_mass_out_kg")
        remaining = data.get("remaining_inventory_kg")
        threshold = data.get("depletion_threshold_kg")
        residual = data.get("max_total_mass_residual_kg")
        if any(_number(value) is None for value in (available, released, remaining, threshold, residual)):
            errors.append(f"{event_id}: provider inventory termination fields are incomplete")
            continue
        rows.append({
            "event_id": event_id,
            "component_id": release.get("component_id"),
            "provider_result_digest": result_digest,
            "termination_basis": "inventory_depletion_positive_threshold",
            "available_mass_kg": available,
            "cumulative_mass_out_kg": released,
            "threshold_mass_kg": threshold,
            "remaining_mass_kg": remaining,
            "max_abs_mass_residual_kg": residual,
            "duration_s": release.get("duration_s"),
            "operator_limited": False,
            "physical_validation_claim": response.get("physical_validation_claim") is True,
            "source": {
                "provider_response": (source_paths or {}).get("provider_responses"),
                "resolved_releases": (source_paths or {}).get("resolved_releases"),
                "source_event_id": source_event_id,
                "provider_termination_provenance": release.get("termination_provenance"),
            },
        })
    return rows, errors


def build_provider_termination_evidence_catalog(
    *,
    storage_catalog_dir: str | Path | None = None,
    inventory_provider_responses: Mapping[str, Any] | None = None,
    inventory_resolved_releases: Mapping[str, Any] | None = None,
    inventory_source_paths: Mapping[str, str] | None = None,
    inventory_source_event_prefix: str = "equipment-inventory-campaign/",
    inventory_target_event_prefix: str = "generic-lh2-full-scope-example/inventory-depletion/inventory-depletion/",
) -> dict[str, Any]:
    """Build the evidence catalog from persisted provider artifacts."""

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    source_records: list[str] = []
    if storage_catalog_dir is not None:
        storage_dir = Path(storage_catalog_dir)
        storage_rows, storage_errors = _storage_rows(storage_dir)
        rows.extend(storage_rows)
        errors.extend(storage_errors)
        source_records.append(str(storage_dir.resolve()))
    if inventory_provider_responses is not None or inventory_resolved_releases is not None:
        if not isinstance(inventory_provider_responses, Mapping) or not isinstance(
            inventory_resolved_releases, Mapping
        ):
            raise ValueError(
                "inventory_provider_responses and inventory_resolved_releases must be supplied together"
            )
        inventory_rows, inventory_errors = _inventory_rows(
            inventory_provider_responses,
            inventory_resolved_releases,
            source_paths=inventory_source_paths,
            source_event_prefix=inventory_source_event_prefix,
            target_event_prefix=inventory_target_event_prefix,
        )
        rows.extend(inventory_rows)
        errors.extend(inventory_errors)
        source_records.extend(
            str(value) for value in (inventory_source_paths or {}).values() if value
        )
    event_ids = [row["event_id"] for row in rows]
    duplicate_event_ids = sorted({event_id for event_id in event_ids if event_ids.count(event_id) > 1})
    if duplicate_event_ids:
        errors.extend(f"duplicate evidence event_id: {event_id}" for event_id in duplicate_event_ids)
    return {
        "schema_version": SCHEMA,
        "status": (
            "EVIDENCE_CATALOG_READY"
            if rows and not errors
            else "EVIDENCE_CATALOG_PARTIAL"
            if rows
            else "EVIDENCE_CATALOG_OPEN"
        ),
        "row_count": len(rows),
        "event_count": len(set(event_ids)),
        "duplicate_event_ids": duplicate_event_ids,
        "errors": list(dict.fromkeys(errors)),
        "source_records": list(dict.fromkeys(source_records)),
        "rows": rows,
        "provider_qualification_claim": False,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "diagnostic_only": True,
        "policy": (
            "explicit provider termination evidence only; positive thresholds are not converted to zero inventory; "
            "qualification, frequency inference and facility IR/F-N remain closed"
        ),
    }


__all__ = ["SCHEMA", "build_provider_termination_evidence_catalog"]
