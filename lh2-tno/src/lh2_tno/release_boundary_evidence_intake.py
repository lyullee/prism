"""Validate provider responses to open LH2 release-boundary requests.

The request exporter identifies *what* a provider must supply.  This module
checks the returned packet before it is handed back to the case-level release
audit.  It is intentionally an intake contract, not a provider qualification
or facility-QRA promotion step: it never fills missing values, changes a
termination basis, assigns a frequency, or treats a diagnostic horizon as a
physical stop.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any


SCHEMA = "prism.release_boundary_evidence_intake.v1"
RESPONSE_SCHEMA = "prism.release_boundary_evidence_response.v1"
_MASS_TOLERANCE_KG = 1.0e-8
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_SUPPORTED_NON_HORIZON_BASES = {
    "reviewed_isolation_success",
    "inventory_depletion_positive_threshold",
    "inventory_depletion_releasable_mass",
    "model_pressure_equalization",
}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> bool:
    number = _finite(value)
    return number is not None and number > 0.0


def _nonnegative(value: Any) -> bool:
    number = _finite(value)
    return number is not None and number >= 0.0


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value.strip()))


def _same_sequence(left: Any, right: Any) -> bool:
    if not isinstance(left, Sequence) or isinstance(left, (str, bytes)):
        return False
    if not isinstance(right, Sequence) or isinstance(right, (str, bytes)):
        return False
    return [str(item) for item in left] == [str(item) for item in right]


def _same_mass(left: Any, right: Any, tolerance: float = _MASS_TOLERANCE_KG) -> bool:
    a = _finite(left)
    b = _finite(right)
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-8, abs_tol=tolerance)


def _identity_checks(request: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, bool]:
    expected = request.get("identity")
    actual = response.get("identity")
    expected = expected if isinstance(expected, Mapping) else {}
    actual = actual if isinstance(actual, Mapping) else {}
    return {
        "event_id_matches": actual.get("event_id") == expected.get("event_id"),
        "case_key_matches": actual.get("case_key") == expected.get("case_key"),
        "asset_id_matches": actual.get("asset_id") == expected.get("asset_id"),
        "component_id_matches": actual.get("component_id") == expected.get("component_id"),
        "port_ids_match": _same_sequence(actual.get("port_ids"), expected.get("port_ids")),
        "operating_mode_matches": actual.get("operating_mode") == expected.get("operating_mode"),
        "hazop_scenario_id_matches": actual.get("hazop_scenario_id") == expected.get("hazop_scenario_id"),
    }


def _current_digest_matches(request: Mapping[str, Any], response: Mapping[str, Any]) -> bool:
    current = request.get("current_boundary")
    current = current if isinstance(current, Mapping) else {}
    digest = current.get("provider_result_digest")
    return (
        isinstance(digest, str)
        and bool(digest)
        and response.get("supersedes_provider_result_digest") == digest
    )


def _mass_checks(response: Mapping[str, Any]) -> tuple[dict[str, bool], list[str]]:
    checks = {
        "initial_inventory_present": _nonnegative(response.get("initial_inventory_kg")),
        "cumulative_mass_out_present": _nonnegative(response.get("cumulative_mass_out_kg")),
        "final_inventory_present": _nonnegative(response.get("final_inventory_kg")),
        "mass_residual_present": _finite(response.get("mass_residual_kg")) is not None,
        "mass_residual_closed": (
            _finite(response.get("mass_residual_kg")) is not None
            and abs(float(response["mass_residual_kg"])) <= _MASS_TOLERANCE_KG
        ),
        "mass_balance_matches": False,
    }
    if all(checks[key] for key in ("initial_inventory_present", "cumulative_mass_out_present", "final_inventory_present")):
        initial = float(response["initial_inventory_kg"])
        released = float(response["cumulative_mass_out_kg"])
        final = float(response["final_inventory_kg"])
        residual = float(response.get("mass_residual_kg", float("nan")))
        checks["mass_balance_matches"] = math.isclose(
            initial,
            released + final + residual,
            rel_tol=1e-8,
            abs_tol=_MASS_TOLERANCE_KG,
        )
    reasons = [f"{name}" for name, ok in checks.items() if not ok]
    return checks, reasons


def _common_checks(response: Mapping[str, Any]) -> tuple[dict[str, bool], list[str]]:
    checks = {
        "provider_source_digest_present": _sha256(response.get("provider_source_digest")),
        "provider_result_digest_present": _sha256(response.get("provider_result_digest")),
        "positive_termination_time": _positive(response.get("termination_time_s")),
        "termination_history_present": (
            _finite(response.get("termination_history_sample_count")) is not None
            and float(response["termination_history_sample_count"]) >= 2
        ),
        "termination_provenance_present": bool(
            isinstance(response.get("termination_provenance"), str)
            and response["termination_provenance"].strip()
        ),
        "stopping_event_present": isinstance(response.get("stopping_event"), Mapping),
    }
    reasons = [f"{name}" for name, ok in checks.items() if not ok]
    return checks, reasons


def _family_checks(
    request: Mapping[str, Any], response: Mapping[str, Any]
) -> tuple[dict[str, bool], list[str]]:
    basis = request.get("termination_basis_observed")
    checks: dict[str, bool] = {}
    reasons: list[str] = []
    if basis == "emergency_relief_discharge":
        checks.update({
            "response_basis_is_emergency_relief": response.get("termination_basis") == "emergency_relief_discharge",
            "event_kind_is_emergency_relief": response.get("event_kind") == "emergency_relief",
            "source_operator_is_emergency_relief": response.get("source_operator") == "equipment_emergency_relief",
            "failure_opening_not_declared": response.get("failure_opening_diameter_m") in (None, ""),
            "relief_setpoint_positive": _positive(response.get("relief_setpoint_pa")),
            "relief_capacity_positive": _positive(response.get("relief_capacity_kg_s")),
            "discharge_complete_declared": response.get("discharge_complete") is True,
        })
    elif basis == "inventory_over_600s":
        response_basis = response.get("termination_basis")
        checks["response_replaces_horizon_basis"] = response_basis in _SUPPORTED_NON_HORIZON_BASES
        checks["horizon_not_reused_as_stop"] = response_basis != "inventory_over_600s"
        if response_basis == "reviewed_isolation_success":
            checks.update({
                "isolation_success_declared": response.get("isolation_success") is True,
                "isolation_time_present": _positive(response.get("isolation_time_s")),
                "post_isolation_observation_present": _positive(response.get("post_isolation_observation_s")),
                "post_isolation_zero_flow_declared": response.get("post_isolation_zero_flow") is True,
            })
        elif response_basis == "inventory_depletion_positive_threshold":
            checks.update({
                "depletion_threshold_positive": _positive(response.get("threshold_mass_kg")),
                "remaining_at_or_below_threshold": (
                    _finite(response.get("remaining_mass_kg")) is not None
                    and _finite(response.get("threshold_mass_kg")) is not None
                    and float(response["remaining_mass_kg"]) <= float(response["threshold_mass_kg"]) + _MASS_TOLERANCE_KG
                ),
            })
        elif response_basis == "inventory_depletion_releasable_mass":
            definition = response.get("available_mass_definition")
            checks.update({
                "releasable_definition_present": isinstance(definition, str) and "releasable" in definition.lower(),
                "remaining_releasable_mass_closed": (
                    _finite(response.get("remaining_releasable_mass_kg")) is not None
                    and abs(float(response["remaining_releasable_mass_kg"])) <= _MASS_TOLERANCE_KG
                ),
                "provider_residual_mass_closed": (
                    _finite(response.get("provider_residual_mass_kg")) is not None
                    and abs(float(response["provider_residual_mass_kg"])) <= _MASS_TOLERANCE_KG
                ),
            })
        elif response_basis == "model_pressure_equalization":
            checks.update({
                "pressure_equalization_declared": response.get("pressure_equalization_confirmed") is True,
                "terminal_pressure_present": _finite(response.get("terminal_pressure_pa")) is not None,
                "downstream_pressure_present": _finite(response.get("downstream_pressure_pa")) is not None,
                "pressure_tolerance_present": _positive(response.get("pressure_equalization_tolerance_pa")),
                "pressure_difference_closed": (
                    _finite(response.get("pressure_difference_pa")) is not None
                    and _finite(response.get("pressure_equalization_tolerance_pa")) is not None
                    and abs(float(response["pressure_difference_pa"])) <= float(response["pressure_equalization_tolerance_pa"])
                ),
                "post_equalization_observation_present": _positive(response.get("post_equalization_observation_s")),
            })
    else:
        checks["request_basis_supported"] = False
    reasons.extend(name for name, ok in checks.items() if not ok)
    return checks, reasons


def validate_release_boundary_evidence_response(
    request_root: Mapping[str, Any],
    response_root: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate responses against exact open requests.

    A valid response is marked ``RELEASE_BOUNDARY_REAUDIT_READY`` only.  The
    case-level audit must still consume the provider packet and a separate
    qualification/physical-validation review remains required.
    """
    requests = _rows(request_root.get("requests")) if isinstance(request_root, Mapping) else []
    if isinstance(response_root, Mapping):
        responses = _rows(response_root.get("responses"))
        if not responses and response_root.get("request_id") is not None:
            responses = [response_root]
    else:
        responses = _rows(response_root)
    request_by_id = {str(item.get("request_id")): item for item in requests if item.get("request_id") is not None}
    response_by_id: dict[str, list[Mapping[str, Any]]] = {}
    for response in responses:
        response_by_id.setdefault(str(response.get("request_id")), []).append(response)
    rows: list[dict[str, Any]] = []
    for request_id, request in sorted(request_by_id.items()):
        candidates = response_by_id.get(request_id, [])
        if len(candidates) != 1:
            rows.append({
                "request_id": request_id,
                "status": "MISSING" if not candidates else "INVALID",
                "checks": {"exactly_one_response": False},
                "blocking_reasons": ["exactly_one_response_required"],
                "release_boundary_reaudit_ready": False,
            })
            continue
        response = candidates[0]
        identity = _identity_checks(request, response)
        common, common_reasons = _common_checks(response)
        family, family_reasons = _family_checks(request, response)
        checks = {
            **identity,
            "response_schema_matches": response.get("schema_version") == RESPONSE_SCHEMA,
            "request_id_matches": response.get("request_id") == request_id,
            "superseded_digest_matches": _current_digest_matches(request, response),
            **common,
        }
        reasons = [
            name for name, ok in checks.items() if not ok
        ] + common_reasons + family_reasons
        mass_checks, mass_reasons = _mass_checks(response)
        checks.update(mass_checks)
        reasons.extend(mass_reasons)
        reasons = list(dict.fromkeys(reasons))
        ready = not reasons
        rows.append({
            "request_id": request_id,
            "status": "RELEASE_BOUNDARY_REAUDIT_READY" if ready else "INVALID",
            "checks": checks,
            "blocking_reasons": reasons,
            "provider_result_digest": response.get("provider_result_digest"),
            "termination_basis": response.get("termination_basis"),
            "release_boundary_reaudit_ready": ready,
            "provider_qualification_claim": False,
            "physical_validation_claim": False,
            "facility_qra_promotion_allowed": False,
        })
    extra = sorted(set(response_by_id) - set(request_by_id))
    if extra:
        rows.extend({
            "request_id": request_id,
            "status": "INVALID",
            "checks": {"request_id_known": False},
            "blocking_reasons": ["response_request_id_not_in_open_request_set"],
            "release_boundary_reaudit_ready": False,
            "provider_qualification_claim": False,
            "physical_validation_claim": False,
            "facility_qra_promotion_allowed": False,
        } for request_id in extra)
    ready_count = sum(row.get("release_boundary_reaudit_ready") is True for row in rows)
    return {
        "schema_version": SCHEMA,
        "response_schema_version": RESPONSE_SCHEMA,
        "status": "RELEASE_BOUNDARY_REAUDIT_READY" if rows and ready_count == len(rows) else "RESPONSE_EVIDENCE_OPEN",
        "request_count": len(requests),
        "response_count": len(responses),
        "row_count": len(rows),
        "ready_count": ready_count,
        "rows": rows,
        "extra_request_ids": extra,
        "policy": {
            "duration_inference_allowed": False,
            "termination_basis_substitution_allowed": False,
            "frequency_inference_allowed": False,
            "provider_qualification_claim": False,
            "physical_validation_claim": False,
            "facility_qra_promotion_allowed": False,
            "diagnostic_only": True,
        },
    }


