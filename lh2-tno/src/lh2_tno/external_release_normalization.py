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


SCHEMA = "prism.external_release_response_normalization.v1"
MASS_TOLERANCE_KG = 1.0e-8


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
    residual = float(final) + float(released) - float(initial)
    return {
        "schema_version": "prism.provider_mass_balance.v1",
        "initial_mass_kg": float(initial),
        "cumulative_mass_out_kg": float(released),
        "final_mass_kg": float(final),
        "reported_residual_mass_kg": meta.get("residual_mass_kg"),
        "derived_accounting_residual_kg": residual,
        "mass_balance_closed": abs(residual) <= MASS_TOLERANCE_KG,
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
        "result_digest_rebound": isinstance(response.get("provider_result_digest"), str)
        and response.get("provider_result_digest") == release.get("provider_result_digest"),
    }

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

    reasons: list[str] = []
    for name, ok in checks.items():
        if not ok:
            if name == "result_digest_rebound":
                reasons.append("provider response does not carry a digest-bound provider_result_digest")
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


__all__ = ["SCHEMA", "MASS_TOLERANCE_KG", "ExternalReleaseNormalizationError", "audit_external_release_response"]
