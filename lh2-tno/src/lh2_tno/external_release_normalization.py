"""Audit the handoff between an external twin response and a resolved release.

An external equipment model normally writes two records: its native response
(``provider_response.json``) and the atmospheric boundary that PRISM would
consume (``resolved_release.json``).  This module checks that the second record
did not change the event identity, clock, inventory, termination declaration,
or source digest.  It also exposes a mass-ledger *candidate* when the native
response contains enough fields to calculate one.

The result is deliberately diagnostic.  A matching response is not a
qualification sidecar, does not create a frequency, and does not open a
facility QRA gate.  In particular, a fixed diagnostic horizon and a residual
inventory are retained as open evidence rather than being converted to an
inventory-depletion claim.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping
import copy

from .contracts import canonical_digest


SCHEMA = "prism.external_release_response_normalization.v1"
MASS_TOLERANCE_KG = 1.0e-8
COMPRESSIBLE_SOURCE_STATE_FIELDS = (
    "source_specific_entropy_j_kgk",
    "throat_pressure_pa_abs",
    "throat_density_kg_m3",
    "throat_specific_enthalpy_j_kg",
)


class ExternalReleaseNormalizationError(ValueError):
    """Raised when a native response or resolved release cannot be read."""


def _read(value: Mapping[str, Any] | str | Path, label: str) -> Mapping[str, Any]:
    if isinstance(value, (str, Path)):
        try:
            value = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExternalReleaseNormalizationError(f"cannot read {label}: {error}") from error
    if not isinstance(value, Mapping):
        raise ExternalReleaseNormalizationError(f"{label} must be a JSON object")
    return value


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _same(left: Any, right: Any, *, tolerance: float = MASS_TOLERANCE_KG) -> bool:
    return _finite(left) and _finite(right) and math.isclose(
        float(left), float(right), rel_tol=1.0e-8, abs_tol=tolerance
    )


def _response_payload(response: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = response.get("data")
    return payload if isinstance(payload, Mapping) else response


def _mass_ledger(meta: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return only the mass ledger explicitly present in the native response."""

    initial = meta.get("initial_mass_kg")
    final = meta.get("final_mass_kg")
    released = meta.get("cumulative_mass_out_kg", payload.get("cumulative_mass_out_kg"))
    if not all(_finite(value) for value in (initial, final, released)):
        return None
    cumulative_in = meta.get("cumulative_mass_in_kg", 0.0)
    if not _finite(cumulative_in):
        cumulative_in = 0.0
    residual = (
        float(final)
        + float(released)
        - float(initial)
        - float(cumulative_in)
    )
    ledger: dict[str, Any] = {
        "schema_version": "prism.provider_mass_balance.v1",
        "initial_mass_kg": float(initial),
        "cumulative_mass_in_kg": float(cumulative_in),
        "cumulative_mass_out_kg": float(released),
        "final_mass_kg": float(final),
        "reported_residual_mass_kg": meta.get("residual_mass_kg"),
        "derived_accounting_residual_kg": residual,
        "mass_balance_closed": abs(residual) <= MASS_TOLERANCE_KG,
    }
    # These fields are provider observations, not PRISM estimates.  Preserve
    # them when present so downstream release and facility ledgers can retain
    # the explicit isolation/pressure-equalization closure basis.
    for key in (
        "isolation_time_s",
        "post_isolation_observation_s",
        "pressure_equalization_time_s",
        "post_pressure_equalization_observation_s",
        "terminal_source_pressure_pa_abs",
        "ambient_pressure_pa_abs",
        "max_post_pressure_equalization_flow_kg_s",
    ):
        value = meta.get(key)
        if _finite(value):
            ledger[key] = float(value)
    for key in ("isolation_success", "pressure_equalization_success"):
        value = meta.get(key)
        if isinstance(value, bool):
            ledger[key] = value
    dynamic_state_closure = meta.get("dynamic_state_closure")
    if isinstance(dynamic_state_closure, Mapping):
        ledger["dynamic_state_closure"] = copy.deepcopy(dict(dynamic_state_closure))
    return ledger


