"""Independently audit the facility IR/F-N aggregation from risk atoms.

The facility ledger stores a conditional diagnostic IR/F-N result after it
has combined equipment campaigns.  This module recomputes those two outputs
directly from the saved risk atoms and compares the result with the stored
aggregate.  It is an accounting diagnostic only: it does not qualify a
provider packet, add missing accident families, or promote facility QRA.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


FACILITY_AGGREGATE_CLOSURE_SCHEMA = "prism.facility_aggregate_closure_audit.v1"


class FacilityAggregateClosureAuditError(ValueError):
    """Raised when a campaign result cannot be audited safely."""


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise FacilityAggregateClosureAuditError(f"{label} must be an array")
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise FacilityAggregateClosureAuditError(f"{label}[{index}] must be an object")
        result.append(row)
    return result


def _same_number(left: Any, right: Any, *, rel_tol: float = 1.0e-8, abs_tol: float = 1.0e-12) -> bool:
    return _finite(left) and _finite(right) and math.isclose(
        float(left), float(right), rel_tol=rel_tol, abs_tol=abs_tol
    )


def _aggregate_ir(atoms: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    total: dict[str, list[float]] = {}
    for index, atom in enumerate(atoms):
        frequency = atom.get("initiating_frequency_per_year")
        weight = atom.get("conditional_weight")
        harm = atom.get("receptor_harm_low_high")
        if not _finite(frequency) or not _finite(weight) or not isinstance(harm, Mapping):
            raise FacilityAggregateClosureAuditError(
                f"risk_atoms[{index}] lacks finite frequency/weight or harm mapping"
            )
        for receptor_id, endpoints in harm.items():
            if (
                not isinstance(endpoints, Sequence)
                or isinstance(endpoints, (str, bytes))
                or len(endpoints) != 2
                or not all(_finite(value) for value in endpoints)
            ):
                raise FacilityAggregateClosureAuditError(
                    f"risk_atoms[{index}] receptor {receptor_id} requires two finite harm endpoints"
                )
            values = total.setdefault(str(receptor_id), [0.0, 0.0])
            values[0] += float(frequency) * float(weight) * float(endpoints[0])
            values[1] += float(frequency) * float(weight) * float(endpoints[1])
    return total


def _fn_curve(atoms: Sequence[Mapping[str, Any]], endpoint: int) -> dict[str, list[float]]:
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
            raise FacilityAggregateClosureAuditError(
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


def _ir_mismatches(expected: Any, computed: Mapping[str, Sequence[float]]) -> list[str]:
    if not isinstance(expected, Mapping):
        return ["stored conditional diagnostic annual IR is missing"]
    mismatches: list[str] = []
    if set(str(key) for key in expected) != set(computed):
        mismatches.append("stored and recomputed IR receptor sets differ")
    for receptor_id, values in computed.items():
        stored = expected.get(receptor_id)
        if stored is None:
            stored = expected.get(str(receptor_id))
        if (
            not isinstance(stored, Sequence)
            or isinstance(stored, (str, bytes))
            or len(stored) != 2
            or any(not _same_number(stored[index], values[index]) for index in range(2))
        ):
            mismatches.append(f"receptor {receptor_id} IR differs")
    return mismatches


def _fn_mismatches(expected: Any, computed: Sequence[Mapping[str, Sequence[float]]]) -> list[str]:
    if not isinstance(expected, list) or len(expected) != 2:
        return ["stored conditional diagnostic F/N endpoints are missing"]
    mismatches: list[str] = []
    for endpoint, expected_curve in enumerate(computed):
        stored = expected[endpoint]
        if not isinstance(stored, Mapping):
            mismatches.append(f"F/N endpoint {endpoint} is not an object")
            continue
        for field in ("expected_deaths", "cumulative_frequency_per_year"):
            left = stored.get(field)
            right = expected_curve[field]
            if not isinstance(left, Sequence) or isinstance(left, (str, bytes)) or len(left) != len(right):
                mismatches.append(f"F/N endpoint {endpoint} {field} differs")
                continue
            if any(not _same_number(value, right[index]) for index, value in enumerate(left)):
                mismatches.append(f"F/N endpoint {endpoint} {field} differs")
    return mismatches


def build_facility_aggregate_closure_audit(
    campaign_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an independent IR/F-N aggregate closure record."""
    if not isinstance(campaign_result, Mapping):
        raise FacilityAggregateClosureAuditError("campaign_result must be an object")
    atoms = _rows(campaign_result.get("risk_atoms"), "campaign_result.risk_atoms")
    computed_ir = _aggregate_ir(atoms)
    computed_fn = [_fn_curve(atoms, endpoint) for endpoint in range(2)]
    ir_mismatches = _ir_mismatches(
        campaign_result.get("conditional_diagnostic_facility_annual_ir_low_high"),
        computed_ir,
    )
    fn_mismatches = _fn_mismatches(
        campaign_result.get("conditional_diagnostic_facility_expected_death_fn_low_high"),
        computed_fn,
    )
    blocking = list(dict.fromkeys(ir_mismatches + fn_mismatches))
    closed = bool(atoms) and not blocking
    return {
        "schema_version": FACILITY_AGGREGATE_CLOSURE_SCHEMA,
        "status": (
            "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC"
            if closed
            else "BLOCKED_FACILITY_IR_FN_AGGREGATE_CLOSURE"
        ),
        "facility_id": campaign_result.get("facility_id"),
        "risk_atom_count": len(atoms),
        "recomputed_annual_ir_low_high": computed_ir,
        "stored_annual_ir_low_high": campaign_result.get(
            "conditional_diagnostic_facility_annual_ir_low_high"
        ),
        "recomputed_expected_death_fn_low_high": computed_fn,
        "stored_expected_death_fn_low_high": campaign_result.get(
            "conditional_diagnostic_facility_expected_death_fn_low_high"
        ),
        "ir_mismatch_count": len(ir_mismatches),
        "fn_mismatch_count": len(fn_mismatches),
        "blocking_reasons": blocking,
        "diagnostic_only": True,
        "frequency_reallocation_performed": False,
        "qualified_provider_packet": False,
        "physical_validation_claim": False,
        "facility_total_risk_available": campaign_result.get("facility_total_risk_available") is True,
        "facility_qra_claim": campaign_result.get("complete_facility_qra_claim") is True,
        "interpretation": (
            "The stored conditional facility IR/F-N is independently reproduced from the saved "
            "risk atoms. This closes numerical aggregation for the declared diagnostic ledger; "
            "it does not close missing provider evidence, physical validation, scope, or QRA gates."
        ),
    }


__all__ = [
    "FACILITY_AGGREGATE_CLOSURE_SCHEMA",
    "FacilityAggregateClosureAuditError",
    "build_facility_aggregate_closure_audit",
]
