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
_ALLOWED_BASES = {"reviewed_isolation_success", "inventory_depletion", "two_sided_rupture"}
_TOLERANCE_KG = 1e-8
_TERMINATION_EVIDENCE_BASES = {
    "reviewed_isolation_success",
    "inventory_depletion_positive_threshold",
    "inventory_depletion_releasable_mass",
    "two_sided_rupture",
}


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


def _same_mass(left: Any, right: Any, tolerance: float) -> bool:
    """Compare provider-owned masses without accepting missing values."""

    left_value = _finite(left)
    right_value = _finite(right)
    return (
        left_value is not None
        and right_value is not None
        and math.isclose(left_value, right_value, rel_tol=1e-8, abs_tol=tolerance)
    )


def _same_mass_vector(left: Any, right: Any, tolerance: float) -> bool:
    """Compare scalar or endpoint-vector masses without collapsing endpoints."""

    left_values = _finite_values(left)
    right_values = _finite_values(right)
    return bool(left_values) and len(left_values) == len(right_values) and all(
        _same_mass(left_value, right_value, tolerance)
        for left_value, right_value in zip(left_values, right_values)
    )


def _termination_evidence_candidates(
    provider_termination_evidence: Mapping[str, Any] | None,
    *,
    case_key: str,
    event_id: Any,
) -> list[Mapping[str, Any]]:
    """Return candidate provider termination ledgers for one facility case.

    The catalog accepts either a reviewer-facing ``rows`` array or a simple
    event-id keyed mapping.  Event-id matching is intentionally a fallback for
    annual-condition duplicates: one provider packet may support several
    weather branches, but the packet digest and masses still have to match the
    consuming facility row.
    """

    if not isinstance(provider_termination_evidence, Mapping):
        return []
    raw_rows = provider_termination_evidence.get("rows")
    rows = _as_rows(raw_rows) if raw_rows is not None else []
    if not rows:
        for key, value in provider_termination_evidence.items():
            if key in {"schema_version", "policy", "rows", "diagnostic_only"}:
                continue
            if isinstance(value, Mapping):
                row = dict(value)
                row.setdefault("event_id", key)
                rows.append(row)
    candidates: list[Mapping[str, Any]] = []
    for row in rows:
        row_key = row.get("case_key")
        row_event = row.get("event_id")
        if row_key == case_key or (row_event is not None and str(row_event) == str(event_id)):
            candidates.append(row)
    return candidates


