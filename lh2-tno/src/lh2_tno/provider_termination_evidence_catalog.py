"""Build a portable catalog of provider-owned release termination evidence.

The catalog is deliberately narrower than provider qualification.  It records
only explicit provider stopping rules and mass residual diagnostics so the
facility release-boundary audit can consume them without treating a positive
threshold as zero inventory or inferring a frequency.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


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
    if events_dir.is_dir():
        event_dirs = sorted(path for path in events_dir.iterdir() if path.is_dir())
    elif (catalog_dir / "resolved_release.json").is_file() and (catalog_dir / "verification.json").is_file():
        # A single persisted provider packet is a useful additional replay
        # source.  Accept it directly so callers do not need to manufacture a
        # one-event catalog wrapper around an already immutable result bundle.
        event_dirs = [catalog_dir]
    else:
        raise ValueError(f"storage catalog events directory is missing: {events_dir}")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for event_dir in event_dirs:
        packet_path = event_dir / "resolved_release.json"
        if not packet_path.exists():
            packet_path = event_dir / "resolved_release_set.json"
        verification_path = event_dir / "verification.json"
        try:
            packet = _read_json(packet_path)
            verification = _read_json(verification_path)
            if packet.get("provider_export_schema") == "prism.resolved_release_set.v1":
                releases = packet.get("releases")
                endpoint_rows = [release for release in releases if isinstance(release, Mapping)] if isinstance(releases, list) else []
                endpoint_digests = [
                    release.get("provider_result_digest")
                    for release in endpoint_rows
                    if isinstance(release.get("provider_result_digest"), str)
                ]
                event_id = packet.get("event_id")
                if not isinstance(event_id, str) or not event_id:
                    errors.append(f"{event_dir.name}: resolved release set event_id is missing")
                    continue
                if len(endpoint_rows) != 2 or len(endpoint_digests) != 2:
                    errors.append(f"{event_id}: two-sided provider endpoint set is incomplete")
                    continue
                verification_endpoint_count = verification.get("strict_packet_endpoint_count")
                if verification_endpoint_count != len(endpoint_rows):
                    errors.append(f"{event_id}: endpoint count does not match verification")
                    continue
                rows.append({
                    "event_id": event_id,
                    "component_id": packet.get("component_id"),
                    "provider_result_digest": packet.get("provider_result_digest"),
                    "provider_result_digests": endpoint_digests,
                    "termination_basis": packet.get("rupture_mode"),
                    "available_mass_kg": [
                        release.get("available_mass_kg") for release in endpoint_rows
                    ],
                    "cumulative_mass_out_kg": [
                        release.get("cumulative_mass_out_kg") for release in endpoint_rows
                    ],
                    "max_abs_mass_residual_kg": abs(float(verification.get("strict_packet_mass_residual_kg")))
                    if _number(verification.get("strict_packet_mass_residual_kg")) is not None
                    else None,
                    "duration_s": [release.get("duration_s") for release in endpoint_rows],
                    "endpoint_count": len(endpoint_rows),
                    "termination_provenance": packet.get("inventory_provenance"),
                    "operator_limited": True,
                    "physical_validation_claim": verification.get("physical_validation_claim") is True,
                    "source": {
                        "packet": str(packet_path),
                        "verification": str(verification_path),
                        "provider_export_schema": packet.get("provider_export_schema"),
                    },
                })
                continue
            meta = verification.get("provider_run_meta")
            if not isinstance(meta, Mapping):
                # Native accident exports use the same resolved-release and
                # verification contract, but their termination fields live in
                # provider_response.data/provider_meta.  Preserve those rows
                # instead of misclassifying them as absent evidence.
                response_path = event_dir / "provider_response.json"
                try:
                    response = _read_json(response_path)
                    data = response.get("data")
                    provider_meta = data.get("provider_meta") if isinstance(data, Mapping) else None
                    if not isinstance(data, Mapping) or not isinstance(provider_meta, Mapping):
                        errors.append(f"{event_dir.name}: provider_run_meta and native provider response are missing")
                        continue
                    event_id = data.get("event_id") or packet.get("event_id")
                    digest = packet.get("provider_result_digest")
                    if not isinstance(event_id, str) or not event_id:
                        errors.append(f"{event_dir.name}: packet/provider response event_id is missing")
                        continue
                    if not isinstance(digest, str) or not digest:
                        errors.append(f"{event_dir.name}: packet provider_result_digest is missing")
                        continue
                    verification_digest = verification.get("provider_result_digest")
                    if verification_digest != digest:
                        errors.append(f"{event_id}: packet and verification digests do not agree")
                        continue
                    termination_basis = data.get("termination_basis")
                    row: dict[str, Any] = {
                        "event_id": event_id,
                        "component_id": data.get("component_id") or packet.get("component_id"),
                        "provider_result_digest": digest,
                        "termination_basis": termination_basis,
                        "available_mass_kg": data.get("available_mass_kg"),
                        "cumulative_mass_out_kg": data.get("cumulative_mass_out_kg"),
                        "duration_s": data.get("duration_s") or verification.get("duration_s"),
                        "operator_limited": False,
                        "physical_validation_claim": verification.get("physical_validation_claim") is True,
                        "source": {
                            "packet": str(packet_path),
                            "verification": str(verification_path),
                            "provider_response": str(response_path),
                            "provider_response_status": response.get("provider_export_schema"),
                        },
                    }
                    if termination_basis == "reviewed_isolation_success":
                        row.update({
                            "isolation_success": verification.get("isolation_success", provider_meta.get("isolation_success")),
                            "isolation_time_s": verification.get("isolation_time_s", provider_meta.get("isolation_time_s")),
                            "post_isolation_observation_s": verification.get(
                                "post_isolation_observation_s", provider_meta.get("post_isolation_observation_s")
                            ),
                            "post_isolation_zero_flow": provider_meta.get("post_isolation_zero_flow"),
                            "termination_provenance": data.get("termination_provenance"),
                            "max_abs_mass_residual_kg": verification.get("mass_residual_kg"),
                            "provider_residual_mass_kg": verification.get("mass_residual_kg"),
                        })
                    elif termination_basis == "inventory_depletion":
                        definition = provider_meta.get("available_mass_definition")
                        available = _number(data.get("available_mass_kg"))
                        released = _number(data.get("cumulative_mass_out_kg"))
                        if isinstance(definition, str) and "releasable" in definition.lower():
                            row.update({
                                "termination_basis": "inventory_depletion_releasable_mass",
                                "available_mass_definition": definition,
                                "remaining_releasable_mass_kg": (
                                    max(0.0, available - released)
                                    if available is not None and released is not None
                                    else None
                                ),
                                "provider_residual_mass_kg": provider_meta.get("residual_mass_kg"),
                            })
                        else:
                            row.update({
                                "threshold_mass_kg": data.get("depletion_threshold_kg"),
                                "remaining_mass_kg": data.get("remaining_inventory_kg"),
                                "max_abs_mass_residual_kg": data.get("max_total_mass_residual_kg"),
                            })
                    rows.append(row)
                    continue
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                    errors.append(f"{event_dir.name}: native provider response error: {error}")
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
    additional_storage_catalog_dirs: Sequence[str | Path] | None = None,
    inventory_provider_responses: Mapping[str, Any] | None = None,
    inventory_resolved_releases: Mapping[str, Any] | None = None,
    inventory_source_paths: Mapping[str, str] | None = None,
    inventory_source_event_prefix: str = "equipment-inventory-campaign/",
    # The target scope already owns the ``inventory-depletion`` family
    # segment. Keeping it in the default once is important: duplicating the
    # segment produces an event identity that cannot match the facility case
    # ledger, so otherwise valid provider evidence is reported as missing.
    inventory_target_event_prefix: str = "generic-lh2-full-scope-example/inventory-depletion/",
) -> dict[str, Any]:
    """Build the evidence catalog from persisted provider artifacts."""

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    source_records: list[str] = []
    storage_dirs: list[Path] = []
    if storage_catalog_dir is not None:
        storage_dirs.append(Path(storage_catalog_dir))
    storage_dirs.extend(Path(value) for value in (additional_storage_catalog_dirs or ()))
    seen_storage_dirs: set[Path] = set()
    for storage_dir in storage_dirs:
        if storage_dir in seen_storage_dirs:
            continue
        seen_storage_dirs.add(storage_dir)
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
    # One facility event can legitimately have several provider packets when
    # the same opening is replayed with different provider clocks, isolation
    # policies, or model revisions.  Keep those variants in the catalog and
    # let the consuming case select by its exact provider-result digest.  A
    # repeated event/digest pair is still an ambiguous duplicate and remains
    # fail-closed.
    rows_by_event: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_event.setdefault(str(row["event_id"]), []).append(row)
    duplicate_event_ids = sorted(
        event_id
        for event_id, event_rows in rows_by_event.items()
        if len({str(row.get("provider_result_digest")) for row in event_rows})
        < len(event_rows)
    )
    variant_event_ids = sorted(
        event_id
        for event_id, event_rows in rows_by_event.items()
        if len(event_rows) > 1
        and event_id not in duplicate_event_ids
    )
    if duplicate_event_ids:
        errors.extend(f"duplicate evidence event_id/digest: {event_id}" for event_id in duplicate_event_ids)
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
        "variant_event_ids": variant_event_ids,
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
