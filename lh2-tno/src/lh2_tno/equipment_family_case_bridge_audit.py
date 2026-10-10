"""Audit the bridge from generic equipment scenario coverage to facility cases.

The equipment scenario catalogue and the facility release worklist answer
different questions.  This audit joins them by explicit ``asset_id`` and
``scenario_families`` so that a case outside the declared generic scope is
visible.  It does not infer an asset kind, create a release, assign a
frequency, or promote facility QRA evidence.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


AUDIT_SCHEMA = "prism.equipment_family_case_bridge_audit.v1"
COVERAGE_SCHEMA = "prism.equipment_scenario_coverage_audit.v1"
WORKLIST_SCHEMA = "prism.release_closure_worklist.v1"


class EquipmentFamilyCaseBridgeAuditError(ValueError):
    """Raised when a bridge audit input is malformed."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EquipmentFamilyCaseBridgeAuditError(f"{label} must be an object")
    return value


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EquipmentFamilyCaseBridgeAuditError(f"{label} must be an array")
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise EquipmentFamilyCaseBridgeAuditError(f"{label}[{index}] must be an object")
        result.append(row)
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EquipmentFamilyCaseBridgeAuditError(f"{label} must be a non-empty string")
    return value.strip()


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EquipmentFamilyCaseBridgeAuditError(f"{label} must be an array")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_text(item, f"{label}[{index}]"))
    return list(dict.fromkeys(result))


