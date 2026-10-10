"""Audit diagnostic mappings from observed LH2 streams to generic components.

The inspection-center time series can identify *what kind of equipment* a
stream appears to describe, but the current package does not have a reviewed
asset register, P&ID endpoint identity, or accident-release packet for those
streams.  This audit records candidate classes and aliases.  A facility
component ID is accepted only when the manifest explicitly marks the asset
identity as field-confirmed and supplies separate identity evidence; even
then, no release event, frequency, or QRA result is created.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.observed_component_mapping_audit.v1"
MANIFEST_SCHEMA = "prism.observed_component_mapping_manifest.v1"
EVIDENCE_SCHEMA = "prism.observed_equipment_state_evidence.v1"


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
    result = [str(item).strip() for item in value]
    if any(not item for item in result):
        raise ValueError(f"{label} cannot contain empty values")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} cannot contain duplicate values")
    return result


def audit_observed_component_mapping(
    observed_state_evidence: Mapping[str, Any],
    mapping_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed component mapping report."""
    if not isinstance(observed_state_evidence, Mapping):
        raise ValueError("observed_state_evidence must be an object")
    if observed_state_evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError(f"observed_state_evidence schema_version must be {EVIDENCE_SCHEMA}")
    if not isinstance(mapping_manifest, Mapping):
        raise ValueError("mapping_manifest must be an object")
    if mapping_manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"mapping_manifest schema_version must be {MANIFEST_SCHEMA}")

    source_rows = _rows(observed_state_evidence.get("source_rows", []), "source_rows")
    observed: dict[str, list[str]] = {}
    for row in source_rows:
        component_id = str(row.get("component_id") or "").strip()
        source_id = str(row.get("source_id") or "").strip()
        if not component_id or not source_id:
            raise ValueError("source rows require component_id and source_id")
        observed.setdefault(component_id, []).append(source_id)
    if not observed:
        raise ValueError("observed_state_evidence contains no components")

    mapping_rows = _rows(mapping_manifest.get("mappings", []), "mapping_manifest.mappings")
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    exact_ids: set[str] = set()
    candidate_ids: set[str] = set()
    blocking_reasons: list[str] = []
    for index, mapping in enumerate(mapping_rows):
        mapping_id = str(mapping.get("mapping_id") or f"mapping-{index + 1}").strip()
        observed_component_id = str(mapping.get("observed_component_id") or "").strip()
        candidate_class = str(mapping.get("candidate_component_class") or "").strip()
        source_ids = _string_list(mapping.get("source_ids", []), f"mapping {mapping_id}.source_ids")
        aliases = _string_list(
            mapping.get("candidate_facility_asset_aliases", []),
            f"mapping {mapping_id}.candidate_facility_asset_aliases",
        )
        evidence_refs = _string_list(mapping.get("evidence_refs", []), f"mapping {mapping_id}.evidence_refs")
        reasons: list[str] = []
        if not mapping_id:
            reasons.append("mapping_id is required")
        if mapping_id in seen:
            reasons.append("mapping_id is duplicated")
        seen.add(mapping_id)
        if not observed_component_id:
            reasons.append("observed_component_id is required")
        elif observed_component_id not in observed:
            reasons.append("observed component is not present in evidence")
        else:
            missing = sorted(set(source_ids) - set(observed[observed_component_id]))
            if missing:
                reasons.append(f"source_ids are not owned by observed component: {missing}")
            if set(source_ids) != set(observed[observed_component_id]):
                reasons.append("mapping must cover all source_ids owned by the observed component")
        if not candidate_class:
            reasons.append("candidate_component_class is required")
        if not aliases:
            reasons.append("at least one candidate facility asset alias is required")
        if not evidence_refs:
            reasons.append("at least one evidence reference is required")
        review_status = str(mapping.get("review_status") or "").strip()
        facility_component_id = str(mapping.get("facility_component_id") or "").strip()
        identity_refs = _string_list(
            mapping.get("asset_identity_evidence_refs", []),
            f"mapping {mapping_id}.asset_identity_evidence_refs",
        )
        if facility_component_id:
            if review_status != "field_confirmed":
                reasons.append(
                    "facility_component_id requires review_status=field_confirmed"
                )
            if not identity_refs:
                reasons.append(
                    "field-confirmed facility_component_id requires asset identity evidence"
                )
        elif review_status not in {"candidate", "unresolved"}:
            reasons.append(
                "review_status must be candidate or unresolved when facility_component_id is absent"
            )
        status = (
            "EXACT_COMPONENT_MAPPING_NO_RELEASE"
            if facility_component_id and not reasons
            else "CANDIDATE_CLASS_MAPPING"
            if not facility_component_id and not reasons
            else "MAPPING_INPUT_INVALID"
        )
        if status == "CANDIDATE_CLASS_MAPPING":
            candidate_ids.add(observed_component_id)
        elif status == "EXACT_COMPONENT_MAPPING_NO_RELEASE":
            exact_ids.add(observed_component_id)
        else:
            blocking_reasons.extend(reasons)
        rows.append({
            "mapping_id": mapping_id,
            "observed_component_id": observed_component_id,
            "source_ids": source_ids,
            "candidate_component_class": candidate_class,
            "candidate_facility_asset_aliases": aliases,
            "facility_component_id": facility_component_id or None,
            "review_status": review_status,
            "status": status,
            "evidence_refs": evidence_refs,
            "asset_identity_evidence_refs": identity_refs,
            "mapping_basis": str(mapping.get("mapping_basis") or "").strip(),
            "blocking_reasons": list(dict.fromkeys(reasons)),
        })

    missing_components = sorted(set(observed) - {row["observed_component_id"] for row in rows})
    extra_components = sorted({row["observed_component_id"] for row in rows} - set(observed))
    if missing_components:
        blocking_reasons.append(f"observed components have no candidate mapping: {missing_components}")
    if extra_components:
        blocking_reasons.append(f"mapping contains components absent from evidence: {extra_components}")
    if len(rows) != len(observed):
        blocking_reasons.append("mapping manifest must contain exactly one row per observed component")
    complete_mapping = (
        not blocking_reasons
        and len(candidate_ids) + len(exact_ids) == len(observed)
        and all(
            row["status"]
            in {"CANDIDATE_CLASS_MAPPING", "EXACT_COMPONENT_MAPPING_NO_RELEASE"}
            for row in rows
        )
    )
    if complete_mapping and exact_ids and not candidate_ids:
        status = "EXACT_COMPONENT_MAPPINGS_NO_RELEASE"
        blocking_reasons = ["provider release event binding remains separate and empty"]
    elif complete_mapping and candidate_ids and exact_ids:
        status = "MIXED_COMPONENT_MAPPINGS_NO_RELEASE"
        blocking_reasons = [
            "some exact facility asset identities remain unresolved",
            "provider release event binding remains separate and empty",
        ]
    elif complete_mapping:
        status = "CANDIDATE_COMPONENT_CLASS_MAPPINGS_ONLY"
        blocking_reasons = [
            "exact facility asset identity is unresolved",
            "provider release event binding remains separate and empty",
        ]
    else:
        status = "PARTIAL_OR_INVALID_COMPONENT_MAPPINGS"
    return {
        "schema": SCHEMA,
        "status": status,
        "observed_state_status": observed_state_evidence.get("status"),
        "observed_component_count": len(observed),
        "candidate_mapping_count": len(candidate_ids),
        "exact_facility_component_count": len(exact_ids),
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "policy": {
            "state_data_are_not_accident_sources": True,
            "candidate_class_mapping_is_not_asset_identity": not bool(exact_ids),
            "field_confirmed_asset_identity_is_not_release_evidence": True,
            "release_event_binding_is_not_created": True,
            "frequency_is_not_assigned": True,
            "facility_ir_fn_promotion": False,
            "diagnostic_only": True,
        },
    }


__all__ = ["EVIDENCE_SCHEMA", "MANIFEST_SCHEMA", "SCHEMA", "audit_observed_component_mapping"]