def _audit_termination_evidence(
    case: Mapping[str, Any],
    row: Mapping[str, Any],
    candidate: Mapping[str, Any] | None,
    *,
    residual_tolerance_kg: float,
) -> dict[str, Any]:
    """Validate an explicit provider termination ledger at the facility grain.

    A positive threshold is a real provider stopping rule, not zero inventory.
    It can therefore close the release *boundary* only when the threshold,
    remaining mass, packet digest, and provider mass residual all agree.  This
    function never changes the residual to zero and never qualifies the
    provider or promotes facility IR/F-N.
    """

    result: dict[str, Any] = {
        "status": "NOT_SUPPLIED" if candidate is None else "INVALID",
        "used": False,
        "basis": candidate.get("termination_basis") if candidate else None,
        "provider_result_digest": candidate.get("provider_result_digest") if candidate else None,
        "source": candidate.get("source") if candidate else None,
        "checks": {},
        "blocking_reasons": [],
    }
    if candidate is None:
        return result
    identity = _as_mapping(case.get("provider_packet_identity"))
    provider = _as_mapping(row.get("provider"))
    raw_digests = identity.get("provider_result_digests")
    expected_digests = {
        str(value)
        for value in raw_digests
        if value is not None
    } if isinstance(raw_digests, Sequence) and not isinstance(raw_digests, (str, bytes)) else set()
    if not expected_digests:
        raw = identity.get("provider_result_digests")
        if isinstance(raw, str) and raw:
            expected_digests.add(raw)
    digest = candidate.get("provider_result_digest")
    candidate_digests = candidate.get("provider_result_digests")
    checks = result["checks"]
    checks["event_id_matches"] = (
        candidate.get("event_id") is None
        or str(candidate.get("event_id")) == str(row.get("event_id"))
    )
    if isinstance(candidate_digests, Sequence) and not isinstance(candidate_digests, (str, bytes)):
        checks["provider_result_digest_matches"] = bool(expected_digests) and {
            str(value) for value in candidate_digests if value is not None
        } == expected_digests
    else:
        checks["provider_result_digest_matches"] = (
            isinstance(digest, str) and bool(expected_digests) and digest in expected_digests
        )
    available = _finite_values(provider.get("available_mass_kg"))
    released = _finite_values(provider.get("cumulative_mass_out_kg"))
    candidate_available = candidate.get("available_mass_kg")
    candidate_released = candidate.get("cumulative_mass_out_kg")
    checks["available_mass_matches"] = bool(available) and _same_mass_vector(
        candidate_available, available, residual_tolerance_kg
    )
    checks["cumulative_release_matches"] = bool(released) and _same_mass_vector(
        candidate_released, released, residual_tolerance_kg
    )
    basis = candidate.get("termination_basis")
    checks["supported_basis"] = basis in _TERMINATION_EVIDENCE_BASES
    remaining = _finite(candidate.get("remaining_mass_kg"))
    threshold = _finite(candidate.get("threshold_mass_kg"))
    provider_residual = _finite(candidate.get("provider_residual_mass_kg"))
    max_residual = _finite(candidate.get("max_abs_mass_residual_kg"))
    if basis == "reviewed_isolation_success":
        isolation_success = candidate.get("isolation_success")
        isolation_time = _finite(candidate.get("isolation_time_s"))
        observation = _finite(candidate.get("post_isolation_observation_s"))
        provenance = candidate.get("termination_provenance")
        checks["isolation_success_declared"] = isolation_success is True
        checks["isolation_time_present"] = isolation_time is not None and isolation_time >= 0.0
        checks["post_isolation_observation_present"] = observation is not None and observation > 0.0
        checks["termination_provenance_present"] = isinstance(provenance, str) and bool(provenance.strip())
        # Reviewed isolation closes the outlet boundary even when the
        # upstream component retains inventory.  A provider mass residual is
        # checked when the packet supplies one; otherwise the case-level mass
        # ledger and explicit isolation state remain the governing checks.
        post_isolation_zero_flow = candidate.get("post_isolation_zero_flow")
        checks["post_isolation_zero_flow"] = (
            post_isolation_zero_flow is True or post_isolation_zero_flow is None
        )
        checks["mass_residual_closed"] = (
            max_residual is None or abs(max_residual) <= residual_tolerance_kg
        )
        checks["boundary_closed"] = all(
            checks[name]
            for name in (
                "isolation_success_declared",
                "isolation_time_present",
                "post_isolation_observation_present",
                "termination_provenance_present",
                "post_isolation_zero_flow",
                "mass_residual_closed",
            )
        )
    elif basis == "inventory_depletion_positive_threshold":
        checks["threshold_positive"] = threshold is not None and threshold > residual_tolerance_kg
        checks["remaining_at_or_below_threshold"] = (
            remaining is not None
            and threshold is not None
            and remaining <= threshold + residual_tolerance_kg
        )
        checks["remaining_matches_provider_ledger"] = (
            bool(available)
            and bool(released)
            and remaining is not None
            and _same_mass(remaining, available[0] - released[0], residual_tolerance_kg)
        )
        checks["mass_residual_closed"] = max_residual is not None and abs(max_residual) <= residual_tolerance_kg
        checks["boundary_closed"] = all(
            checks[name]
            for name in (
                "threshold_positive",
                "remaining_at_or_below_threshold",
                "remaining_matches_provider_ledger",
                "mass_residual_closed",
            )
        )
    elif basis == "inventory_depletion_releasable_mass":
        definition = candidate.get("available_mass_definition")
        releasable_remaining = _finite(candidate.get("remaining_releasable_mass_kg"))
        checks["releasable_definition_present"] = (
            isinstance(definition, str) and "releasable mass" in definition.lower()
        )
        checks["releasable_remaining_closed"] = (
            releasable_remaining is not None and abs(releasable_remaining) <= residual_tolerance_kg
        )
        checks["provider_residual_closed"] = (
            provider_residual is not None and abs(provider_residual) <= residual_tolerance_kg
        )
        checks["boundary_closed"] = all(
            checks[name]
            for name in (
                "releasable_definition_present",
                "releasable_remaining_closed",
                "provider_residual_closed",
            )
        )
    elif basis == "two_sided_rupture":
        endpoint_count = candidate.get("endpoint_count")
        checks["endpoint_count_matches"] = (
            isinstance(endpoint_count, int)
            and not isinstance(endpoint_count, bool)
            and endpoint_count == len(expected_digests)
            and endpoint_count >= 2
        )
        provenance = candidate.get("termination_provenance")
        checks["termination_provenance_present"] = isinstance(provenance, str) and bool(provenance.strip())
        checks["mass_residual_closed"] = max_residual is not None and abs(max_residual) <= residual_tolerance_kg
        checks["boundary_closed"] = all(
            checks[name]
            for name in (
                "endpoint_count_matches",
                "termination_provenance_present",
                "mass_residual_closed",
            )
        )
    else:
        checks["boundary_closed"] = False
    for name, ok in checks.items():
        if not ok:
            result["blocking_reasons"].append(f"provider_termination_evidence_{name}")
    if checks.get("boundary_closed") and all(
        checks.get(name) is True
        for name in (
            "event_id_matches",
            "provider_result_digest_matches",
            "available_mass_matches",
            "cumulative_release_matches",
            "supported_basis",
        )
    ):
        result["status"] = "VALID"
        result["used"] = True
        result["blocking_reasons"] = []
    else:
        result["blocking_reasons"] = list(dict.fromkeys(result["blocking_reasons"]))
    return result


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
    termination_evidence_audit: Mapping[str, Any] | None = None,
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
        evidence_status = (
            termination_evidence_audit.get("status")
            if isinstance(termination_evidence_audit, Mapping)
            else None
        )
        if evidence_status == "INVALID":
            reasons.append("provider_termination_evidence_invalid")
        if (
            evidence_status != "VALID"
            and (not values or any(value is None or abs(value) > residual_tolerance_kg for value in values))
        ):
            reasons.append("provider_inventory_residual_not_depleted")
    if basis == "two_sided_rupture":
        evidence_status = (
            termination_evidence_audit.get("status")
            if isinstance(termination_evidence_audit, Mapping)
            else None
        )
        if evidence_status == "INVALID":
            reasons.append("provider_termination_evidence_invalid")
        elif evidence_status != "VALID":
            reasons.append("two_sided_provider_termination_evidence_not_supplied")
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