def build_release_boundary_evidence_response_template(
    request_root: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a blank, family-specific response template without fake values."""
    templates: list[dict[str, Any]] = []
    for request in _rows(request_root.get("requests")):
        basis = request.get("termination_basis_observed")
        response: dict[str, Any] = {
            "schema_version": RESPONSE_SCHEMA,
            "request_id": request.get("request_id"),
            "supersedes_provider_result_digest": (
                request.get("current_boundary", {}).get("provider_result_digest")
                if isinstance(request.get("current_boundary"), Mapping)
                else None
            ),
            "identity": request.get("identity", {}),
            "provider_source_digest": None,
            "provider_result_digest": None,
            "termination_basis": None,
            "termination_time_s": None,
            "termination_history_sample_count": None,
            "termination_provenance": None,
            "stopping_event": None,
            "initial_inventory_kg": None,
            "cumulative_mass_out_kg": None,
            "final_inventory_kg": None,
            "mass_residual_kg": None,
        }
        if basis == "emergency_relief_discharge":
            response.update({
                "event_kind": "emergency_relief",
                "source_operator": "equipment_emergency_relief",
                "failure_opening_diameter_m": None,
                "relief_setpoint_pa": None,
                "relief_capacity_kg_s": None,
                "discharge_complete": None,
            })
        elif basis == "inventory_over_600s":
            response.update({
                "termination_basis": "reviewed_isolation_success",
                "isolation_success": None,
                "isolation_time_s": None,
                "post_isolation_observation_s": None,
                "post_isolation_zero_flow": None,
                "threshold_mass_kg": None,
                "remaining_mass_kg": None,
                "available_mass_definition": None,
                "remaining_releasable_mass_kg": None,
                "provider_residual_mass_kg": None,
                "pressure_equalization_confirmed": None,
                "terminal_pressure_pa": None,
                "downstream_pressure_pa": None,
                "pressure_equalization_tolerance_pa": None,
                "pressure_difference_pa": None,
                "post_equalization_observation_s": None,
            })
        templates.append(response)
    return {
        "schema_version": RESPONSE_SCHEMA,
        "status": "TEMPLATE_ONLY",
        "responses": templates,
        "policy": {
            "placeholder_values_are_not_evidence": True,
            "facility_qra_promotion_allowed": False,
            "diagnostic_only": True,
        },
    }


__all__ = [
    "SCHEMA",
    "RESPONSE_SCHEMA",
    "build_release_boundary_evidence_response_template",
    "validate_release_boundary_evidence_response",
]