def audit_equipment_family_case_bridge(
    equipment_scenario_coverage: Mapping[str, Any],
    release_closure_worklist: Mapping[str, Any],
) -> dict[str, Any]:
    """Join declared generic assets/families to case-level release worklist rows."""
    coverage = _object(equipment_scenario_coverage, "equipment_scenario_coverage")
    worklist = _object(release_closure_worklist, "release_closure_worklist")
    if coverage.get("schema_version") != COVERAGE_SCHEMA:
        raise EquipmentFamilyCaseBridgeAuditError(
            f"equipment_scenario_coverage must be {COVERAGE_SCHEMA}"
        )
    if worklist.get("schema_version") != WORKLIST_SCHEMA:
        raise EquipmentFamilyCaseBridgeAuditError(
            f"release_closure_worklist must be {WORKLIST_SCHEMA}"
        )

    assets = _rows(coverage.get("assets"), "equipment_scenario_coverage.assets")
    families = _rows(
        coverage.get("scenario_families"),
        "equipment_scenario_coverage.scenario_families",
    )
    cases = _rows(worklist.get("cases"), "release_closure_worklist.cases")

    asset_ids: list[str] = []
    asset_by_id: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(assets):
        asset_id = _text(row.get("asset_id"), f"coverage.assets[{index}].asset_id")
        if asset_id in asset_by_id:
            raise EquipmentFamilyCaseBridgeAuditError(f"duplicate coverage asset_id: {asset_id}")
        asset_ids.append(asset_id)
        asset_by_id[asset_id] = row

    family_by_name: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(families):
        family = _text(row.get("family"), f"coverage.scenario_families[{index}].family")
        if family in family_by_name:
            raise EquipmentFamilyCaseBridgeAuditError(f"duplicate scenario family: {family}")
        applicable = _strings(
            row.get("applicable_asset_ids", []),
            f"coverage.scenario_families[{index}].applicable_asset_ids",
        )
        family_by_name[family] = {**row, "applicable_asset_ids": applicable}

    case_rows: list[dict[str, Any]] = []
    case_asset_ids: set[str] = set()
    family_cases: dict[str, list[dict[str, Any]]] = {family: [] for family in family_by_name}
    asset_cases: dict[str, list[dict[str, Any]]] = {asset_id: [] for asset_id in asset_by_id}
    blockers: list[str] = []
    duplicate_case_ids: set[str] = set()
    seen_case_ids: set[str] = set()

    for index, raw in enumerate(cases):
        case_id = str(raw.get("request_id") or raw.get("case_id") or f"case-{index}")
        asset_id = _text(raw.get("asset_id"), f"worklist.cases[{index}].asset_id")
        raw_families = _strings(raw.get("scenario_families", []), f"worklist.cases[{index}].scenario_families")
        gaps = _strings(raw.get("closure_gaps", []), f"worklist.cases[{index}].closure_gaps")
        if case_id in seen_case_ids:
            duplicate_case_ids.add(case_id)
        seen_case_ids.add(case_id)
        case_asset_ids.add(asset_id)
        family_mismatches: list[str] = []
        if asset_id not in asset_by_id:
            family_mismatches.append("case asset is absent from equipment scenario coverage")
        for family in raw_families:
            family_row = family_by_name.get(family)
            if family_row is None:
                family_mismatches.append(f"case family is absent from scenario coverage: {family}")
            elif asset_id not in family_row["applicable_asset_ids"]:
                family_mismatches.append(
                    f"case asset {asset_id} is not declared applicable to family {family}"
                )
        if family_mismatches:
            blockers.extend(f"{case_id}: {reason}" for reason in family_mismatches)
        normalized = {
            "case_id": case_id,
            "event_id": raw.get("event_id"),
            "asset_id": asset_id,
            "scenario_families": raw_families,
            "closure_status": raw.get("closure_status"),
            "closure_gaps": gaps,
            "scope_status": "BOUND_TO_DECLARED_SCOPE" if not family_mismatches else "SCOPE_MISMATCH",
            "scope_blocking_reasons": family_mismatches,
        }
        case_rows.append(normalized)
        if asset_id in asset_cases:
            asset_cases[asset_id].append(normalized)
        for family in raw_families:
            if family in family_cases:
                family_cases[family].append(normalized)

    if duplicate_case_ids:
        blockers.append("duplicate case identifiers: " + ", ".join(sorted(duplicate_case_ids)))

    case_asset_ids_outside_scope = sorted(case_asset_ids - set(asset_by_id))
    coverage_assets_without_cases: list[str] = []
    asset_rows: list[dict[str, Any]] = []
    for asset_id in asset_ids:
        coverage_families = _strings(
            asset_by_id[asset_id].get("scenario_families", []),
            f"coverage.assets[{asset_id}].scenario_families",
        )
        rows = asset_cases[asset_id]
        case_families = sorted({family for row in rows for family in row["scenario_families"]})
        missing_families = sorted(set(coverage_families) - set(case_families))
        if not rows:
            coverage_assets_without_cases.append(asset_id)
        gap_counts = Counter(gap for row in rows for gap in row["closure_gaps"])
        asset_rows.append({
            "asset_id": asset_id,
            "component_kind": asset_by_id[asset_id].get("component_kind"),
            "coverage_families": coverage_families,
            "case_count": len(rows),
            "case_families": case_families,
            "coverage_families_without_case": missing_families,
            "closure_gap_counts": dict(sorted(gap_counts.items())),
            "scope_status": (
                "NO_CASES_FOR_DECLARED_ASSET" if not rows
                else "PARTIAL_FAMILY_CASE_COVERAGE" if missing_families
                else "CASE_BOUND_TO_ASSET"
            ),
        })

    family_rows: list[dict[str, Any]] = []
    for family, family_row in family_by_name.items():
        rows = family_cases[family]
        applicable = list(family_row["applicable_asset_ids"])
        case_assets = sorted({row["asset_id"] for row in rows})
        assets_without_case = sorted(set(applicable) - set(case_assets))
        case_assets_outside = sorted(set(case_assets) - set(applicable))
        gap_counts = Counter(gap for row in rows for gap in row["closure_gaps"])
        family_scope_mismatch = bool(case_assets_outside or any(
            row["scope_status"] == "SCOPE_MISMATCH" for row in rows
        ))
        if family_scope_mismatch:
            family_status = "CASE_SCOPE_MISMATCH"
        elif not rows:
            family_status = "NO_CASES_FOR_DECLARED_FAMILY"
        elif assets_without_case:
            family_status = "PARTIAL_ASSET_CASE_COVERAGE"
        else:
            family_status = "CASE_BOUND_RELEASE_CLOSURE_OPEN"
        family_rows.append({
            "family": family,
            "applicable_asset_ids": applicable,
            "case_count": len(rows),
            "case_asset_ids": case_assets,
            "applicable_assets_without_case": assets_without_case,
            "case_assets_outside_family_scope": case_assets_outside,
            "closure_gap_counts": dict(sorted(gap_counts.items())),
            "status": family_status,
        })
        if assets_without_case:
            blockers.append(
                f"family {family} has declared assets without a worklist case: "
                + ", ".join(assets_without_case)
            )
        if case_assets_outside:
            blockers.append(
                f"family {family} has cases on undeclared assets: "
                + ", ".join(case_assets_outside)
            )

    if case_asset_ids_outside_scope:
        blockers.append(
            "case assets absent from equipment scenario coverage: "
            + ", ".join(case_asset_ids_outside_scope)
        )

    blockers = list(dict.fromkeys(blockers))
    scope_mismatch_case_count = sum(row["scope_status"] == "SCOPE_MISMATCH" for row in case_rows)
    status = (
        "CASE_SCOPE_MISMATCH_RELEASE_CLOSURE_OPEN"
        if blockers
        else "CASE_BOUND_RELEASE_CLOSURE_OPEN"
    )
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "scope": "generic LH2 equipment-to-facility-case bridge; diagnostic only",
        "coverage_record": coverage.get("_record_path"),
        "worklist_record": worklist.get("_record_path"),
        "asset_count": len(asset_by_id),
        "case_count": len(case_rows),
        "case_asset_count": len(case_asset_ids),
        "case_assets_outside_scope": case_asset_ids_outside_scope,
        "scope_mismatch_case_count": scope_mismatch_case_count,
        "coverage_assets_without_cases": coverage_assets_without_cases,
        "scenario_family_count": len(family_by_name),
        "families_with_cases": sum(bool(rows) for rows in family_cases.values()),
        "families_without_cases": sum(not rows for rows in family_cases.values()),
        "assets": asset_rows,
        "scenario_families": family_rows,
        "cases": case_rows,
        "release_closure_gap_counts": dict(sorted(Counter(
            gap for row in case_rows for gap in row["closure_gaps"]
        ).items())),
        "blocking_reasons": blockers,
        "promotion_gates": {
            "equipment_case_bridge_allowed": not blockers,
            "release_boundary_promotion_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "diagnostic_only": True,
        "policy": {
            "case_asset_identity_is_never_inferred": True,
            "case_family_identity_is_never_inferred": True,
            "scope_mismatch_does_not_create_zero_case": True,
            "bridge_does_not_create_release_or_frequency": True,
            "release_closure_is_reported_separately": True,
            "facility_qra_requires_scope_and_release_closure": True,
        },
        "required_next_evidence": [
            "explicit crosswalk for every case asset, including vertical handoff and inventory-depletion branches",
            "reviewed P&ID accident port for every mapped case asset",
            "provider release packet with duration, isolation, inventory and mass balance",
            "independent holdout consequence comparison",
        ],
    }


__all__ = [
    "AUDIT_SCHEMA",
    "EquipmentFamilyCaseBridgeAuditError",
    "audit_equipment_family_case_bridge",
]
