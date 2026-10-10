"""Audit provider release packets before facility promotion.

This module is the strict intake boundary for the fields that are often
missing at the end of a release calculation: an explicit termination clock,
provider inventory closure, and reviewed isolation evidence.  It only audits
the packet supplied by an equipment model.  It never estimates a missing
duration, replaces a residual with zero, assigns a frequency, or qualifies a
provider packet by itself.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import math
from pathlib import Path
from typing import Any

from .provider_release import (
    ProviderReleaseContractError,
    load_provider_release,
    load_provider_release_set,
)


SCHEMA = "prism.provider_release_closure_audit.v1"
MASS_TOLERANCE_KG = 1.0e-8

_OPEN_BASES = {
    None,
    "synthetic_diagnostic_horizon",
    "model_pressure_equalization",
    "inventory_over_600s",
}


class ProviderReleaseClosureError(ValueError):
    """Raised when a release packet cannot be read or audited."""


def _read(value: Mapping[str, Any] | str | Path, label: str) -> Mapping[str, Any]:
    if isinstance(value, (str, Path)):
        try:
            import json

            value = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ProviderReleaseClosureError(f"cannot read {label}: {error}") from error
    if not isinstance(value, Mapping):
        raise ProviderReleaseClosureError(f"{label} must be an object")
    return value


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _same(left: Any, right: Any) -> bool:
    return _finite(left) and _finite(right) and math.isclose(
        float(left), float(right), rel_tol=1.0e-8, abs_tol=MASS_TOLERANCE_KG
    )


def _packet_rows(value: Mapping[str, Any]) -> tuple[Any, ...]:
    try:
        if isinstance(value.get("releases"), list):
            return tuple(load_provider_release(item) for item in value["releases"])
        if isinstance(value.get("release_sets"), list):
            return tuple(
                release
                for item in value["release_sets"]
                for release in load_provider_release_set(item).releases
            )
        if value.get("provider_export_schema") == "prism.resolved_release_set.v1":
            return tuple(load_provider_release_set(value).releases)
        return (load_provider_release(value),)
    except ProviderReleaseContractError as error:
        raise ProviderReleaseClosureError(str(error)) from error


def _audit_one(packet: Any, *, packet_index: int) -> dict[str, Any]:
    basis = packet.termination_basis
    mass = packet.provider_mass_balance
    gaps: list[str] = []
    checks: dict[str, bool] = {}

    checks["termination_basis_present"] = basis is not None
    if basis in _OPEN_BASES:
        gaps.append(
            "termination basis is absent, synthetic, pressure-equalization, or fixed horizon"
        )
    checks["termination_provenance_present"] = bool(
        isinstance(packet.termination_provenance, str)
        and packet.termination_provenance.strip()
    )
    if not checks["termination_provenance_present"]:
        gaps.append("termination provenance is missing")
    checks["non_synthetic_input"] = packet.input_origin != "synthetic"
    if not checks["non_synthetic_input"]:
        gaps.append("synthetic input origin cannot close a provider boundary")

    checks["packet_mass_within_available_inventory"] = (
        packet.cumulative_mass_out_kg <= packet.available_mass_kg + MASS_TOLERANCE_KG
    )
    if not checks["packet_mass_within_available_inventory"]:
        gaps.append("cumulative release exceeds available provider inventory")

    if basis == "reviewed_isolation_success":
        checks["isolation_record_present"] = mass is not None
        checks["isolation_success_declared"] = bool(
            mass is not None and mass.isolation_success is True
        )
        checks["isolation_clock_present"] = bool(
            mass is not None
            and _finite(mass.isolation_time_s)
            and float(mass.isolation_time_s) <= float(packet.duration_s)
        )
        for name, ok in (
            ("isolation_record_present", checks["isolation_record_present"]),
            ("isolation_success_declared", checks["isolation_success_declared"]),
            ("isolation_clock_present", checks["isolation_clock_present"]),
        ):
            if not ok:
                gaps.append(f"{name} is missing or inconsistent")
    elif basis == "inventory_depletion":
        checks["inventory_record_present"] = mass is not None
        if mass is None:
            gaps.append("provider mass balance is required for inventory depletion")
        else:
            checks["inventory_initial_matches_packet"] = (
                mass.initial_mass_kg is None
                or _same(mass.initial_mass_kg, packet.available_mass_kg)
            )
            checks["inventory_out_matches_packet"] = (
                mass.cumulative_mass_out_kg is None
                or _same(mass.cumulative_mass_out_kg, packet.cumulative_mass_out_kg)
            )
            checks["inventory_final_depleted"] = (
                _finite(mass.final_mass_kg)
                and abs(float(mass.final_mass_kg)) <= MASS_TOLERANCE_KG
            )
            checks["inventory_residual_reported_closed"] = (
                mass.reported_residual_mass_kg is None
                or abs(float(mass.reported_residual_mass_kg)) <= MASS_TOLERANCE_KG
            )
            for name in (
                "inventory_initial_matches_packet",
                "inventory_out_matches_packet",
                "inventory_final_depleted",
                "inventory_residual_reported_closed",
            ):
                if not checks[name]:
                    gaps.append(f"{name} is false")

    if mass is not None and mass.derived_accounting_residual_kg is not None:
        checks["provider_accounting_residual_closed"] = abs(
            float(mass.derived_accounting_residual_kg)
        ) <= MASS_TOLERANCE_KG
        if not checks["provider_accounting_residual_closed"]:
            gaps.append("provider accounting residual exceeds tolerance")
    else:
        checks["provider_accounting_residual_closed"] = basis in {
            "emergency_relief_discharge",
            "two_sided_rupture",
        }

    gaps = list(dict.fromkeys(gaps))
    return {
        "packet_index": packet_index,
        "event_id": packet.event_id,
        "component_id": packet.component_id,
        "port_id": packet.port_id,
        "event_kind": packet.event_kind,
        "input_origin": packet.input_origin,
        "termination_basis": basis,
        "termination_provenance": packet.termination_provenance,
        "duration_s": packet.duration_s,
        "available_mass_kg": packet.available_mass_kg,
        "cumulative_mass_out_kg": packet.cumulative_mass_out_kg,
        "provider_mass_balance": (
            mass.model_dump(mode="json") if mass is not None else None
        ),
        "checks": checks,
        "closure_status": (
            "CLOSURE_READY_FOR_QUALIFICATION" if not gaps else "CLOSURE_EVIDENCE_OPEN"
        ),
        "blocking_reasons": gaps,
        "qualified_provider_packet_allowed": False,
        "facility_qra_allowed": False,
    }


def audit_provider_release_closure(
    packet: Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Return a fail-closed closure audit for a flat or two-sided packet."""
    value = _read(packet, "provider release packet")
    packets = _packet_rows(value)
    rows = [_audit_one(item, packet_index=index) for index, item in enumerate(packets)]
    status_counts = Counter(row["closure_status"] for row in rows)
    blocking = [
        f"packet[{row['packet_index']}]: {reason}"
        for row in rows
        for reason in row["blocking_reasons"]
    ]
    closed = not blocking
    return {
        "schema_version": SCHEMA,
        "status": "CLOSURE_READY_FOR_QUALIFICATION" if closed else "CLOSURE_EVIDENCE_OPEN",
        "event_id": value.get("event_id") or rows[0].get("event_id"),
        "component_id": value.get("component_id") or rows[0].get("component_id"),
        "packet_schema": value.get("provider_export_schema"),
        "packet_count": len(rows),
        "packet_rows": rows,
        "closure_status_counts": dict(sorted(status_counts.items())),
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "promotion_gates": {
            "closure_ready": closed,
            "qualified_provider_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "physical_validation_claim": False,
            "diagnostic_only": True,
        },
        "tolerances": {"mass_residual_kg": MASS_TOLERANCE_KG},
    }


__all__ = [
    "SCHEMA",
    "MASS_TOLERANCE_KG",
    "ProviderReleaseClosureError",
    "audit_provider_release_closure",
]
