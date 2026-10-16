"""Independently audit equipment-level contributions in a facility ledger.

The campaign already stores a component contribution table and a diagnostic
risk ranking.  This module rebuilds both views from the saved risk atoms.  It
is deliberately fail-closed and diagnostic-only: it does not fill missing
equipment cases, reallocate frequencies, or promote a facility QRA claim.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import math
from typing import Any


FACILITY_COMPONENT_AUDIT_SCHEMA = "prism.facility_component_contribution_audit.v1"


class FacilityComponentContributionAuditError(ValueError):
    """Raised when a campaign cannot be audited safely."""


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise FacilityComponentContributionAuditError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise FacilityComponentContributionAuditError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _same_number(left: Any, right: Any, *, rel_tol: float = 1.0e-8, abs_tol: float = 1.0e-12) -> bool:
    return _finite(left) and _finite(right) and math.isclose(
        float(left), float(right), rel_tol=rel_tol, abs_tol=abs_tol
    )


def _endpoint_curve(atoms: Sequence[Mapping[str, Any]], endpoint: int) -> dict[str, list[float]]:
    outcomes: list[tuple[float, float]] = []
    for index, atom in enumerate(atoms):
        frequency = atom.get("initiating_frequency_per_year")
        weight = atom.get("conditional_weight")
        deaths = atom.get("expected_deaths_low_high")
        if (
            not _finite(frequency)
            or not _finite(weight)
            or not isinstance(deaths, Sequence)
            or isinstance(deaths, (str, bytes))
            or len(deaths) != 2
            or not all(_finite(value) for value in deaths)
        ):
            raise FacilityComponentContributionAuditError(
                f"risk_atoms[{index}] lacks finite frequency/weight/death endpoints"
            )
        outcomes.append((float(deaths[endpoint]), float(frequency) * float(weight)))
    levels = sorted({deaths for deaths, _ in outcomes if deaths >= 1.0})
    return {
        "expected_deaths": levels,
        "cumulative_frequency_per_year": [
            sum(frequency for deaths, frequency in outcomes if deaths >= level)
            for level in levels
        ],
    }


def _component_rows(atoms: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, atom in enumerate(atoms):
        identity = atom.get("provider_packet_identity")
        component_id = identity.get("component_id") if isinstance(identity, Mapping) else None
        if not isinstance(component_id, str) or not component_id:
            raise FacilityComponentContributionAuditError(
                f"risk_atoms[{index}] lacks provider_packet_identity.component_id"
            )
        grouped[component_id].append(atom)
    return dict(grouped)


def _computed_contribution(component_id: str, atoms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ir: dict[str, list[float]] = {}
    event_ids = {str(atom.get("event_id")) for atom in atoms}
    for index, atom in enumerate(atoms):
        frequency = atom.get("initiating_frequency_per_year")
        weight = atom.get("conditional_weight")
        harms = atom.get("receptor_harm_low_high")
        if not _finite(frequency) or not _finite(weight) or not isinstance(harms, Mapping):
            raise FacilityComponentContributionAuditError(
                f"risk_atoms component {component_id} row {index} lacks finite frequency/weight/harm"
            )
        for receptor_id, endpoints in harms.items():
            if (
                not isinstance(endpoints, Sequence)
                or isinstance(endpoints, (str, bytes))
                or len(endpoints) != 2
                or not all(_finite(value) for value in endpoints)
            ):
                raise FacilityComponentContributionAuditError(
                    f"risk_atoms component {component_id} receptor {receptor_id} has invalid harm endpoints"
                )
            values = ir.setdefault(str(receptor_id), [0.0, 0.0])
            values[0] += float(frequency) * float(weight) * float(endpoints[0])
            values[1] += float(frequency) * float(weight) * float(endpoints[1])
    return {
        "component_id": component_id,
        "event_count": len(event_ids),
        "risk_atom_count": len(atoms),
        "annual_ir_low_high": ir,
        "expected_death_fn_low_high": [
            _endpoint_curve(atoms, endpoint) for endpoint in range(2)
        ],
        "frequency_is_not_reallocated": True,
    }


def _compare_contribution(
    component_id: str,
    stored: Any,
    computed: Mapping[str, Any],
    *,
    partial_scope: bool = False,
) -> list[str]:
    if not isinstance(stored, Mapping):
        return [f"component {component_id} stored contribution is missing"]
    mismatches: list[str] = []
    if stored.get("event_count") != computed["event_count"]:
        stored_event_count = stored.get("event_count")
        if not (
            partial_scope
            and isinstance(stored_event_count, int)
            and stored_event_count >= computed["event_count"]
        ):
            mismatches.append(f"component {component_id} event_count differs")
    if stored.get("risk_atom_count") != computed["risk_atom_count"]:
        mismatches.append(f"component {component_id} risk_atom_count differs")
    stored_ir = stored.get("annual_ir_low_high")
    if not isinstance(stored_ir, Mapping) or set(map(str, stored_ir)) != set(computed["annual_ir_low_high"]):
        mismatches.append(f"component {component_id} annual IR receptor set differs")
    else:
        for receptor_id, values in computed["annual_ir_low_high"].items():
            left = stored_ir.get(receptor_id)
            if (
                not isinstance(left, Sequence)
                or isinstance(left, (str, bytes))
                or len(left) != 2
                or any(not _same_number(left[i], values[i]) for i in range(2))
            ):
                mismatches.append(f"component {component_id} receptor {receptor_id} annual IR differs")
    stored_fn = stored.get("expected_death_fn_low_high")
    if not isinstance(stored_fn, list) or len(stored_fn) != 2:
        mismatches.append(f"component {component_id} F/N curves are missing")
    else:
        for endpoint, expected in enumerate(computed["expected_death_fn_low_high"]):
            left = stored_fn[endpoint]
            if not isinstance(left, Mapping):
                mismatches.append(f"component {component_id} F/N endpoint {endpoint} is invalid")
                continue
            for field in ("expected_deaths", "cumulative_frequency_per_year"):
                values = left.get(field)
                right = expected[field]
                if (
                    not isinstance(values, Sequence)
                    or isinstance(values, (str, bytes))
                    or len(values) != len(right)
                    or any(not _same_number(values[i], right[i]) for i in range(len(right)))
                ):
                    mismatches.append(f"component {component_id} F/N endpoint {endpoint} {field} differs")
    if stored.get("frequency_is_not_reallocated") is not True:
        mismatches.append(f"component {component_id} frequency reallocation flag is not false")
    return mismatches


def _ranking(contributions: Mapping[str, Mapping[str, Any]]) -> list[str]:
    rows: list[tuple[str, float]] = []
    for component_id, contribution in contributions.items():
        values = contribution.get("annual_ir_low_high", {}).values()
        peak = max((float(row[1]) for row in values if isinstance(row, Sequence) and len(row) == 2), default=0.0)
        rows.append((component_id, peak))
    return [component_id for component_id, _ in sorted(rows, key=lambda item: (-item[1], item[0]))]


def build_facility_component_contribution_audit(
    campaign_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an independent equipment-level contribution and ranking audit."""
    if not isinstance(campaign_result, Mapping):
        raise FacilityComponentContributionAuditError("campaign_result must be an object")
    atoms = _rows(campaign_result.get("risk_atoms"), "campaign_result.risk_atoms")
    grouped = _component_rows(atoms)
    computed = {component_id: _computed_contribution(component_id, rows) for component_id, rows in grouped.items()}
    stored = campaign_result.get("component_contributions")
    uncomputed_cases = campaign_result.get("uncomputed_cases")
    partial_scope = (
        isinstance(uncomputed_cases, list) and bool(uncomputed_cases)
    ) or str(campaign_result.get("status", "")).startswith("PARTIAL_")
    mismatches: list[str] = []
    if not isinstance(stored, Mapping):
        mismatches.append("stored component contributions are missing")
        stored = {}
    if set(map(str, stored)) != set(computed):
        mismatches.append("stored and recomputed component sets differ")
    for component_id, contribution in computed.items():
        mismatches.extend(
            _compare_contribution(
                component_id,
                stored.get(component_id),
                contribution,
                partial_scope=partial_scope,
            )
        )
    expected_order = _ranking(computed)
    ranking = campaign_result.get("component_risk_ranking")
    stored_order = []
    if isinstance(ranking, Mapping) and isinstance(ranking.get("rows"), list):
        for row in ranking["rows"]:
            if isinstance(row, Mapping) and isinstance(row.get("component_id"), str):
                stored_order.append(row["component_id"])
        if stored_order != expected_order:
            mismatches.append("stored component risk ranking order differs")
        if ranking.get("frequency_reallocation_performed") is not False:
            mismatches.append("stored component ranking permits frequency reallocation")
        if ranking.get("facility_ir_fn_promotion") is not False:
            mismatches.append("stored component ranking permits facility IR/F-N promotion")
    else:
        mismatches.append("stored component risk ranking is missing")
    blocking = list(dict.fromkeys(mismatches))
    closed = bool(computed) and not blocking
    return {
        "schema_version": FACILITY_COMPONENT_AUDIT_SCHEMA,
        "status": (
            "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
            if closed
            else "BLOCKED_FACILITY_COMPONENT_CONTRIBUTION_AUDIT"
        ),
        "facility_id": campaign_result.get("facility_id"),
        "risk_atom_count": len(atoms),
        "component_count": len(computed),
        "component_ids": sorted(computed),
        "partial_scope": partial_scope,
        "recomputed_component_contributions": computed,
        "stored_component_contributions": campaign_result.get("component_contributions"),
        "recomputed_ranking_order": expected_order,
        "stored_ranking_order": stored_order,
        "mismatch_count": len(blocking),
        "blocking_reasons": blocking,
        "diagnostic_only": True,
        "frequency_reallocation_performed": False,
        "facility_ir_fn_promotion": False,
        "qualified_provider_packet": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "Equipment-level IR/F-N contributions and the diagnostic risk ranking are independently "
            "reproduced from risk atoms. Missing equipment cases and provider evidence remain gates."
        ),
    }


__all__ = [
    "FACILITY_COMPONENT_AUDIT_SCHEMA",
    "FacilityComponentContributionAuditError",
    "build_facility_component_contribution_audit",
]
