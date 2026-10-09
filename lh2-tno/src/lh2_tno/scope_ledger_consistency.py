"""Compare a declared accident scope matrix with a facility risk ledger.

Scope matrices may be assembled from several campaign snapshots while the
facility ledger is assembled from the campaign results actually merged.  This
audit makes that distinction explicit.  It never repairs IDs, assigns missing
families, or opens a facility QRA claim.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "prism.scope_ledger_consistency.v1"


def _as_rows(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"{name} must be an array of objects")
    return [dict(row) for row in value]


def _case_family_index(cases: list[dict[str, Any]]) -> tuple[
    dict[str, set[str]], dict[str, list[dict[str, Any]]], int
]:
    event_ids_by_family: dict[str, set[str]] = defaultdict(set)
    cases_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unattributed = 0
    for case in cases:
        event_id = str(case.get("event_id", ""))
        raw_families = case.get("scenario_families")
        families = (
            tuple(str(family) for family in raw_families)
            if isinstance(raw_families, list)
            else ()
        )
        if not families:
            unattributed += 1
            continue
        for family in families:
            cases_by_family[family].append(case)
            if event_id:
                event_ids_by_family[family].add(event_id)
    return dict(event_ids_by_family), dict(cases_by_family), unattributed


def audit_scope_ledger_consistency(
    scope_matrix: Mapping[str, Any],
    facility_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed comparison of scope rows and ledger accounting."""
    if not isinstance(scope_matrix, Mapping) or not isinstance(facility_ledger, Mapping):
        raise ValueError("scope matrix and facility ledger must be objects")
    scope_rows = _as_rows(scope_matrix.get("rows"), "scope matrix rows")
    ledger_events = _as_rows(facility_ledger.get("events"), "facility ledger events")
    ledger_cases = _as_rows(facility_ledger.get("cases"), "facility ledger cases")
    scope_by_family: dict[str, dict[str, Any]] = {}
    duplicate_scope_families: list[str] = []
    for row in scope_rows:
        family = str(row.get("family", ""))
        if not family:
            raise ValueError("scope matrix row is missing family")
        if family in scope_by_family:
            duplicate_scope_families.append(family)
        scope_by_family[family] = row

    scope_event_ids = {
        str(event_id)
        for row in scope_rows
        for event_id in row.get("event_ids", [])
        if event_id
    }
    ledger_event_ids = {
        str(event.get("id")) for event in ledger_events if event.get("id")
    }
    ledger_event_ids_by_family, ledger_cases_by_family, unattributed_case_count = (
        _case_family_index(ledger_cases)
    )
    families = tuple(dict.fromkeys(
        [str(family) for family in scope_matrix.get("required_families", [])]
        + list(scope_by_family)
        + list(ledger_cases_by_family)
    ))
    family_rows: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    for family in families:
        scope = scope_by_family.get(family, {})
        ledger_family_cases = ledger_cases_by_family.get(family, [])
        scope_ids = {
            str(event_id) for event_id in scope.get("event_ids", []) if event_id
        }
        ledger_ids = ledger_event_ids_by_family.get(family, set())
        scope_case_count = int(scope.get("case_count", 0))
        scope_conditional_executed = int(scope.get("conditional_executed_case_count", 0))
        scope_conditional_uncomputed = int(scope.get("conditional_uncomputed_case_count", 0))
        ledger_conditional_executed = sum(
            str(case.get("status", "")).startswith("EXECUTED")
            for case in ledger_family_cases
        )
        ledger_conditional_uncomputed = len(ledger_family_cases) - ledger_conditional_executed
        row = {
            "family": family,
            "scope_matrix_event_count": int(scope.get("generated_event_count", len(scope_ids))),
            "scope_matrix_case_count": scope_case_count,
            "scope_matrix_conditional_executed_case_count": scope_conditional_executed,
            "scope_matrix_conditional_uncomputed_case_count": scope_conditional_uncomputed,
            "ledger_event_count_from_tagged_cases": len(ledger_ids),
            "ledger_case_count_from_tagged_cases": len(ledger_family_cases),
            "ledger_conditional_executed_case_count": ledger_conditional_executed,
            "ledger_conditional_uncomputed_case_count": ledger_conditional_uncomputed,
            "scope_only_event_ids": sorted(scope_ids - ledger_event_ids),
            "ledger_only_event_ids": sorted(ledger_ids - scope_ids),
            "ledger_event_ids_without_scope_row": sorted(ledger_ids - scope_event_ids),
            "case_count_match": scope_case_count == len(ledger_family_cases),
            "conditional_execution_count_match": (
                scope_conditional_executed == ledger_conditional_executed
            ),
            "conditional_uncomputed_count_match": (
                scope_conditional_uncomputed == ledger_conditional_uncomputed
            ),
            "event_id_set_match": scope_ids == ledger_ids,
        }
        row["consistent"] = all(
            row[key]
            for key in (
                "case_count_match",
                "conditional_execution_count_match",
                "conditional_uncomputed_count_match",
                "event_id_set_match",
            )
        )
        if not row["consistent"]:
            blocking_reasons.append(f"{family}: scope row and ledger accounting disagree")
        family_rows.append(row)

    if duplicate_scope_families:
        blocking_reasons.append("scope matrix contains duplicate family rows")
    if scope_event_ids != ledger_event_ids:
        blocking_reasons.append("scope matrix and facility ledger event ID sets disagree")
    if int(scope_matrix.get("conditional_uncomputed_case_count", 0)) != int(
        facility_ledger.get("conditional_uncomputed_case_count", 0)
    ):
        blocking_reasons.append("top-level conditional uncomputed case counts disagree")
    if unattributed_case_count:
        blocking_reasons.append("facility ledger has cases without scenario-family metadata")

    consistent = not blocking_reasons
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "CONSISTENT_SCOPE_LEDGER" if consistent else "INCONSISTENT_SCOPE_LEDGER",
        "facility_id": scope_matrix.get("facility_id", facility_ledger.get("facility_id")),
        "scope_matrix_status": scope_matrix.get("matrix_complete"),
        "scope_matrix_conditional_chain_complete": scope_matrix.get("conditional_chain_complete"),
        "facility_ledger_status": facility_ledger.get("status"),
        "scope_matrix_event_count": len(scope_event_ids),
        "facility_ledger_event_count": len(ledger_event_ids),
        "scope_matrix_case_count": sum(int(row.get("case_count", 0)) for row in scope_rows),
        "facility_ledger_case_count": int(facility_ledger.get("case_count", len(ledger_cases))),
        "scope_matrix_conditional_uncomputed_case_count": int(
            scope_matrix.get("conditional_uncomputed_case_count", 0)
        ),
        "facility_ledger_conditional_uncomputed_case_count": int(
            facility_ledger.get(
                "conditional_uncomputed_case_count",
                sum(not str(case.get("status", "")).startswith("EXECUTED") for case in ledger_cases),
            )
        ),
        "scope_only_event_ids": sorted(scope_event_ids - ledger_event_ids),
        "ledger_only_event_ids": sorted(ledger_event_ids - scope_event_ids),
        "unattributed_ledger_case_count": unattributed_case_count,
        "duplicate_scope_families": sorted(set(duplicate_scope_families)),
        "families": family_rows,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "facility_qra_claim": False,
        "interpretation": (
            "The audit compares declared scope with the merged ledger; it never "
            "renames event IDs, infers missing families, or promotes facility IR/F-N."
        ),
    }


__all__ = ["SCHEMA_VERSION", "audit_scope_ledger_consistency"]
