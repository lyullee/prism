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
from typing import Any, Mapping


RELEASE_LEDGER_SCHEMA = "prism.release_termination_inventory_ledger.v1"


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


def _provider_inventory(identity: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(identity, Mapping):
        return {
            "packet_consumed": False,
            "available_mass_kg": None,
            "cumulative_mass_out_kg": None,
            "residual_mass_kg": None,
        }
    available = _float_list(identity.get("available_mass_kg"))
    released = _float_list(identity.get("cumulative_mass_out_kg"))
    residual = None
    if available is not None and released is not None and len(available) == len(released):
        residual = [a - r for a, r in zip(available, released)]
    return {
        "packet_consumed": bool(identity.get("provider_result_digests")),
        "available_mass_kg": available,
        "cumulative_mass_out_kg": released,
        "residual_mass_kg": residual,
    }


def _isolation_status(termination_basis: str | None) -> str:
    if termination_basis == "reviewed_isolation_success":
        return "provider_declared_isolation_success"
    return "not_declared"


def _inventory_status(termination_basis: str | None) -> str:
    if termination_basis == "inventory_depletion":
        return "provider_declared_inventory_depletion"
    if termination_basis == "inventory_over_600s":
        return "provider_declared_inventory_over_600s"
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
) -> dict[str, Any]:
    """Return a machine-readable ledger without promoting any case."""
    rows = [_row(case) for case in cases]
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
            "uncomputed_row_count": status_counts.get("UNCOMPUTED", 0),
            "incomplete_row_count": status_counts.get("INCOMPLETE", 0),
            "provider_packet_consumed_row_count": sum(
                bool(row["provider"]["packet_consumed"]) for row in rows
            ),
        },
        "semantics": {
            "one_row": "event × release branch × annual condition",
            "isolation": "reported only when the provider termination basis explicitly says reviewed_isolation_success",
            "inventory": "reported only from provider packet mass fields and explicit inventory termination basis",
            "missing_branch": "UNCOMPUTED remains a missing branch and is never converted to zero risk",
            "operator_limited": "numerically executed but not qualified facility evidence",
        },
    }


__all__ = [
    "RELEASE_LEDGER_SCHEMA",
    "build_release_termination_inventory_ledger",
]
