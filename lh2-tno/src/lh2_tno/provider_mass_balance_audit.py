"""Audit optional provider-state mass ledgers from external LH2 exports.

This module is intentionally diagnostic.  It compares the equipment model's
own ``provider_meta`` ledger with the atmospheric release aggregate and
reports any residual without changing the release packet or inferring a
frequency.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from .equipment_boundary import ProviderMassBalance
from .resolved_liquid_worker import dynamic_state_closure_status


PROVIDER_MASS_BALANCE_AUDIT_SCHEMA = "prism.provider_mass_balance_audit.v1"
_TOLERANCE_KG = 1.0e-8


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def audit_provider_mass_balance_records(
    records: Sequence[Mapping[str, Any]],
    *,
    source_root: str | None = None,
) -> dict[str, Any]:
    """Return one auditable row per external provider response."""

    rows: list[dict[str, Any]] = []
    for index, response in enumerate(records):
        data = response.get("data") if isinstance(response, Mapping) else None
        data = data if isinstance(data, Mapping) else {}
        metadata = data.get("provider_meta")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        cumulative_out = _finite(data.get("cumulative_mass_out_kg"))
        payload: dict[str, Any] = {
            "schema_version": "prism.provider_mass_balance.v1",
            "cumulative_mass_out_kg": cumulative_out,
        }
        for key in (
            "initial_mass_kg",
            "cumulative_mass_in_kg",
            "final_mass_kg",
            "isolation_time_s",
            "post_isolation_observation_s",
            "pressure_equalization_time_s",
            "post_pressure_equalization_observation_s",
            "terminal_source_pressure_pa_abs",
            "ambient_pressure_pa_abs",
            "max_post_pressure_equalization_flow_kg_s",
        ):
            value = _finite(metadata.get(key))
            if value is not None:
                payload[key] = value
        residual = _finite(metadata.get("residual_mass_kg"))
        if residual is not None:
            payload["reported_residual_mass_kg"] = residual
        if isinstance(metadata.get("isolation_success"), bool):
            payload["isolation_success"] = metadata["isolation_success"]
        if isinstance(metadata.get("pressure_equalization_success"), bool):
            payload["pressure_equalization_success"] = metadata[
                "pressure_equalization_success"
            ]
        if "dynamic_state_closure" in metadata:
            # Preserve the provider's explicit dynamic-state qualification
            # record.  The audit validates it through ProviderMassBalance;
            # it never infers this record from a closed scalar mass balance.
            payload["dynamic_state_closure"] = metadata["dynamic_state_closure"]
        initial = _finite(payload.get("initial_mass_kg"))
        final = _finite(payload.get("final_mass_kg"))
        cumulative_in = _finite(payload.get("cumulative_mass_in_kg")) or 0.0
        if initial is not None and final is not None and cumulative_out is not None:
            payload["derived_accounting_residual_kg"] = (
                final + cumulative_out - initial - cumulative_in
            )
        try:
            balance = ProviderMassBalance.model_validate(payload)
        except (TypeError, ValueError) as error:
            balance = None
            validation_error = str(error)
        else:
            validation_error = None

        if balance is None:
            status = "UNAVAILABLE" if not metadata else "PARTIAL_OR_INVALID"
        elif balance.derived_accounting_residual_kg is None:
            status = "PARTIAL"
        elif abs(balance.derived_accounting_residual_kg) <= _TOLERANCE_KG:
            status = "CLOSED"
        else:
            status = "UNBALANCED"
        event_kind = data.get("event_kind")
        if event_kind in {"accidental_leak", "emergency_relief"}:
            dynamic_audit = dynamic_state_closure_status(
                {
                    "provider_mass_balance": payload,
                    "termination_basis": data.get("termination_basis"),
                }
            )
            dynamic_status = "READY" if dynamic_audit["ready"] else "BLOCKED"
        else:
            dynamic_audit = {
                "ready": None,
                "checks": {},
                "blocking_reasons": [],
            }
            dynamic_status = "NOT_APPLICABLE"
        rows.append(
            {
                "record_index": index,
                "provider_model": response.get("provider_model") if isinstance(response, Mapping) else None,
                "event_id": data.get("event_id"),
                "component_id": data.get("component_id"),
                "termination_basis": data.get("termination_basis"),
                "available_mass_kg": _finite(data.get("available_mass_kg")),
                "cumulative_mass_out_kg": cumulative_out,
                "provider_mass_balance": (
                    balance.model_dump(mode="json") if balance is not None else payload
                ),
                "status": status,
                "validation_error": validation_error,
                "dynamic_state_closure_status": dynamic_status,
                "dynamic_state_closure_audit": dynamic_audit,
            }
        )

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    dynamic_status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["dynamic_state_closure_status"])
        dynamic_status_counts[status] = dynamic_status_counts.get(status, 0) + 1
    return {
        "schema_version": PROVIDER_MASS_BALANCE_AUDIT_SCHEMA,
        "source_root": source_root,
        "record_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "dynamic_state_closure_status_counts": dict(sorted(dynamic_status_counts.items())),
        "dynamic_state_closure_ready_record_count": dynamic_status_counts.get("READY", 0),
        "dynamic_state_closure_blocked_record_count": dynamic_status_counts.get("BLOCKED", 0),
        "closed_record_count": status_counts.get("CLOSED", 0),
        "unbalanced_record_count": status_counts.get("UNBALANCED", 0),
        "diagnostic_only": True,
        "promotion_allowed": False,
        "rows": rows,
        "interpretation": (
            "CLOSED means the provider's declared initial/final/input/output ledger "
            "closes within tolerance. UNBALANCED remains visible and blocks strict "
            "release-boundary promotion; it is never repaired by PRISM."
        ),
    }


__all__ = [
    "PROVIDER_MASS_BALANCE_AUDIT_SCHEMA",
    "audit_provider_mass_balance_records",
]
