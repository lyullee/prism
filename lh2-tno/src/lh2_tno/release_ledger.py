"""Build an explicit release, isolation and inventory ledger for campaigns.

The consequence result contains enough information to show whether a release
history was actually consumed, but that information was previously spread over
case rows, provider identity and the mass ledger.  This module gives reviewers
one row per event/branch/annual condition.  It does not fill missing values:
an uncomputed branch remains uncomputed and an operator-limited calculation is
reported as such.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any, Mapping, Sequence


RELEASE_LEDGER_SCHEMA = "prism.release_termination_inventory_ledger.v1"
RELEASE_BOUNDARY_GATE_SCHEMA = "prism.facility_release_boundary_gate.v1"
_ALLOWED_STRICT_TERMINATION_BASES = {
    "reviewed_isolation_success",
    "inventory_depletion",
    # A pressure-relief discharge has its own provider-owned termination
    # evidence.  It is not a hole event and therefore has no isolation or
    # inventory-depletion step to declare.
    "emergency_relief_discharge",
}
_STRICT_RESIDUAL_TOLERANCE_KG = 1e-8


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _float_list(value: Any) -> list[float] | None:
    if not isinstance(value, list):
        return None
    values = [_finite(item) for item in value]
    return values if all(item is not None for item in values) else None


def _provider_mass_balances(identity: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize provider-owned mass ledgers and classify their closure."""

    raw = identity.get("provider_mass_balances")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return [], []
    rows: list[dict[str, Any]] = []
    statuses: list[str] = []
    for item in raw:
        if not isinstance(item, Mapping):
            rows.append({"raw": item})
            statuses.append("MALFORMED")
            continue
        row = dict(item)
        derived = _finite(row.get("derived_accounting_residual_kg"))
        initial = _finite(row.get("initial_mass_kg"))
        final = _finite(row.get("final_mass_kg"))
        cumulative_out = _finite(row.get("cumulative_mass_out_kg"))
        cumulative_in = _finite(row.get("cumulative_mass_in_kg")) or 0.0
        if derived is None and initial is not None and final is not None and cumulative_out is not None:
            derived = final + cumulative_out - initial - cumulative_in
            row["derived_accounting_residual_kg"] = derived
        if derived is None:
            statuses.append("PARTIAL")
        elif abs(derived) <= _STRICT_RESIDUAL_TOLERANCE_KG:
            statuses.append("CLOSED")
        else:
            statuses.append("UNBALANCED")
        rows.append(row)
    return rows, statuses


