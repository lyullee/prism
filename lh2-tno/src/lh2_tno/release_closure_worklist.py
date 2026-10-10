"""Build a case-level release-boundary closure worklist.

The facility ledger already tells us which cases were run.  This module makes
the remaining release-boundary evidence explicit: termination, isolation,
inventory and mass closure are reported separately for every case.  It is a
diagnostic accounting artifact only.  It never repairs a ledger, infers a
duration, learns a frequency, or promotes a case to qualified QRA evidence.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import math
from typing import Any


SCHEMA = "prism.release_closure_worklist.v1"
MASS_RESIDUAL_TOLERANCE_KG = 1.0e-8

_ISOLATION_REQUIREMENTS = (
    "reviewed isolation response status, trigger, actuation delay and final valve states",
    "provider-owned isolation coverage for every connected inventory path",
)
_INVENTORY_REQUIREMENTS = (
    "initial and final inventory with a positive threshold or an explicitly reviewed residual",
    "inventory clock and termination basis tied to the provider time history",
)
_MASS_REQUIREMENTS = (
    "end-to-end hydrogen mass and energy closure residuals with units and tolerances",
)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        result.append(row)
    return result


def _identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("event_id", "")),
        str(row.get("annual_condition_id", "")),
        str(row.get("release_branch_id", "")),
    )


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _as_list(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return list(value)


def _requirements_for_case(
    request: Mapping[str, Any] | None,
    *,
    gaps: Sequence[str],
) -> list[str]:
    requirements: list[str] = []
    if request is not None:
        requirements.extend(str(item) for item in _as_list(request.get("required_provider_evidence")))
    gap_set = set(gaps)
    if "ISOLATION_OPEN" in gap_set:
        requirements.extend(_ISOLATION_REQUIREMENTS)
    if "INVENTORY_CLOSURE_OPEN" in gap_set:
        requirements.extend(_INVENTORY_REQUIREMENTS)
    if "MASS_CLOSURE_OPEN" in gap_set:
        requirements.extend(_MASS_REQUIREMENTS)
    if "TERMINATION_OPEN" in gap_set:
        requirements.append("explicit provider termination clock and reviewed termination basis")
    return list(dict.fromkeys(requirements))


def _case_closure(
    row: Mapping[str, Any],
    request: Mapping[str, Any] | None,
) -> dict[str, Any]:
    status = str(row.get("status", "UNSPECIFIED"))
    termination = row.get("termination")
    termination = termination if isinstance(termination, Mapping) else {}
    domain = row.get("domain_assessment")
    domain = domain if isinstance(domain, Mapping) else {}
    mass = row.get("mass_ledger")
    mass = mass if isinstance(mass, Mapping) else {}
    provider = row.get("provider")
    provider = provider if isinstance(provider, Mapping) else {}

    available_mass = _as_list(provider.get("available_mass_kg"))
    cumulative_mass_out = _as_list(provider.get("cumulative_mass_out_kg"))
    residual_mass = _as_list(provider.get("residual_mass_kg"))
    provider_available_mass_kg = (
        available_mass[0] if available_mass and _finite_number(available_mass[0]) else None
    )
    provider_cumulative_mass_out_kg = (
        cumulative_mass_out[-1]
        if cumulative_mass_out and _finite_number(cumulative_mass_out[-1])
        else None
    )
    provider_residual_mass_kg = (
        residual_mass[-1] if residual_mass and _finite_number(residual_mass[-1]) else None
    )
    provider_inventory_balance_residual_kg = None
    if (
        _finite_number(provider_available_mass_kg)
        and _finite_number(provider_cumulative_mass_out_kg)
        and _finite_number(provider_residual_mass_kg)
    ):
        provider_inventory_balance_residual_kg = (
            float(provider_available_mass_kg)
            - float(provider_cumulative_mass_out_kg)
            - float(provider_residual_mass_kg)
        )

    gaps: list[str] = []
    if status in {"UNCOMPUTED", "FAILED"}:
        gaps.append("NUMERICAL_CASE_MISSING")

    basis = termination.get("basis")
    if not isinstance(basis, str) or not basis.strip() or basis == "synthetic_diagnostic_horizon":
        gaps.append("TERMINATION_OPEN")

    isolation = str(row.get("isolation_status", "not_declared"))
    if isolation in {"not_declared", "unknown", "unreviewed", ""}:
        gaps.append("ISOLATION_OPEN")

    residual = mass.get("end_to_end_residual_kg")
    if not _finite_number(residual) or abs(float(residual)) > MASS_RESIDUAL_TOLERANCE_KG:
        gaps.append("MASS_CLOSURE_OPEN")

    if domain.get("domain_truncated") is True or domain.get("inventory_outside_domain") is True:
        gaps.append("DOMAIN_CLOSURE_OPEN")

    inventory_status = str(row.get("inventory_status", "not_declared"))
    if inventory_status in {"not_declared", "unknown", ""}:
        gaps.append("INVENTORY_CLOSURE_OPEN")
    if basis == "inventory_depletion":
        if not _finite_number(provider_residual_mass_kg):
            gaps.append("INVENTORY_CLOSURE_OPEN")
        elif abs(float(provider_residual_mass_kg)) > MASS_RESIDUAL_TOLERANCE_KG:
            gaps.append("INVENTORY_CLOSURE_OPEN")
        if (
            provider_inventory_balance_residual_kg is None
            or abs(float(provider_inventory_balance_residual_kg))
            > MASS_RESIDUAL_TOLERANCE_KG
        ):
            gaps.append("INVENTORY_CLOSURE_OPEN")

    # Operator-limited and domain-incomplete rows are numerically useful, but
    # their provider qualification remains withheld until the exact packet is
    # independently reviewed.
    if status.startswith("EXECUTED_") or (
        request is not None and request.get("qualification_required") is True
    ):
        gaps.append("PROVIDER_QUALIFICATION_OPEN")

    gaps = list(dict.fromkeys(gaps))
    if "NUMERICAL_CASE_MISSING" in gaps:
        closure_status = "NUMERICAL_CASE_MISSING"
    elif "MASS_CLOSURE_OPEN" in gaps:
        closure_status = "MASS_CLOSURE_OPEN"
    elif "INVENTORY_CLOSURE_OPEN" in gaps:
        closure_status = "INVENTORY_CLOSURE_OPEN"
    elif "TERMINATION_OPEN" in gaps:
        closure_status = "TERMINATION_OPEN"
    elif "ISOLATION_OPEN" in gaps:
        closure_status = "ISOLATION_OPEN"
    elif "DOMAIN_CLOSURE_OPEN" in gaps:
        closure_status = "DOMAIN_CLOSURE_OPEN"
    elif "INVENTORY_CLOSURE_OPEN" in gaps:
        closure_status = "INVENTORY_CLOSURE_OPEN"
    elif "PROVIDER_QUALIFICATION_OPEN" in gaps:
        closure_status = "PROVIDER_QUALIFICATION_OPEN"
    else:
        closure_status = "READY_FOR_STRICT_REVIEW"

    request_reasons = _as_list(request.get("blocking_reasons")) if request else []
    reasons = [str(item) for item in request_reasons if str(item).strip()]
    if status.startswith("EXECUTED_"):
        reasons.append(f"current case status is {status}")
    if "TERMINATION_OPEN" in gaps:
        reasons.append("release termination is missing or synthetic")
    if "ISOLATION_OPEN" in gaps:
        reasons.append(f"isolation status is {isolation}")
    if "INVENTORY_CLOSURE_OPEN" in gaps:
        reasons.append(
            "provider inventory residual is missing, nonzero at depletion, or not mass-balanced"
        )
    if "MASS_CLOSURE_OPEN" in gaps:
        reasons.append("end-to-end mass closure residual is missing or outside tolerance")
    if "DOMAIN_CLOSURE_OPEN" in gaps:
        reasons.append("consequence domain or inventory boundary remains open")
    if "INVENTORY_CLOSURE_OPEN" in gaps:
        reasons.append(f"inventory status is {inventory_status}")
    reasons = list(dict.fromkeys(reasons))

    return {
        "closure_status": closure_status,
        "closure_gaps": gaps,
        "blocking_reasons": reasons,
        "release_boundary": {
            "termination_basis": basis,
            "termination_time_s": termination.get("time_s"),
            "termination_provenance": termination.get("provenance"),
            "isolation_status": isolation,
            "inventory_status": inventory_status,
            "end_to_end_residual_kg": residual,
            "mass_residual_tolerance_kg": MASS_RESIDUAL_TOLERANCE_KG,
            "provider_available_mass_kg": provider_available_mass_kg,
            "provider_cumulative_mass_out_kg": provider_cumulative_mass_out_kg,
            "provider_residual_mass_kg": provider_residual_mass_kg,
            "provider_inventory_balance_residual_kg": provider_inventory_balance_residual_kg,
            "provider_inventory_residual_closed": (
                basis != "inventory_depletion"
                or (
                    _finite_number(provider_residual_mass_kg)
                    and abs(float(provider_residual_mass_kg))
                    <= MASS_RESIDUAL_TOLERANCE_KG
                    and _finite_number(provider_inventory_balance_residual_kg)
                    and abs(float(provider_inventory_balance_residual_kg))
                    <= MASS_RESIDUAL_TOLERANCE_KG
                )
            ),
            "domain_truncated": domain.get("domain_truncated"),
            "inventory_outside_domain": domain.get("inventory_outside_domain"),
            "provider_packet_consumed": provider.get("packet_consumed"),
            "provider_termination_matches_request": row.get("provider_termination_matches_request"),
        },
        "required_provider_evidence": _requirements_for_case(request, gaps=gaps),
    }


def build_release_closure_worklist(
    facility_assessment: Mapping[str, Any],
    facility_evidence_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one actionable release-closure row for every facility case.

    The source rows are copied as observations.  The only calculated values
    are gap classifications and counts, so a missing field can never be
    mistaken for a successful release boundary.
    """
    assessment = _mapping(facility_assessment, "facility_assessment")
    ledger = _mapping(
        assessment.get("release_termination_inventory_ledger"),
        "facility_assessment.release_termination_inventory_ledger",
    )
    source_rows = _rows(ledger.get("rows", ()), "release_termination_inventory_ledger.rows")

    requests_by_key: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    if facility_evidence_request is not None:
        request_root = _mapping(facility_evidence_request, "facility_evidence_request")
        for request in _rows(request_root.get("case_requests", ()), "facility_evidence_request.case_requests"):
            requests_by_key[_identity(request)] = request

    cases: list[dict[str, Any]] = []
    for row in sorted(source_rows, key=_identity):
        request = requests_by_key.get(_identity(row))
        closure = _case_closure(row, request)
        identity = row.get("provider") if isinstance(row.get("provider"), Mapping) else {}
        cases.append(
            {
                "request_id": (
                    request.get("request_id")
                    if request is not None
                    else "/".join(_identity(row))
                ),
                "event_id": row.get("event_id"),
                "asset_id": row.get("asset_id"),
                "component_id": (
                    identity.get("component_id")
                    or (request.get("component_id") if request is not None else None)
                    or row.get("component_id")
                ),
                "release_branch_id": row.get("release_branch_id"),
                "annual_condition_id": row.get("annual_condition_id"),
                "scenario_families": list(request.get("scenario_families", ()))
                if request is not None
                else [],
                "current_status": row.get("status"),
                "initiating_frequency_per_year": row.get("initiating_frequency_per_year"),
                "release_branch_probability": row.get("release_branch_probability"),
                "isolation_status": row.get("isolation_status"),
                "inventory_status": row.get("inventory_status"),
                "provider_packet_identity_present": bool(identity),
                **closure,
            }
        )

    status_counts = Counter(str(row["closure_status"]) for row in cases)
    gap_counts = Counter(
        str(gap)
        for row in cases
        for gap in row["closure_gaps"]
    )
    basis_counts = Counter(
        str(row["release_boundary"].get("termination_basis", "not_declared"))
        for row in cases
    )
    isolation_counts = Counter(str(row["release_boundary"].get("isolation_status", "not_declared")) for row in cases)
    inventory_counts = Counter(str(row["release_boundary"].get("inventory_status", "not_declared")) for row in cases)
    open_cases = [row for row in cases if row["closure_status"] != "READY_FOR_STRICT_REVIEW"]
    return {
        "schema_version": SCHEMA,
        "facility_id": assessment.get("facility_id"),
        "status": "CLOSED_DIAGNOSTIC_BOUNDARY_WORKLIST" if not open_cases else "OPEN_RELEASE_CLOSURE_WORKLIST",
        "case_count": len(cases),
        "open_case_count": len(open_cases),
        "summary": {
            "closure_status_counts": dict(sorted(status_counts.items())),
            "closure_gap_counts": dict(sorted(gap_counts.items())),
            "termination_basis_counts": dict(sorted(basis_counts.items())),
            "isolation_status_counts": dict(sorted(isolation_counts.items())),
            "inventory_status_counts": dict(sorted(inventory_counts.items())),
            "provider_packet_required_case_count": sum(
                1 for row in cases if "PROVIDER_QUALIFICATION_OPEN" in row["closure_gaps"]
            ),
            "mass_closure_open_case_count": gap_counts.get("MASS_CLOSURE_OPEN", 0),
            "isolation_open_case_count": gap_counts.get("ISOLATION_OPEN", 0),
            "termination_open_case_count": gap_counts.get("TERMINATION_OPEN", 0),
            "inventory_closure_open_case_count": gap_counts.get("INVENTORY_CLOSURE_OPEN", 0),
        },
        "promotion_gates": {
            "release_boundary_promotion_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "physical_validation_claim": False,
            "diagnostic_only": True,
        },
        "source_semantics": {
            "duration_is_not_inferred": True,
            "isolation_is_not_inferred": True,
            "inventory_depletion_is_not_inferred": True,
            "mass_residual_tolerance_kg": MASS_RESIDUAL_TOLERANCE_KG,
        },
        "cases": cases,
    }


__all__ = ["SCHEMA", "MASS_RESIDUAL_TOLERANCE_KG", "build_release_closure_worklist"]
