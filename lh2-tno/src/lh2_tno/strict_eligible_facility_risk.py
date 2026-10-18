"""Export the strict-eligible subset of a conditional facility ledger.

This view is deliberately smaller than the conditional facility view.  It keeps
only risk atoms whose case was executed and was not withheld from strict
facility QRA.  The result is useful for review and ranking, but it is still a
diagnostic contribution, not a promoted facility QRA result.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


STRICT_ELIGIBLE_FACILITY_RISK_SCHEMA = "prism.strict_eligible_facility_risk.v1"


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _atoms(campaign_result: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    raw = campaign_result.get("risk_atoms")
    if not isinstance(raw, list):
        ledger = campaign_result.get("facility_risk_ledger")
        raw = ledger.get("risk_atoms") if isinstance(ledger, Mapping) else None
    if not isinstance(raw, list):
        raise ValueError("campaign_result.risk_atoms must be an array")
    selected: list[Mapping[str, Any]] = []
    excluded: dict[str, int] = {}
    for index, atom in enumerate(raw):
        if not isinstance(atom, Mapping):
            raise ValueError(f"risk_atoms[{index}] must be an object")
        status = str(atom.get("case_status", "UNSPECIFIED"))
        withheld = atom.get("case_withheld_from_strict_facility_qra")
        eligibility = atom.get("risk_atom_eligibility")
        if status == "EXECUTED" and withheld is False and eligibility == "ELIGIBLE_FOR_NUMERICAL_SCOPE":
            selected.append(atom)
        else:
            reason = f"status={status};withheld={withheld};eligibility={eligibility}"
            excluded[reason] = excluded.get(reason, 0) + 1
    return selected, excluded


def _aggregate_ir(atoms: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for index, atom in enumerate(atoms):
        frequency = atom.get("initiating_frequency_per_year")
        weight = atom.get("conditional_weight")
        harm = atom.get("receptor_harm_low_high")
        if not _finite(frequency) or not _finite(weight) or not isinstance(harm, Mapping):
            raise ValueError(f"risk_atoms[{index}] lacks finite frequency/weight/harm")
        for receptor, endpoints in harm.items():
            if not isinstance(endpoints, Sequence) or isinstance(endpoints, (str, bytes)) or len(endpoints) != 2 or not all(_finite(v) for v in endpoints):
                raise ValueError(f"risk_atoms[{index}] has invalid harm endpoints")
            values = result.setdefault(str(receptor), [0.0, 0.0])
            values[0] += float(frequency) * float(weight) * float(endpoints[0])
            values[1] += float(frequency) * float(weight) * float(endpoints[1])
    return result


def _fn_curve(atoms: Sequence[Mapping[str, Any]], endpoint: int) -> dict[str, list[float]]:
    rows: list[tuple[float, float]] = []
    for index, atom in enumerate(atoms):
        frequency = atom.get("initiating_frequency_per_year")
        weight = atom.get("conditional_weight")
        deaths = atom.get("expected_deaths_low_high")
        if not _finite(frequency) or not _finite(weight) or not isinstance(deaths, Sequence) or isinstance(deaths, (str, bytes)) or len(deaths) != 2 or not all(_finite(v) for v in deaths):
            raise ValueError(f"risk_atoms[{index}] lacks finite frequency/weight/deaths")
        rows.append((float(deaths[endpoint]), float(frequency) * float(weight)))
    levels = sorted({deaths for deaths, _ in rows if deaths >= 1.0})
    return {"expected_deaths": levels, "cumulative_frequency_per_year": [sum(freq for deaths, freq in rows if deaths >= level) for level in levels]}


def build_strict_eligible_facility_risk_view(campaign_result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a transparent, strict-eligible diagnostic contribution."""
    if not isinstance(campaign_result, Mapping):
        raise ValueError("campaign_result must be an object")
    selected, excluded = _atoms(campaign_result)
    return {
        "schema_version": STRICT_ELIGIBLE_FACILITY_RISK_SCHEMA,
        "status": "STRICT_ELIGIBLE_DIAGNOSTIC_FACILITY_RISK",
        "facility_id": campaign_result.get("facility_id"),
        "source_status": campaign_result.get("status"),
        "source_assessment_digest": campaign_result.get("assessment_digest"),
        "selected_risk_atom_count": len(selected),
        "source_risk_atom_count": sum(excluded.values()) + len(selected),
        "excluded_risk_atom_count": sum(excluded.values()),
        "excluded_atom_reasons": excluded,
        "annual_ir_low_high": _aggregate_ir(selected),
        "expected_death_fn_low_high": [_fn_curve(selected, endpoint) for endpoint in range(2)],
        "facility_qra_promotion": False,
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "interpretation": (
            "Contribution from executed, non-withheld risk atoms only. Excluded atoms are shown "
            "explicitly; this view must not be interpreted as complete facility QRA."
        ),
    }


__all__ = ["STRICT_ELIGIBLE_FACILITY_RISK_SCHEMA", "build_strict_eligible_facility_risk_view"]
