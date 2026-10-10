"""Cross-check provider isolation responses against the consequence campaign.

The audit is intentionally narrower than a facility QRA.  It proves that a
provider-owned isolation success/failure history was consumed by a numerical
release-to-harm campaign and that the provider's flow and conservation claims
are visible.  It does not infer a plant failure-on-demand probability or
qualify synthetic geometry as facility evidence.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


SCHEMA = "prism.isolation_response_audit.v1"
_RESIDUAL_TOLERANCE_KG = 1.0e-8
_ENERGY_TOLERANCE_J = 1.0e-5


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _check(checks: list[dict[str, Any]], name: str, condition: bool, evidence: Mapping[str, Any]) -> None:
    checks.append({"name": name, "status": "PASS" if condition else "FAIL", "evidence": dict(evidence)})


def audit_isolation_response_campaign(
    provider_response: Mapping[str, Any],
    campaign_result: Mapping[str, Any],
    *,
    residual_tolerance_kg: float = _RESIDUAL_TOLERANCE_KG,
    energy_tolerance_j: float = _ENERGY_TOLERANCE_J,
) -> dict[str, Any]:
    """Audit isolation response rows and their consumed campaign cases."""
    if not isinstance(provider_response, Mapping):
        raise ValueError("provider_response must be an object")
    if not isinstance(campaign_result, Mapping):
        raise ValueError("campaign_result must be an object")
    if (
        isinstance(residual_tolerance_kg, bool)
        or not isinstance(residual_tolerance_kg, (int, float))
        or not math.isfinite(float(residual_tolerance_kg))
        or float(residual_tolerance_kg) < 0
    ):
        raise ValueError("residual_tolerance_kg must be finite and non-negative")
    if (
        isinstance(energy_tolerance_j, bool)
        or not isinstance(energy_tolerance_j, (int, float))
        or not math.isfinite(float(energy_tolerance_j))
        or float(energy_tolerance_j) < 0
    ):
        raise ValueError("energy_tolerance_j must be finite and non-negative")

    cases = _rows(campaign_result.get("cases", []), "campaign_result.cases")
    risk_atoms = _rows(campaign_result.get("risk_atoms", []), "campaign_result.risk_atoms")
    checks: list[dict[str, Any]] = []
    branch_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    observed_outcomes: set[str] = set()
    for location, outcomes in provider_response.items():
        if not isinstance(outcomes, Mapping):
            blockers.append(f"{location}: branch outcomes must be an object")
            continue
        for outcome, response in outcomes.items():
            if outcome not in {"success", "failure"}:
                blockers.append(f"{location}/{outcome}: unsupported isolation outcome")
                continue
            if not isinstance(response, Mapping) or not isinstance(response.get("data"), Mapping):
                blockers.append(f"{location}/{outcome}: provider data is missing")
                continue
            data = response["data"]
            label = f"{location}/{outcome}"
            provider_outcome = data.get("isolation_outcome")
            if provider_outcome != outcome:
                blockers.append(f"{label}: isolation_outcome does not match branch")
            observed_outcomes.add(str(provider_outcome))
            flow_zero = data.get("isolation_flow_zero_confirmed")
            post_observation = data.get("post_close_observation_available")
            close_time = _finite(data.get("close_time_s"))
            duration = _finite(data.get("duration_s"))
            pre_flow = _finite(data.get("pre_close_max_flow_kg_s"))
            post_flow = _finite(data.get("post_close_max_flow_kg_s"))
            mass_residual = _finite(data.get("max_total_mass_residual_kg"))
            energy_residual = _finite(data.get("max_total_energy_residual_j"))
            expected_basis = (
                "reviewed_isolation_success" if outcome == "success"
                else "synthetic_diagnostic_horizon"
            )
            matching_cases = [
                case for case in cases
                if case.get("release_branch_id") == f"provider-isolation-{outcome}"
                and str(location) in str(case.get("event_id", ""))
            ]
            case_bases = sorted({
                str(case.get("termination", {}).get("basis"))
                for case in matching_cases
                if isinstance(case.get("termination"), Mapping)
            })
            case_statuses = sorted({str(case.get("status")) for case in matching_cases})
            row = {
                "location": str(location),
                "outcome": outcome,
                "provider_outcome": provider_outcome,
                "close_time_s": close_time,
                "duration_s": duration,
                "pre_close_max_flow_kg_s": pre_flow,
                "post_close_max_flow_kg_s": post_flow,
                "post_close_observation_available": post_observation,
                "isolation_flow_zero_confirmed": flow_zero,
                "max_total_mass_residual_kg": mass_residual,
                "max_total_energy_residual_j": energy_residual,
                "campaign_case_count": len(matching_cases),
                "campaign_case_statuses": case_statuses,
                "campaign_termination_bases": case_bases,
                "expected_campaign_termination_basis": expected_basis,
            }
            branch_rows.append(row)
            if provider_outcome != outcome:
                continue
            if close_time is None or duration is None or close_time > duration:
                blockers.append(f"{label}: invalid isolation clock")
            if mass_residual is None or abs(mass_residual) > float(residual_tolerance_kg):
                blockers.append(f"{label}: mass residual is not closed")
            if energy_residual is None or abs(energy_residual) > float(energy_tolerance_j):
                blockers.append(f"{label}: energy residual is not closed")
            if outcome == "success":
                if flow_zero is not True or post_observation is not True or post_flow not in {0.0}:
                    blockers.append(f"{label}: provider did not confirm zero post-close flow")
                if pre_flow is None or pre_flow <= 0:
                    blockers.append(f"{label}: success branch lacks positive pre-close flow")
            else:
                if flow_zero is not False or post_observation is not False:
                    blockers.append(f"{label}: failure branch was incorrectly marked closed")
                if pre_flow is None or pre_flow <= 0:
                    blockers.append(f"{label}: failure branch lacks positive pre-close flow")
            if not matching_cases:
                blockers.append(f"{label}: no matching campaign cases")
            elif case_bases != [expected_basis]:
                blockers.append(f"{label}: campaign termination basis does not match provider branch")
            elif any(status != "EXECUTED" for status in case_statuses):
                blockers.append(f"{label}: campaign case did not execute numerically")

    _check(
        checks,
        "provider_branch_identity",
        len(branch_rows) > 0 and observed_outcomes == {"success", "failure"},
        {"branch_count": len(branch_rows), "observed_outcomes": sorted(observed_outcomes)},
    )
    success_rows = [row for row in branch_rows if row["outcome"] == "success"]
    failure_rows = [row for row in branch_rows if row["outcome"] == "failure"]
    _check(
        checks,
        "isolation_success_flow_zero",
        bool(success_rows)
        and all(
            row["isolation_flow_zero_confirmed"] is True
            and row["post_close_observation_available"] is True
            and row["post_close_max_flow_kg_s"] == 0.0
            for row in success_rows
        ),
        {"success_branch_count": len(success_rows)},
    )
    _check(
        checks,
        "isolation_failure_remains_horizon_bounded",
        bool(failure_rows)
        and all(
            row["isolation_flow_zero_confirmed"] is False
            and row["post_close_observation_available"] is False
            and row["campaign_termination_bases"] == ["synthetic_diagnostic_horizon"]
            for row in failure_rows
        ),
        {"failure_branch_count": len(failure_rows)},
    )
    _check(
        checks,
        "campaign_chain_consumed",
        campaign_result.get("status") == "DECLARED_SCOPE_EXECUTED"
        and bool(branch_rows)
        and all(row["campaign_case_count"] > 0 for row in branch_rows)
        and sum(row["campaign_case_count"] for row in branch_rows) == len(cases)
        and all(case.get("status") == "EXECUTED" for case in cases)
        and len(risk_atoms) > 0,
        {
            "campaign_status": campaign_result.get("status"),
            "campaign_case_count": len(cases),
            "risk_atom_count": len(risk_atoms),
        },
    )
    _check(
        checks,
        "no_facility_qra_promotion",
        campaign_result.get("facility_total_risk_available") is not True
        and campaign_result.get("complete_facility_qra_claim") is not True
        and campaign_result.get("physical_validation_claim") is not True,
        {
            "facility_total_risk_available": campaign_result.get("facility_total_risk_available"),
            "complete_facility_qra_claim": campaign_result.get("complete_facility_qra_claim"),
            "physical_validation_claim": campaign_result.get("physical_validation_claim"),
        },
    )
    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "schema": SCHEMA,
        "status": "ISOLATION_RESPONSE_CHAIN_DIAGNOSTIC" if not unique_blockers else "ISOLATION_RESPONSE_CHAIN_BLOCKED",
        "branch_count": len(branch_rows),
        "success_branch_count": len(success_rows),
        "failure_branch_count": len(failure_rows),
        "campaign_case_count": len(cases),
        "risk_atom_count": len(risk_atoms),
        "rows": branch_rows,
        "checks": checks,
        "blocking_reasons": unique_blockers,
        "policy": {
            "diagnostic_only": True,
            "synthetic_barrier_probability_is_not_inferred": True,
            "provider_packet_promotion": False,
            "facility_ir_fn_promotion": False,
            "physical_validation_claim": False,
            "frequency_inference_performed": False,
        },
        "interpretation": (
            "Provider isolation success/failure and its consumed consequence chain are audited. "
            "The failure branch remains a diagnostic horizon and no plant barrier reliability is inferred."
        ),
    }


__all__ = ["SCHEMA", "audit_isolation_response_campaign"]
