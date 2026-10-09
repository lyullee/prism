"""Trace literature frequency inputs from the catalogue to facility events.

The report produced here is deliberately a provenance audit, not a claim that
the literature rates are field-validated.  It records the exact profile,
source digest, catalogue digest, exposure multiplier and uncertainty bounds
used by a declared frequency plan.  Missing field data and sensor-derived
frequency learning remain explicit policy values rather than silent fallbacks.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .contracts import canonical_digest
from .equipment_manifest import EquipmentManifest, audit_manifest
from .frequency import FrequencyPlan, catalogue, generate_events


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build_frequency_provenance_report(
    manifest: EquipmentManifest,
    plan: FrequencyPlan,
    *,
    catalogue_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a reproducible source-to-event frequency trace.

    ``catalogue_data`` is injectable for integrity tests.  Normal callers use
    the packaged reviewed snapshot through :func:`frequency.catalogue`.
    The function validates the manifest and plan before generating events and
    never invents a profile for an unlisted component.
    """
    data = deepcopy(catalogue_data if catalogue_data is not None else catalogue())
    catalogue_digest = canonical_digest(data)
    manifest_audit = audit_manifest(manifest)
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    checks.append({
        "id": "manifest_executable",
        "passed": manifest_audit["status"] == "EXECUTABLE",
        "status": manifest_audit["status"],
        "blocking_reasons": manifest_audit["blocking_reasons"],
    })
    if manifest_audit["status"] != "EXECUTABLE":
        blockers.append("manifest is not executable; frequency events were not promoted")

    profile_names = {asset.profile for asset in plan.assets}
    unknown_profiles = sorted(profile_names - set(data.get("profiles", {})))
    checks.append({
        "id": "frequency_profiles_reviewed",
        "passed": not unknown_profiles,
        "unknown_profiles": unknown_profiles,
    })
    if unknown_profiles:
        blockers.append("frequency plan references a profile missing from the reviewed catalogue")

    source_files = data.get("source_files", [])
    source_hashes = {row.get("sha256") for row in source_files if isinstance(row, dict)}
    profile_rows: list[dict[str, Any]] = []
    for profile_id in sorted(profile_names):
        profile = data.get("profiles", {}).get(profile_id)
        if profile is None:
            continue
        source_sha = profile.get("source_sha256")
        profile_rows.append({
            "profile": profile_id,
            "basis": profile.get("basis"),
            "statistic": profile.get("statistic"),
            "unit": profile.get("unit"),
            "source": profile.get("source"),
            "source_sha256": source_sha,
            "source_file_hash_registered": source_sha in source_hashes,
            "event_count_in_catalogue": len(profile.get("events", [])),
            "limitations": profile.get("limitations", []),
        })
        if source_sha not in source_hashes:
            blockers.append(f"profile {profile_id} source_sha256 is not registered in source_files")

    source_registry_check = not any(
        not row["source_file_hash_registered"] for row in profile_rows
    )
    checks.append({
        "id": "profile_source_hashes_registered",
        "passed": source_registry_check,
        "profile_count": len(profile_rows),
    })

    events: tuple = ()
    if not blockers:
        try:
            facility = manifest.to_facility()
            events = generate_events(facility, plan)
        except (ValueError, TypeError) as error:
            blockers.append(f"frequency event generation failed: {error}")
    event_rows = [event.model_dump(mode="json") for event in events]

    event_profile_ids = {event.profile for event in events}
    event_catalogue_digests = sorted({event.catalogue_digest for event in events})
    event_catalogue_check = event_catalogue_digests in ([], [catalogue_digest])
    checks.append({
        "id": "generated_event_catalogue_digest",
        "passed": event_catalogue_check,
        "catalogue_digest": catalogue_digest,
        "event_catalogue_digests": event_catalogue_digests,
    })
    if not event_catalogue_check:
        blockers.append("generated event catalogue_digest does not match the packaged snapshot")

    profile_event_coverage = {
        profile_id: sum(event.profile == profile_id for event in events)
        for profile_id in sorted(profile_names)
    }
    checks.append({
        "id": "plan_profiles_have_generated_events",
        "passed": event_profile_ids == profile_names,
        "profile_event_counts": profile_event_coverage,
    })
    if event_profile_ids != profile_names:
        blockers.append("one or more declared frequency profiles produced no generated event")

    limitations = _unique_strings([
        "Rates are a reviewed literature/catalogue baseline; they are not field-validated LH2 failure statistics.",
        "Field accident-frequency collection is intentionally inactive because no confirmed exposure/event register was supplied.",
        "Sensor alarms and process telemetry are not used to learn or multiply initiating-event frequency.",
        "Published marginal p05/p95 bounds are not a facility-level credible interval when event correlation is unavailable.",
        *data.get("unresolved_profiles", []),
        *[item for row in profile_rows for item in row["limitations"]],
    ])
    if manifest.configuration_origin == "synthetic":
        limitations.append("The supplied manifest is synthetic; real asset classification, count, length and applicability review is required.")
    limitations = _unique_strings(limitations)

    status = "FAILED_PROVENANCE_INTEGRITY" if blockers else "PASS_WITH_SCOPE_LIMITATIONS"
    return {
        "schema_version": "prism.frequency_provenance.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "facility": {
            "id": manifest.facility_id,
            "environment": manifest.environment,
            "configuration_origin": manifest.configuration_origin,
            "manifest_digest": manifest.digest(),
            "manifest_audit_status": manifest_audit["status"],
        },
        "frequency_plan": {
            "id": plan.id,
            "digest": plan.digest(),
            "asset_count": len(plan.assets),
            "excluded_model_components": plan.excluded_model_components,
        },
        "catalogue": {
            "digest": catalogue_digest,
            "reviewed_date_kst": data.get("reviewed_date_kst"),
            "interpretation": data.get("interpretation"),
            "source_files": source_files,
            "unresolved_profiles": data.get("unresolved_profiles", []),
        },
        "profile_provenance": profile_rows,
        "generated_events": event_rows,
        "policy": {
            "literature_frequency_baseline": True,
            "field_frequency_collection_used": False,
            "sensor_frequency_learning_used": False,
            "physical_validation_claim": False,
            "external_frequency_override_used": False,
            "frequency_is_separate_from_sensor_state": True,
        },
        "checks": checks,
        "blocking_reasons": _unique_strings(blockers),
        "limitations": limitations,
    }