def _compressible_source_state_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Audit the optional gas-plane handoff inputs without filling fields.

    ``build_compressible_plane_handoff`` consumes the four fields listed in
    ``COMPRESSIBLE_SOURCE_STATE_FIELDS`` for every provider interval.  The
    external response is classified only by its exported step shape: a
    ``mass_flow_kg_s`` series is a gas-plane candidate, while the liquid or
    two-phase series is reported as not applicable.  No atmospheric velocity
    or thermodynamic state is inferred here.
    """

    raw_steps = payload.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    gas_shape = bool(steps) and all(
        isinstance(step, Mapping) and "mass_flow_kg_s" in step for step in steps
    )
    state_count = 0
    missing_by_interval: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        state = step.get("provider_source_state") if isinstance(step, Mapping) else None
        if isinstance(state, Mapping):
            state_count += 1
        missing = [
            field
            for field in COMPRESSIBLE_SOURCE_STATE_FIELDS
            if not isinstance(state, Mapping) or state.get(field) is None
        ]
        if missing:
            missing_by_interval.append({"interval": index, "missing_fields": missing})
    complete = bool(steps) and not missing_by_interval
    if not gas_shape:
        status = "NOT_APPLICABLE_LIQUID_OR_TWO_PHASE_SHAPE"
        blocking_reason = None
        phase_family = "liquid_or_two_phase"
    elif complete:
        status = "COMPLETE_FOR_OPTIONAL_COMPRESSIBLE_HANDOFF"
        blocking_reason = None
        phase_family = "gas"
    else:
        status = "BLOCKED_MISSING_PROVIDER_SOURCE_STATE"
        blocking_reason = (
            "optional compressible handoff is blocked: provider_source_state is incomplete; "
            "atmospheric packet velocity cannot be substituted"
        )
        phase_family = "gas"
    return {
        "status": status,
        "phase_family": phase_family,
        "interval_count": len(steps),
        "provider_source_state_interval_count": state_count,
        "provider_source_state_complete": complete,
        "required_fields": list(COMPRESSIBLE_SOURCE_STATE_FIELDS),
        "missing_by_interval": missing_by_interval,
        "blocking_reason": blocking_reason,
        "handoff_candidate": gas_shape,
    }


def audit_external_release_response(
    resolved_release: Mapping[str, Any] | str | Path,
    provider_response: Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Audit one native response against one PRISM-shaped release record.

    The function only compares fields that the response actually exports.  A
    missing provider result digest, termination sidecar, or physical
    qualification is reported as an open gap; no value is synthesized.
    """

    release = _read(resolved_release, "resolved release")
    response = _read(provider_response, "provider response")
    payload = _response_payload(response)
    meta = payload.get("provider_meta")
    meta = meta if isinstance(meta, Mapping) else {}

    checks: dict[str, bool] = {
        "identity_matches": all(
            release.get(key) == payload.get(key)
            for key in ("event_id", "component_id", "port_id")
        ),
        "clock_matches": _same(release.get("duration_s"), payload.get("duration_s"), tolerance=1.0e-12),
        "available_mass_matches": _same(
            release.get("available_mass_kg"), payload.get("available_mass_kg")
        ),
        "released_mass_matches": _same(
            release.get("cumulative_mass_out_kg"), payload.get("cumulative_mass_out_kg")
        ),
        "termination_basis_matches": release.get("termination_basis")
        == payload.get("termination_basis"),
        "termination_provenance_matches": release.get("termination_provenance")
        == payload.get("termination_provenance"),
        "source_digest_matches": release.get("provider_source_digest")
        == response.get("provider_source_digest"),
        "state_snapshot_digest_present": isinstance(
            response.get("provider_state_snapshot_digest"), str
        )
        and bool(response.get("provider_state_snapshot_digest")),
        # The native response does not need to duplicate the digest as a
        # mutable field.  PRISM's provider contract binds it to the canonical
        # response bytes; recomputing that digest is the exact handoff check.
        "result_digest_rebound": False,
    }

    try:
        computed_result_digest = canonical_digest(response)
    except (TypeError, ValueError, OverflowError):
        computed_result_digest = None
    checks["result_digest_rebound"] = computed_result_digest == release.get(
        "provider_result_digest"
    )

    ledger = _mass_ledger(meta, payload)
    if ledger is not None:
        checks["mass_ledger_present"] = True
        checks["mass_ledger_closed"] = ledger["mass_balance_closed"] is True
    else:
        checks["mass_ledger_present"] = False
        checks["mass_ledger_closed"] = False

    isolation_time = meta.get("isolation_time_s")
    isolation_success = meta.get("isolation_success")
    isolation = {
        "present": _finite(isolation_time) or isinstance(isolation_success, bool),
        "isolation_time_s": isolation_time,
        "isolation_success": isolation_success,
        "within_release_clock": _finite(isolation_time)
        and _finite(payload.get("duration_s"))
        and float(isolation_time) <= float(payload["duration_s"]) + 1.0e-12,
    }
    checks["isolation_evidence_present"] = isolation["present"]
    checks["isolation_clock_valid"] = (
        isolation["within_release_clock"] if isolation["present"] else False
    )
    compressible_source_state = _compressible_source_state_audit(payload)

    reasons: list[str] = []
    for name, ok in checks.items():
        if not ok:
            if name == "result_digest_rebound":
                reasons.append(
                    "canonical provider response digest does not match resolved release provider_result_digest"
                )
            elif name == "mass_ledger_closed":
                reasons.append("native provider mass ledger does not close within tolerance")
            elif name == "isolation_clock_valid":
                reasons.append("native isolation evidence is absent or outside the release clock")
            else:
                reasons.append(f"native provider response check failed: {name}")

    basis = release.get("termination_basis")
    if basis == "synthetic_diagnostic_horizon":
        reasons.append("synthetic diagnostic horizon is not a release termination boundary")
    if basis == "inventory_depletion":
        final_mass = meta.get("final_mass_kg")
        if not _finite(final_mass) or float(final_mass) > MASS_TOLERANCE_KG:
            reasons.append("native inventory still has residual mass; depletion is not proven")
    if release.get("input_origin") in {"synthetic", "model_prediction", None}:
        reasons.append("input origin remains diagnostic and is not qualified actual evidence")
    if compressible_source_state["blocking_reason"]:
        reasons.append(compressible_source_state["blocking_reason"])

    normalized = all(
        checks[name]
        for name in (
            "identity_matches",
            "clock_matches",
            "available_mass_matches",
            "released_mass_matches",
            "termination_basis_matches",
            "termination_provenance_matches",
            "source_digest_matches",
        )
    )
    return {
        "schema_version": SCHEMA,
        "status": "NORMALIZED_PROVIDER_RESPONSE" if normalized else "PROVIDER_RESPONSE_MISMATCH",
        "diagnostic_only": True,
        "event_id": release.get("event_id"),
        "component_id": release.get("component_id"),
        "port_id": release.get("port_id"),
        "provider_model": response.get("provider_model"),
        "provider_state_snapshot_digest": response.get("provider_state_snapshot_digest"),
        "computed_provider_result_digest": computed_result_digest,
        "provider_result_digest_binding": (
            "canonical_response_digest"
            if checks["result_digest_rebound"]
            else "UNBOUND"
        ),
        "compressible_source_state_audit": compressible_source_state,
        "checks": checks,
        "provider_mass_balance_candidate": ledger,
        "isolation_evidence_candidate": isolation,
        "blocking_reasons": list(dict.fromkeys(reasons)),
        "closure_ready": False,
        "qualified_provider_packet_allowed": False,
        "frequency_inference_allowed": False,
        "physical_validation_claim": False,
        "facility_qra_allowed": False,
        "promotion_policy": {
            "provider_result_digest_synthesized": False,
            "termination_evidence_synthesized": False,
            "residual_inventory_replaced_with_zero": False,
            "frequency_assigned": False,
            "facility_qra_promoted": False,
        },
    }