def _provider_inventory(identity: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(identity, Mapping):
        return {
            "packet_consumed": False,
            "available_mass_kg": None,
            "cumulative_mass_out_kg": None,
            "residual_mass_kg": None,
            "mass_balances": [],
            "mass_balance_statuses": [],
        }
    available = _float_list(identity.get("available_mass_kg"))
    released = _float_list(identity.get("cumulative_mass_out_kg"))
    residual = None
    if available is not None and released is not None and len(available) == len(released):
        residual = [a - r for a, r in zip(available, released)]
    mass_balances, mass_balance_statuses = _provider_mass_balances(identity)
    return {
        "packet_consumed": bool(identity.get("provider_result_digests")),
        "available_mass_kg": available,
        "cumulative_mass_out_kg": released,
        "residual_mass_kg": residual,
        "mass_balances": mass_balances,
        "mass_balance_statuses": mass_balance_statuses,
    }


def _isolation_status(termination_basis: str | None) -> str:
    if termination_basis == "reviewed_isolation_success":
        return "provider_declared_isolation_success"
    if termination_basis == "emergency_relief_discharge":
        return "not_applicable"
    return "not_declared"


def _inventory_status(termination_basis: str | None) -> str:
    if termination_basis == "inventory_depletion":
        return "provider_declared_inventory_depletion"
    if termination_basis == "inventory_over_600s":
        return "provider_declared_inventory_over_600s"
    if termination_basis == "emergency_relief_discharge":
        return "not_applicable"
    return "not_inventory_termination"


def _row(case: Mapping[str, Any]) -> dict[str, Any]:
    status = str(case.get("status", "UNKNOWN"))
    termination = case.get("termination")
    termination = termination if isinstance(termination, Mapping) else {}
    basis = termination.get("basis")
    basis = basis if isinstance(basis, str) else None
    duration = _finite(termination.get("time_s"))
    mass_ledger = case.get("mass_ledger")
    mass_ledger = mass_ledger if isinstance(mass_ledger, Mapping) else {}
    end_to_end_residual = _finite(mass_ledger.get("end_to_end_residual_kg"))
    identity = case.get("provider_packet_identity")
    identity = identity if isinstance(identity, Mapping) else None
    provider_inventory = _provider_inventory(identity)
    provider_durations = (
        identity.get("duration_s") if isinstance(identity, Mapping) else None
    )
    provider_durations = _float_list(provider_durations)
    if status == "UNCOMPUTED" or status == "ZERO_WEIGHT":
        ledger_status = status
    elif duration is None or not mass_ledger:
        ledger_status = "INCOMPLETE"
    elif status == "EXECUTED":
        ledger_status = "COMPLETE"
    elif status == "EXECUTED_DOMAIN_INCOMPLETE":
        ledger_status = "DOMAIN_INCOMPLETE"
    elif status.startswith("EXECUTED"):
        ledger_status = "OPERATOR_LIMITED_OR_DOMAIN_INCOMPLETE"
    else:
        ledger_status = "INCOMPLETE"
    return {
        "event_id": case.get("event_id"),
        "asset_id": case.get("asset_id"),
        "release_branch_id": case.get("release_branch_id"),
        "annual_condition_id": case.get("annual_condition_id"),
        "status": status,
        "ledger_status": ledger_status,
        "reason": case.get("reason"),
        "release_branch_probability": case.get("release_branch_probability"),
        "initiating_frequency_per_year": case.get("initiating_frequency_per_year"),
        "termination": {
            "basis": basis,
            "time_s": duration,
            "provenance": termination.get("provenance"),
        },
        "isolation_status": _isolation_status(basis),
        "inventory_status": _inventory_status(basis),
        "provider": {
            "packet_consumed": provider_inventory["packet_consumed"],
            "event_id": identity.get("event_id") if identity else None,
            "component_id": identity.get("component_id") if identity else None,
            "provider_export_schema": identity.get("provider_export_schema") if identity else None,
            "provider_source_digests": identity.get("provider_source_digests", []) if identity else [],
            "provider_result_digests": identity.get("provider_result_digests", []) if identity else [],
            "provider_boundary_references": identity.get("provider_boundary_references", []) if identity else [],
            "duration_s": provider_durations,
            "available_mass_kg": provider_inventory["available_mass_kg"],
            "cumulative_mass_out_kg": provider_inventory["cumulative_mass_out_kg"],
            "residual_mass_kg": provider_inventory["residual_mass_kg"],
            "provider_mass_balances": provider_inventory["mass_balances"],
            "provider_mass_balance_statuses": provider_inventory["mass_balance_statuses"],
        },
        "mass_ledger": {
            "released_kg": _finite(mass_ledger.get("released_kg")),
            "end_to_end_residual_kg": end_to_end_residual,
        },
        "provider_termination_matches_request": (
            basis is not None
            and isinstance(identity, Mapping)
            and all(
                value is None or value == basis
                for value in identity.get("termination_bases", [])
            )
        ) if identity else False,
    }


def build_release_termination_inventory_ledger(
    cases: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    withheld_cases: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Return a machine-readable ledger without promoting any case."""
    rows = [_row(case) for case in cases]
    withheld = list(withheld_cases)
    withheld_status_counts = Counter(
        str(case.get("status", "UNKNOWN")) for case in withheld
    )
    status_counts = Counter(row["ledger_status"] for row in rows)
    basis_counts = Counter(
        row["termination"]["basis"]
        for row in rows
        if row["termination"]["basis"] is not None
    )
    return {
        "schema_version": RELEASE_LEDGER_SCHEMA,
        "rows": rows,
        "summary": {
            "case_count": len(rows),
            "ledger_status_counts": dict(sorted(status_counts.items())),
            "termination_basis_counts": dict(sorted(basis_counts.items())),
            "complete_row_count": status_counts.get("COMPLETE", 0),
            "operator_limited_or_domain_incomplete_row_count": status_counts.get(
                "OPERATOR_LIMITED_OR_DOMAIN_INCOMPLETE", 0
            ),
            "domain_incomplete_row_count": status_counts.get("DOMAIN_INCOMPLETE", 0),
            "uncomputed_row_count": status_counts.get("UNCOMPUTED", 0),
            "incomplete_row_count": status_counts.get("INCOMPLETE", 0),
            "provider_packet_consumed_row_count": sum(
                bool(row["provider"]["packet_consumed"]) for row in rows
            ),
            "withheld_case_count": len(withheld),
            "withheld_case_status_counts": dict(sorted(withheld_status_counts.items())),
            "withheld_operator_limited_case_count": withheld_status_counts.get(
                "EXECUTED_OPERATOR_LIMITED", 0
            ),
            "withheld_domain_incomplete_case_count": withheld_status_counts.get(
                "EXECUTED_DOMAIN_INCOMPLETE", 0
            ),
        },
        "semantics": {
            "one_row": "event × release branch × annual condition",
            "isolation": "reported only when the provider termination basis explicitly says reviewed_isolation_success",
            "inventory": "reported only from provider packet mass fields and explicit inventory termination basis",
            "missing_branch": "UNCOMPUTED remains a missing branch and is never converted to zero risk",
            "operator_limited": "numerically executed but not qualified facility evidence",
            "withheld_cases": "campaign-level copies of partial, failed, domain-incomplete, or uncomputed cases; they are summarized separately and never duplicated as ledger rows",
        },
    }


def evaluate_facility_release_boundary(
    ledger: Mapping[str, Any],
    *,
    residual_tolerance_kg: float = _STRICT_RESIDUAL_TOLERANCE_KG,
) -> dict[str, Any]:
    """Evaluate whether a facility release ledger is closed enough to promote.

    This is deliberately a *release-boundary* gate only.  It does not qualify
    an external provider, validate SLABx-LH2 or a physical experiment, assign
    a frequency, or promote facility IR/F-N.  A row must have a complete
    numerical ledger, an explicit reviewed isolation or inventory-depletion
    termination, and a finite mass residual.  Operator-limited, synthetic
    horizon, 600-second horizon, emergency-relief, and two-sided rows remain
    visible but cannot silently close this gate.
    """
    if not isinstance(ledger, Mapping):
        raise TypeError("release ledger must be a mapping")
    if (
        isinstance(residual_tolerance_kg, bool)
        or not isinstance(residual_tolerance_kg, (int, float))
        or not math.isfinite(float(residual_tolerance_kg))
        or float(residual_tolerance_kg) < 0.0
    ):
        raise ValueError("residual_tolerance_kg must be finite and nonnegative")
    tolerance = float(residual_tolerance_kg)
    raw_rows = ledger.get("rows", ())
    rows: Sequence[Mapping[str, Any]] = (
        tuple(row for row in raw_rows if isinstance(row, Mapping))
        if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes))
        else ()
    )
    summary = ledger.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    blocking: list[str] = []
    checks = {
        "all_rows_complete": bool(rows),
        "all_termination_bases_allowed": True,
        "all_isolation_or_inventory_statuses_closed": True,
        "all_mass_residuals_closed": True,
        "all_provider_mass_balances_closed": True,
        "no_withheld_cases": True,
    }
    withheld_count = summary.get("withheld_case_count", 0)
    try:
        withheld_count = max(0, int(withheld_count or 0))
    except (TypeError, ValueError):
        withheld_count = 0
    if withheld_count:
        checks["no_withheld_cases"] = False
        blocking.append(f"{withheld_count} case(s) are withheld from the release ledger")
    if not rows:
        blocking.append("release ledger contains no case rows")

    for index, row in enumerate(rows):
        label = str(
            row.get("event_id")
            or row.get("release_branch_id")
            or f"row-{index + 1}"
        )
        status = str(row.get("status", "UNKNOWN"))
        if status != "EXECUTED":
            checks["all_rows_complete"] = False
            blocking.append(f"{label}: status {status} is not a complete numerical case")

        termination = row.get("termination")
        termination = termination if isinstance(termination, Mapping) else {}
        basis = termination.get("basis")
        if basis not in _ALLOWED_STRICT_TERMINATION_BASES:
            checks["all_termination_bases_allowed"] = False
            blocking.append(
                f"{label}: termination basis {basis or 'not_declared'} is not a reviewed release boundary"
            )
        if basis == "reviewed_isolation_success":
            if row.get("isolation_status") != "provider_declared_isolation_success":
                checks["all_isolation_or_inventory_statuses_closed"] = False
                blocking.append(f"{label}: reviewed isolation status is not declared")
        elif basis == "inventory_depletion":
            if row.get("inventory_status") != "provider_declared_inventory_depletion":
                checks["all_isolation_or_inventory_statuses_closed"] = False
                blocking.append(f"{label}: inventory depletion status is not declared")
        elif basis == "emergency_relief_discharge":
            if (
                row.get("isolation_status") != "not_applicable"
                or row.get("inventory_status") != "not_applicable"
            ):
                checks["all_isolation_or_inventory_statuses_closed"] = False
                blocking.append(
                    f"{label}: emergency-relief isolation and inventory statuses must be not_applicable"
                )

        mass = row.get("mass_ledger")
        mass = mass if isinstance(mass, Mapping) else {}
        residual = _finite(mass.get("end_to_end_residual_kg"))
        if residual is None or abs(residual) > tolerance:
            checks["all_mass_residuals_closed"] = False
            blocking.append(
                f"{label}: end-to-end mass residual is not within {tolerance:g} kg"
            )

        provider = row.get("provider")
        provider = provider if isinstance(provider, Mapping) else {}
        residuals = provider.get("residual_mass_kg")
        if basis == "inventory_depletion" and residuals is not None:
            if (
                not isinstance(residuals, Sequence)
                or isinstance(residuals, (str, bytes))
                or not residuals
                or any(
                    _finite(value) is None or abs(float(_finite(value))) > tolerance
                    for value in residuals
                )
            ):
                checks["all_mass_residuals_closed"] = False
                blocking.append(
                    f"{label}: provider inventory residual is not depleted within {tolerance:g} kg"
                )
        provider_balance_statuses = provider.get("provider_mass_balance_statuses")
        if provider_balance_statuses:
            if (
                not isinstance(provider_balance_statuses, Sequence)
                or isinstance(provider_balance_statuses, (str, bytes))
                or not provider_balance_statuses
                or any(status != "CLOSED" for status in provider_balance_statuses)
            ):
                checks["all_provider_mass_balances_closed"] = False
                blocking.append(
                    f"{label}: provider mass-balance evidence is not closed"
                )

    unique_blocking = list(dict.fromkeys(blocking))
    return {
        "schema_version": RELEASE_BOUNDARY_GATE_SCHEMA,
        "strict_release_boundary_ready": bool(rows) and not unique_blocking,
        "case_count": len(rows),
        "withheld_case_count": withheld_count,
        "termination_basis_counts": dict(summary.get("termination_basis_counts", {})),
        "checks": checks,
        "blocking_reasons": unique_blocking,
        "residual_tolerance_kg": tolerance,
        "provider_qualification_evaluated": False,
        "independent_physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_ir_fn_promotion": False,
        "policy": (
            "release-boundary closure only; provider qualification, physical validation, "
            "frequency, weather/population integration, and facility IR/F-N remain separate gates"
        ),
    }


__all__ = [
    "RELEASE_LEDGER_SCHEMA",
    "RELEASE_BOUNDARY_GATE_SCHEMA",
    "build_release_termination_inventory_ledger",
    "evaluate_facility_release_boundary",
]
