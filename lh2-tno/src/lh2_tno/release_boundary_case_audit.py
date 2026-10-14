"""Case-level audit of release termination, isolation and inventory closure.

The facility assessment already contains one release ledger for every executed
case.  This module turns that ledger into a reviewer-facing promotion table so
that a calculated consequence is never confused with a closed facility release
boundary.  It deliberately stops before provider qualification, frequency
inference, physical validation, or facility IR/F-N promotion.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any, Mapping, Sequence


SCHEMA = "prism.release_boundary_case_audit.v1"
_ALLOWED_BASES = {"reviewed_isolation_success", "inventory_depletion"}
_TOLERANCE_KG = 1e-8


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _case_key(row: Mapping[str, Any]) -> str:
    """Use the release ledger grain: event × branch × annual condition."""

    values = (
        row.get("event_id"),
        row.get("release_branch_id"),
        row.get("annual_condition_id"),
    )
    return "|".join("" if value is None else str(value) for value in values)


def _provider_origins(case: Mapping[str, Any], ledger_row: Mapping[str, Any]) -> list[str]:
    identity = _as_mapping(case.get("provider_packet_identity"))
    origins = identity.get("input_origins")
    if isinstance(origins, Sequence) and not isinstance(origins, (str, bytes)):
        return sorted({str(origin) for origin in origins})
    provider = _as_mapping(ledger_row.get("provider"))
    origins = provider.get("input_origins")
    if isinstance(origins, Sequence) and not isinstance(origins, (str, bytes)):
        return sorted({str(origin) for origin in origins})
    return []


def _provider_blockers(case: Mapping[str, Any], ledger_row: Mapping[str, Any]) -> list[str]:
    """Return qualification blockers without treating model output as field data."""

    reasons: list[str] = []
    origins = _provider_origins(case, ledger_row)
    if not origins:
        reasons.append("provider_input_origin_not_declared")
    elif any(origin != "actual" for origin in origins):
        reasons.append("provider_input_is_not_actual_field_data")
    identity = _as_mapping(case.get("provider_packet_identity"))
    if identity.get("physical_validation_claim") is not True:
        reasons.append("independent_physical_validation_not_claimed")
    if not identity.get("provider_source_digests") or not identity.get("provider_result_digests"):
        reasons.append("provider_source_or_result_digest_missing")
    # A provider mass balance can close numerically while the packet is still
    # model-prediction evidence.  Keep those concepts separate.
    statuses = _as_mapping(ledger_row.get("provider")).get("provider_mass_balance_statuses")
    if (
        isinstance(statuses, Sequence)
        and not isinstance(statuses, (str, bytes))
        and statuses
        and any(status != "CLOSED" for status in statuses)
    ):
        reasons.append("provider_mass_balance_not_closed")
    return list(dict.fromkeys(reasons))


def _case_reasons(
    case: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    residual_tolerance_kg: float,
) -> list[str]:
    reasons: list[str] = []
    status = str(row.get("status", "UNKNOWN"))
    if status != "EXECUTED":
        reasons.append(f"status_{status.lower()}")
    termination = _as_mapping(row.get("termination"))
    basis = termination.get("basis")
    if basis not in _ALLOWED_BASES:
        reasons.append(f"termination_basis_{basis or 'not_declared'}_is_not_allowed")
    if basis == "reviewed_isolation_success" and row.get("isolation_status") != "provider_declared_isolation_success":
        reasons.append("isolation_success_not_declared")
    if basis == "inventory_depletion":
        if row.get("inventory_status") != "provider_declared_inventory_depletion":
            reasons.append("inventory_depletion_not_declared")
        residuals = _as_mapping(row.get("provider")).get("residual_mass_kg")
        values = (
            [ _finite(value) for value in residuals ]
            if isinstance(residuals, Sequence) and not isinstance(residuals, (str, bytes))
            else []
        )
        if not values or any(value is None or abs(value) > residual_tolerance_kg for value in values):
            reasons.append("provider_inventory_residual_not_depleted")
    mass = _as_mapping(row.get("mass_ledger"))
    residual = _finite(mass.get("end_to_end_residual_kg"))
    if residual is None or abs(residual) > residual_tolerance_kg:
        reasons.append("end_to_end_mass_residual_not_closed")
    balances = _as_mapping(row.get("provider")).get("provider_mass_balance_statuses")
    if balances and (
        not isinstance(balances, Sequence)
        or isinstance(balances, (str, bytes))
        or not balances
        or any(status != "CLOSED" for status in balances)
    ):
        reasons.append("provider_mass_balance_not_closed")
    domain = _as_mapping(case.get("domain_assessment"))
    if domain.get("domain_truncated") is True:
        reasons.append("consequence_domain_truncated")
    return list(dict.fromkeys(reasons))


def _required_evidence(
    boundary_reasons: Sequence[str],
    provider_reasons: Sequence[str],
) -> list[str]:
    """Translate observable blockers into an actionable evidence request.

    The request is descriptive only.  It never manufactures a provider packet,
    an isolation success probability, a frequency, or a consequence result.
    """

    requirements: list[str] = []
    reason_set = set(boundary_reasons)
    if any(reason.startswith("status_") for reason in reason_set):
        requirements.append(
            "provider-owned release time history with an explicit successful termination event"
        )
    if "status_executed_operator_limited" in reason_set:
        requirements.append(
            "provider-owned transient state and operator-independent isolation or inventory closure evidence"
        )
    for reason in reason_set:
        if reason.startswith("termination_basis_"):
            basis = reason.removeprefix("termination_basis_").removesuffix("_is_not_allowed")
            if basis == "synthetic_diagnostic_horizon":
                requirements.append(
                    "provider run continued to a reviewed isolation success or positive-inventory depletion boundary"
                )
            elif basis == "inventory_over_600s":
                requirements.append(
                    "complete provider history beyond the 600 s horizon or an explicit physical termination boundary"
                )
            elif basis == "emergency_relief_discharge":
                requirements.append(
                    "qualified relief-discharge setpoint, capacity and provider-owned termination history"
                )
            elif basis == "two_sided_rupture":
                requirements.append(
                    "paired outlet histories with endpoint inventories and same-event coupling closure"
                )
            else:
                requirements.append(f"reviewed provider termination evidence for {basis}")
    if "provider_inventory_residual_not_depleted" in reason_set:
        requirements.append(
            "provider initial/final inventory and mass balance proving residual mass is within tolerance"
        )
    if "end_to_end_mass_residual_not_closed" in reason_set:
        requirements.append("end-to-end source-to-consequence mass reconciliation with residual")
    if "provider_mass_balance_not_closed" in reason_set:
        requirements.append("provider mass and energy balance closure with residual diagnostics")
    if "consequence_domain_truncated" in reason_set:
        requirements.append(
            "expanded consequence domain or an independent flammability-boundary closure"
        )
    if provider_reasons:
        requirements.extend([
            "actual provider source and result artifacts with exact event/component/port SHA-256 identity",
            "provider qualification sidecar bound to the exact source/result artifacts",
            "independent physical-validation record or an explicitly reviewed validation gap",
        ])
    return list(dict.fromkeys(requirements))


def build_release_boundary_case_audit(
    facility_assessment: Mapping[str, Any],
    *,
    residual_tolerance_kg: float = _TOLERANCE_KG,
    facility_evidence_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a case-level release-boundary promotion table.

    ``strict_release_boundary_eligible`` means only that the individual row
    satisfies the release-termination gate.  It does *not* mean the row is an
    actual qualified provider packet or that it can contribute to facility
    IR/F-N.  The latter flags remain false until external qualification and
    independent validation are supplied.
    """

    if not isinstance(facility_assessment, Mapping):
        raise TypeError("facility_assessment must be a mapping")
    if (
        isinstance(residual_tolerance_kg, bool)
        or not isinstance(residual_tolerance_kg, (int, float))
        or not math.isfinite(float(residual_tolerance_kg))
        or float(residual_tolerance_kg) < 0.0
    ):
        raise ValueError("residual_tolerance_kg must be finite and nonnegative")
    tolerance = float(residual_tolerance_kg)
    risk_ledger = _as_mapping(facility_assessment.get("facility_risk_ledger"))
    if not risk_ledger:
        risk_ledger = facility_assessment
    cases = _as_rows(risk_ledger.get("cases"))
    release_ledger = _as_mapping(risk_ledger.get("release_termination_inventory_ledger"))
    ledger_rows = _as_rows(release_ledger.get("rows"))
    request_rows = (
        _as_rows(_as_mapping(facility_evidence_request).get("case_requests"))
        if facility_evidence_request is not None
        else []
    )
    request_by_key = {
        _case_key(request): request
        for request in request_rows
        if request.get("event_id") is not None
    }
    cases_by_key = {
        _case_key(case): case for case in cases if case.get("event_id") is not None
    }
    case_ids = [_case_key(case) for case in cases if case.get("event_id") is not None]
    ledger_ids = [_case_key(row) for row in ledger_rows if row.get("event_id") is not None]
    missing_case_ids = sorted(set(case_ids) - set(ledger_ids))
    orphan_ledger_ids = sorted(set(ledger_ids) - set(case_ids))
    duplicate_ledger_ids = sorted({event_id for event_id in ledger_ids if ledger_ids.count(event_id) > 1})
    alignment_blockers: list[str] = []
    if missing_case_ids:
        alignment_blockers.append("case_rows_missing_from_release_ledger")
    if orphan_ledger_ids:
        alignment_blockers.append("release_ledger_rows_missing_case_metadata")
    if duplicate_ledger_ids:
        alignment_blockers.append("duplicate_release_ledger_case_keys")
    request_missing_case_keys: list[str] = []
    request_orphan_case_keys: list[str] = []
    request_duplicate_case_keys = sorted({
        key for key in (
            _case_key(request)
            for request in request_rows
            if request.get("event_id") is not None
        )
        if sum(
            1
            for request in request_rows
            if request.get("event_id") is not None and _case_key(request) == key
        ) > 1
    })
    request_alignment_status = "NOT_SUPPLIED"
    if facility_evidence_request is not None:
        request_missing_case_keys = sorted(set(ledger_ids) - set(request_by_key))
        request_orphan_case_keys = sorted(set(request_by_key) - set(ledger_ids))
        if request_missing_case_keys:
            alignment_blockers.append("release_ledger_cases_missing_from_evidence_request")
        if request_orphan_case_keys:
            alignment_blockers.append("evidence_request_contains_unknown_case_keys")
        if request_duplicate_case_keys:
            alignment_blockers.append("duplicate_evidence_request_case_keys")
        request_alignment_status = "ALIGNED" if not any(
            reason in alignment_blockers
            for reason in (
                "release_ledger_cases_missing_from_evidence_request",
                "evidence_request_contains_unknown_case_keys",
                "duplicate_evidence_request_case_keys",
            )
        ) else "BLOCKED"
    rows: list[dict[str, Any]] = []
    for ledger_row in ledger_rows:
        event_id = str(ledger_row.get("event_id"))
        case = cases_by_key.get(_case_key(ledger_row), {})
        reasons = _case_reasons(case, ledger_row, residual_tolerance_kg=tolerance)
        provider_blockers = _provider_blockers(case, ledger_row)
        required_evidence = _required_evidence(reasons, provider_blockers)
        request = request_by_key.get(_case_key(ledger_row))
        request_evidence = request.get("required_provider_evidence", []) if request else []
        request_evidence = (
            list(request_evidence)
            if isinstance(request_evidence, Sequence)
            and not isinstance(request_evidence, (str, bytes))
            else []
        )
        termination = _as_mapping(ledger_row.get("termination"))
        identity = _as_mapping(case.get("provider_packet_identity"))
        boundary_ok = not reasons
        rows.append({
            "event_id": ledger_row.get("event_id"),
            "case_key": _case_key(ledger_row),
            "release_branch_id": ledger_row.get("release_branch_id"),
            "annual_condition_id": ledger_row.get("annual_condition_id"),
            "asset_id": ledger_row.get("asset_id"),
            "model_component_id": identity.get("component_id"),
            "frequency_port_ids": list(case.get("frequency_port_ids", [])) if isinstance(case.get("frequency_port_ids"), list) else [],
            "operating_mode": case.get("operating_mode"),
            "hazop_scenario_id": case.get("hazop_scenario_id"),
            "scenario_families": list(case.get("scenario_families", [])) if isinstance(case.get("scenario_families"), list) else [],
            "status": ledger_row.get("status"),
            "ledger_status": ledger_row.get("ledger_status"),
            "termination": {
                "basis": termination.get("basis"),
                "time_s": termination.get("time_s"),
                "provenance": termination.get("provenance"),
            },
            "isolation_status": ledger_row.get("isolation_status"),
            "inventory_status": ledger_row.get("inventory_status"),
            "end_to_end_residual_kg": _as_mapping(ledger_row.get("mass_ledger")).get("end_to_end_residual_kg"),
            "provider_input_origins": _provider_origins(case, ledger_row),
            "strict_release_boundary_eligible": boundary_ok,
            "strict_release_boundary_status": "ELIGIBLE" if boundary_ok else "PROMOTION_BLOCKED",
            "release_boundary_blocking_reasons": reasons,
            "required_evidence": required_evidence,
            "evidence_request_status": "OPEN" if required_evidence else "NONE",
            "facility_evidence_request_match": request is not None,
            "facility_evidence_request_id": request.get("request_id") if request else None,
            "facility_evidence_request_status": request.get("status") if request else None,
            "facility_evidence_required_provider_evidence_count": len(request_evidence),
            "provider_qualification_status": "BLOCKED" if provider_blockers else "REVIEW_REQUIRED",
            "provider_qualification_blocking_reasons": provider_blockers,
            "facility_qra_promotion_eligible": False,
            "facility_qra_promotion_status": "PROMOTION_BLOCKED",
            "facility_qra_blocking_reasons": list(dict.fromkeys(
                provider_blockers + ["case_level_audit_does_not_promote_facility_ir_fn"]
            )),
        })
    status_counts = Counter(row["strict_release_boundary_status"] for row in rows)
    provider_status_counts = Counter(row["provider_qualification_status"] for row in rows)
    reasons = [reason for row in rows for reason in row["release_boundary_blocking_reasons"]]
    return {
        "schema_version": SCHEMA,
        "status": (
            "CASE_BOUNDARY_BLOCKED" if alignment_blockers
            else "CASE_BOUNDARY_CLOSED" if rows and not reasons
            else "CASE_BOUNDARY_PARTIAL" if rows and status_counts.get("ELIGIBLE", 0)
            else "CASE_BOUNDARY_BLOCKED"
        ),
        "case_count": len(rows),
        "case_key_definition": "event_id|release_branch_id|annual_condition_id",
        "source_case_count": len(cases),
        "source_release_ledger_row_count": len(ledger_rows),
        "source_alignment_status": "ALIGNED" if not alignment_blockers else "BLOCKED",
        "source_alignment_blocking_reasons": alignment_blockers,
        "missing_case_ids": missing_case_ids,
        "orphan_ledger_ids": orphan_ledger_ids,
        "duplicate_ledger_ids": duplicate_ledger_ids,
        "facility_evidence_request_alignment_status": request_alignment_status,
        "facility_evidence_request_case_count": len(request_rows) if facility_evidence_request is not None else None,
        "facility_evidence_request_missing_case_keys": request_missing_case_keys,
        "facility_evidence_request_orphan_case_keys": request_orphan_case_keys,
        "facility_evidence_request_duplicate_case_keys": request_duplicate_case_keys,
        "strict_release_boundary_eligible_case_count": status_counts.get("ELIGIBLE", 0),
        "strict_release_boundary_blocked_case_count": status_counts.get("PROMOTION_BLOCKED", 0),
        "provider_qualification_status_counts": dict(sorted(provider_status_counts.items())),
        "termination_basis_counts": dict(sorted(Counter(
            row["termination"]["basis"] for row in rows
        ).items())),
        "rows": rows,
        "residual_tolerance_kg": tolerance,
        "provider_qualification_claim": False,
        "independent_physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_ir_fn_promotion": False,
        "policy": (
            "case-level release boundary triage only; an eligible row is not an actual qualified provider packet "
            "and cannot promote facility frequency, weather/population integration, IR, or F-N"
        ),
    }


__all__ = ["SCHEMA", "build_release_boundary_case_audit"]