def build_diagnostic_release_rebind(
    resolved_release: Mapping[str, Any] | str | Path,
    provider_response: Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Attach explicitly exported provider ledger evidence to a release copy.

    A native provider commonly writes a complete ``resolved_release.json`` and
    a sibling ``provider_response.json``.  The two records are first checked
    with :func:`audit_external_release_response`; only fields present in the
    response are then copied into a new diagnostic release mapping.  In
    particular, this helper never changes residual inventory to zero, changes
    a termination basis, adds a frequency, or declares qualification.  The
    returned mapping is intended for strict contract validation and downstream
    diagnostic chain execution only.
    """

    release = dict(_read(resolved_release, "resolved release"))
    response = _read(provider_response, "provider response")
    audit = audit_external_release_response(release, response)
    if audit.get("status") != "NORMALIZED_PROVIDER_RESPONSE":
        raise ExternalReleaseNormalizationError(
            "cannot rebind a mismatched provider response to a release boundary"
        )
    checks = audit.get("checks")
    if not isinstance(checks, Mapping) or checks.get("result_digest_rebound") is not True:
        raise ExternalReleaseNormalizationError(
            "diagnostic release rebind requires the canonical provider result digest"
        )

    candidate = audit.get("provider_mass_balance_candidate")
    rebound = copy.deepcopy(release)
    mass_balance_attached = False
    if candidate is not None:
        # ``audit_external_release_response`` also exposes the convenience
        # boolean ``mass_balance_closed``. It is audit metadata, not a field
        # in the strict ProviderMassBalance contract, so keep only contract
        # keys when attaching the copied evidence.
        contract_mass_balance_keys = {
            "schema_version",
            "initial_mass_kg",
            "cumulative_mass_in_kg",
            "cumulative_mass_out_kg",
            "final_mass_kg",
            "reported_residual_mass_kg",
            "derived_accounting_residual_kg",
            "isolation_time_s",
            "post_isolation_observation_s",
            "isolation_success",
            "pressure_equalization_time_s",
            "post_pressure_equalization_observation_s",
            "pressure_equalization_success",
            "terminal_source_pressure_pa_abs",
            "ambient_pressure_pa_abs",
            "max_post_pressure_equalization_flow_kg_s",
            "dynamic_state_closure",
        }
        candidate = {
            key: copy.deepcopy(value)
            for key, value in candidate.items()
            if key in contract_mass_balance_keys
        }
        existing = rebound.get("provider_mass_balance")
        if existing is None:
            rebound["provider_mass_balance"] = copy.deepcopy(candidate)
            mass_balance_attached = True
        elif existing != candidate:
            raise ExternalReleaseNormalizationError(
                "release provider_mass_balance disagrees with the normalized provider response"
            )
        else:
            mass_balance_attached = True

    return {
        "schema_version": "prism.external_release_diagnostic_rebind.v1",
        "status": "DIAGNOSTIC_RELEASE_REBOUND",
        "diagnostic_only": True,
        "release": rebound,
        "audit": audit,
        "mass_balance_attached": mass_balance_attached,
        "promotion": {
            "qualified_provider_packet_allowed": False,
            "frequency_inference_allowed": False,
            "physical_validation_claim": False,
            "facility_qra_allowed": False,
        },
    }


__all__ = [
    "SCHEMA",
    "MASS_TOLERANCE_KG",
    "COMPRESSIBLE_SOURCE_STATE_FIELDS",
    "ExternalReleaseNormalizationError",
    "audit_external_release_response",
    "build_diagnostic_release_rebind",
]