def _termination_reasons(
    row: Mapping[str, Any],
    *,
    residual_tolerance_kg: float,
    termination_evidence_audit: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return only release-termination and mass-closure reasons.

    ``status`` and consequence-domain limitations are deliberately excluded.
    This second view lets a reviewer distinguish a numerically closed release
    ledger from a row that is still blocked because the provider was marked
    operator-limited or the consequence domain was truncated.  It does not
    relax the strict gate used by :func:`_case_reasons`.
    """

    reasons: list[str] = []
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
            [_finite(value) for value in residuals]
            if isinstance(residuals, Sequence) and not isinstance(residuals, (str, bytes))
            else []
        )
        evidence_status = (
            termination_evidence_audit.get("status")
            if isinstance(termination_evidence_audit, Mapping)
            else None
        )
        if evidence_status == "INVALID":
            reasons.append("provider_termination_evidence_invalid")
        if (
            evidence_status != "VALID"
            and (not values or any(value is None or abs(value) > residual_tolerance_kg for value in values))
        ):
            reasons.append("provider_inventory_residual_not_depleted")
    if basis == "two_sided_rupture":
        evidence_status = (
            termination_evidence_audit.get("status")
            if isinstance(termination_evidence_audit, Mapping)
            else None
        )
        if evidence_status == "INVALID":
            reasons.append("provider_termination_evidence_invalid")
        elif evidence_status != "VALID":
            reasons.append("two_sided_provider_termination_evidence_not_supplied")
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
    return list(dict.fromkeys(reasons))


def _finite_values(value: Any) -> list[float]:
    """Normalize scalar/list numeric release metrics without inventing values."""

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [number for item in value if (number := _finite(item)) is not None]
    number = _finite(value)
    return [] if number is None else [number]


def _release_metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    """Expose provider duration and inventory values at the case-audit grain."""

    provider = _as_mapping(row.get("provider"))
    available = _finite_values(provider.get("available_mass_kg"))
    released = _finite_values(provider.get("cumulative_mass_out_kg"))
    residual = _finite_values(provider.get("residual_mass_kg"))
    durations = _finite_values(provider.get("duration_s"))
    residual_fraction: list[float | None] = []
    for initial, remaining in zip(available, residual):
        residual_fraction.append(None if initial == 0.0 else remaining / initial)
    return {
        "release_duration_s": durations,
        "available_mass_kg": available,
        "cumulative_mass_out_kg": released,
        "residual_mass_kg": residual,
        "residual_fraction": residual_fraction,
    }


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
    if "provider_termination_evidence_invalid" in reason_set:
        requirements.append(
            "provider termination ledger with matching event, packet digest, masses and explicit threshold or releasable-inventory basis"
        )
    if "two_sided_provider_termination_evidence_not_supplied" in reason_set:
        requirements.append(
            "paired endpoint histories with both result digests, shared inventory provenance and common mass-residual closure"
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
    provider_termination_evidence: Mapping[str, Any] | None = None,
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
        evidence_candidates = _termination_evidence_candidates(
            provider_termination_evidence,
            case_key=_case_key(ledger_row),
            event_id=event_id,
        )
        evidence_audit = _audit_termination_evidence(
            case,
            ledger_row,
            evidence_candidates[0] if evidence_candidates else None,
            residual_tolerance_kg=tolerance,
        )
        if len(evidence_candidates) > 1:
            evidence_audit["status"] = "INVALID"
            evidence_audit["used"] = False
            evidence_audit.setdefault("blocking_reasons", []).append(
                "provider_termination_evidence_ambiguous"
            )
            evidence_audit["blocking_reasons"] = list(dict.fromkeys(
                evidence_audit["blocking_reasons"]
            ))
        reasons = _case_reasons(
            case,
            ledger_row,
            residual_tolerance_kg=tolerance,
            termination_evidence_audit=evidence_audit,
        )
        termination_reasons = _termination_reasons(
            ledger_row,
            residual_tolerance_kg=tolerance,
            termination_evidence_audit=evidence_audit,
        )
        operational_reasons = [
            f"status_{str(ledger_row.get('status', 'UNKNOWN')).lower()}"
        ] if ledger_row.get("status", "UNKNOWN") != "EXECUTED" else []
        domain_reasons = (
            ["consequence_domain_truncated"]
            if _as_mapping(case.get("domain_assessment")).get("domain_truncated") is True
            else []
        )
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
        metrics = _release_metrics(ledger_row)
        numerical_release_closed = not termination_reasons
        if numerical_release_closed and operational_reasons:
            numerical_closure_status = "NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED"
        elif numerical_release_closed:
            numerical_closure_status = "NUMERICALLY_CLOSED"
        else:
            numerical_closure_status = "NUMERICALLY_OPEN"
        domain_status = "TRUNCATED" if domain_reasons else "CLOSED"
        residual_closure_basis = (
            evidence_audit.get("basis")
            if evidence_audit.get("status") == "VALID"
            else "provider_residual_mass"
        )
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
            **metrics,
            "isolation_status": ledger_row.get("isolation_status"),
            "inventory_status": ledger_row.get("inventory_status"),
            "end_to_end_residual_kg": _as_mapping(ledger_row.get("mass_ledger")).get("end_to_end_residual_kg"),
            "provider_termination_evidence_status": evidence_audit.get("status"),
            "provider_termination_evidence_used": evidence_audit.get("used") is True,
            "provider_termination_evidence_basis": evidence_audit.get("basis"),
            "provider_termination_evidence_digest": evidence_audit.get("provider_result_digest"),
            "provider_termination_evidence_checks": dict(evidence_audit.get("checks", {})),
            "provider_termination_evidence_blocking_reasons": list(
                evidence_audit.get("blocking_reasons", [])
            ),
            "residual_closure_basis": residual_closure_basis,
            "release_termination_reasons": termination_reasons,
            "operational_execution_reasons": operational_reasons,
            "consequence_domain_reasons": domain_reasons,
            "numerical_release_closed": numerical_release_closed,
            "numerical_closure_status": numerical_closure_status,
            "consequence_domain_status": domain_status,
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
    numerical_closure_counts = Counter(row["numerical_closure_status"] for row in rows)
    domain_status_counts = Counter(row["consequence_domain_status"] for row in rows)
    provider_status_counts = Counter(row["provider_qualification_status"] for row in rows)
    termination_evidence_status_counts = Counter(
        row["provider_termination_evidence_status"] for row in rows
    )
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
        "numerically_closed_case_count": sum(
            row["numerical_release_closed"] is True for row in rows
        ),
        "numerically_open_case_count": sum(
            row["numerical_release_closed"] is not True for row in rows
        ),
        "numerical_closure_status_counts": dict(sorted(numerical_closure_counts.items())),
        "consequence_domain_status_counts": dict(sorted(domain_status_counts.items())),
        "operator_review_required_case_count": numerical_closure_counts.get(
            "NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED", 0
        ),
        "consequence_domain_truncated_case_count": domain_status_counts.get("TRUNCATED", 0),
        "provider_qualification_status_counts": dict(sorted(provider_status_counts.items())),
        "provider_termination_evidence_status_counts": dict(
            sorted(termination_evidence_status_counts.items())
        ),
        "provider_termination_evidence_supplied": provider_termination_evidence is not None,
        "provider_termination_evidence_catalog_path": (
            provider_termination_evidence.get("_record_path")
            if isinstance(provider_termination_evidence, Mapping)
            else None
        ),
        "provider_termination_evidence_catalog_status": (
            provider_termination_evidence.get("status")
            if isinstance(provider_termination_evidence, Mapping)
            else None
        ),
        "provider_termination_evidence_used_case_count": sum(
            row["provider_termination_evidence_used"] is True for row in rows
        ),
        "provider_termination_evidence_invalid_case_count": termination_evidence_status_counts.get(
            "INVALID", 0
        ),
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
