"""Independent audit for the current header-bound frequency uncertainty ledger.

The bridge produces a frequency-uncertainty summary while it evaluates the
consequence chain.  This module re-derives the scenario counts from the saved
component rows so a summary cannot claim complete uncertainty coverage merely
because its own metadata says so.  Missing literature bounds remain explicit;
the audit never infers or imputes them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _has_explicit_bounds(risk: Mapping[str, Any]) -> bool:
    sensitivity = risk.get("frequency_sensitivity_current_weather_ir_low_high")
    return isinstance(sensitivity, Mapping) and all(
        isinstance(sensitivity.get(key), Mapping)
        for key in ("p05", "published", "p95")
    )


def audit_header_bound_frequency_uncertainty(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconcile explicit frequency-bound coverage in a bridge result."""
    summary = result.get("conditional_current_weather_frequency_uncertainty")
    summary = summary if isinstance(summary, Mapping) else {}
    bound_ids: list[str] = []
    unbound_ids: list[str] = []
    risk_rows = 0
    for component_id, component in sorted(
        (result.get("components") or {}).items()
        if isinstance(result.get("components"), Mapping)
        else {}
    ):
        if not isinstance(component, Mapping):
            continue
        for branch in component.get("branches", ()):
            if not isinstance(branch, Mapping):
                continue
            risk = branch.get("risk")
            scenario_id = str(branch.get("scenario_id") or "")
            if not scenario_id or not isinstance(risk, Mapping):
                continue
            if risk.get("status") != "AVAILABLE_CURRENT_WEATHER_IR":
                continue
            risk_rows += 1
            (bound_ids if _has_explicit_bounds(risk) else unbound_ids).append(
                scenario_id
            )

    bound_ids.sort()
    unbound_ids.sort()
    declared_bound_ids = sorted(
        str(value) for value in summary.get("frequency_bound_scenario_ids", [])
    )
    declared_unbound_ids = sorted(
        str(value) for value in summary.get("frequency_unbound_scenario_ids", [])
    )
    counts_match = (
        summary.get("risk_atom_count") == risk_rows
        and summary.get("frequency_bound_scenario_count") == len(bound_ids)
        and summary.get("frequency_unbound_scenario_count") == len(unbound_ids)
        and declared_bound_ids == bound_ids
        and declared_unbound_ids == unbound_ids
    )
    complete = bool(risk_rows) and not unbound_ids
    expected_status = (
        "COMPLETE_CURRENT_WEATHER_FREQUENCY_UNCERTAINTY"
        if complete
        else "PARTIAL_CURRENT_WEATHER_FREQUENCY_UNCERTAINTY"
        if bound_ids
        else "WITHHELD_CURRENT_WEATHER_FREQUENCY_UNCERTAINTY"
    )
    policy_ok = (
        summary.get("status") == expected_status
        and summary.get("complete") is complete
        and summary.get("frequency_inference_performed") is False
        and summary.get("missing_bounds_imputed") is False
    )
    valid = bool(summary) and counts_match and policy_ok
    return {
        "schema_version": "prism.header_bound_frequency_uncertainty_audit.v1",
        "status": "PASS_DIAGNOSTIC_ONLY" if valid else "BLOCKED",
        "diagnostic_only": True,
        "risk_atom_count": risk_rows,
        "frequency_bound_scenario_count": len(bound_ids),
        "frequency_unbound_scenario_count": len(unbound_ids),
        "frequency_bound_scenario_ids": bound_ids,
        "frequency_unbound_scenario_ids": unbound_ids,
        "expected_summary_status": expected_status,
        "summary_counts_match": counts_match,
        "summary_policy_match": policy_ok,
        "frequency_inference_performed": False,
        "missing_bounds_imputed": False,
        "blocking_reasons": []
        if valid
        else [
            reason
            for reason, condition in (
                ("summary_counts_or_ids_do_not_match_component_rows", not counts_match),
                ("summary_status_or_policy_is_not_fail_closed", not policy_ok),
            )
            if condition
        ],
        "interpretation": (
            "The saved bridge rows and their uncertainty summary reconcile. "
            "Only explicit provider frequency bounds are counted; missing bounds "
            "remain unbounded and no frequency inference or interval imputation is performed."
        ),
    }

