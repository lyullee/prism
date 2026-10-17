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
    load_provider_emergency_relief,
    load_provider_release,
    load_provider_release_set,
)


SCHEMA = "prism.provider_release_closure_audit.v1"
MASS_TOLERANCE_KG = 1.0e-8

_OPEN_BASES = {
    None,
    "synthetic_diagnostic_horizon",
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
    def _load_single(item: Mapping[str, Any]) -> Any:
        # Emergency relief is a reviewed provider boundary with a dedicated
        # loader.  Keeping it separate from accidental-leak catalog loading
        # prevents relief packets from being silently treated as random leaks.
        if item.get("event_kind") == "emergency_relief":
            return load_provider_emergency_relief(item)
        return load_provider_release(item)

    try:
        if isinstance(value.get("releases"), list):
            return tuple(_load_single(item) for item in value["releases"])
        if isinstance(value.get("release_sets"), list):
            return tuple(
                release
                for item in value["release_sets"]
                for release in load_provider_release_set(item).releases
            )
        if value.get("provider_export_schema") == "prism.resolved_release_set.v1":
            return tuple(load_provider_release_set(value).releases)
        return (_load_single(value),)
    except ProviderReleaseContractError as error:
        raise ProviderReleaseClosureError(str(error)) from error


def _inventory_termination_evidence(packet: Any, evidence: Mapping[str, Any] | None) -> tuple[dict[str, bool], list[str], str | None]:
    """Audit an external provider's explicit inventory termination ledger.

    LH2 providers can expose either a positive inventory threshold or a
    separately defined *releasable* inventory that is exhausted while a
    non-releasable upstream reserve remains.  Both are accepted only when the
    provider ledger closes against the packet digest and mass totals.  A prose
    termination string alone is never enough evidence.
    """
    checks = {
        "termination_evidence_present": isinstance(evidence, Mapping),
        "termination_evidence_basis": False,
        "termination_evidence_digest_matches": False,
        "termination_evidence_available_matches_packet": False,
        "termination_evidence_release_matches_packet": False,
        "termination_evidence_threshold_positive": False,
        "termination_evidence_remaining_at_or_below_threshold": False,
        "termination_evidence_releasable_definition_present": False,
        "termination_evidence_releasable_remaining_closed": False,
        "termination_evidence_provider_residual_closed": False,
        "termination_evidence_mass_residual_closed": False,
    }
    gaps: list[str] = []
    if not isinstance(evidence, Mapping):
        return checks, ["provider inventory termination evidence is missing"], None
    basis = evidence.get("termination_basis")
    mode = (
        "positive_threshold"
        if basis == "inventory_depletion_positive_threshold"
        else "releasable_inventory"
        if basis == "inventory_depletion_releasable_mass"
        else None
    )
    checks["termination_evidence_basis"] = mode is not None
    if not checks["termination_evidence_basis"]:
        gaps.append("provider termination evidence basis is unsupported")
    digest = evidence.get("provider_result_digest")
    checks["termination_evidence_digest_matches"] = (
        isinstance(digest, str)
        and digest == getattr(packet, "provider_result_digest", None)
    )
    if not checks["termination_evidence_digest_matches"]:
        gaps.append("provider termination evidence result digest does not match packet")
    available = evidence.get("available_mass_kg")
    checks["termination_evidence_available_matches_packet"] = (
        _same(available, packet.available_mass_kg)
    )
    if not checks["termination_evidence_available_matches_packet"]:
        gaps.append("provider termination evidence available mass does not match packet")
    released = evidence.get("cumulative_mass_out_kg")
    checks["termination_evidence_release_matches_packet"] = (
        _same(released, packet.cumulative_mass_out_kg)
    )
    if not checks["termination_evidence_release_matches_packet"]:
        gaps.append("provider termination evidence released mass does not match packet")
    threshold = evidence.get("threshold_mass_kg")
    remaining = evidence.get("remaining_mass_kg")
    checks["termination_evidence_threshold_positive"] = (
        mode == "positive_threshold"
        and _finite(threshold)
        and float(threshold) > MASS_TOLERANCE_KG
    )
    checks["termination_evidence_remaining_at_or_below_threshold"] = (
        mode == "positive_threshold"
        and _finite(remaining)
        and _finite(threshold)
        and float(remaining) <= float(threshold) + MASS_TOLERANCE_KG
    )
    if mode == "positive_threshold":
        if not checks["termination_evidence_threshold_positive"]:
            gaps.append("provider positive inventory threshold is missing or non-positive")
        if not checks["termination_evidence_remaining_at_or_below_threshold"]:
            gaps.append("provider remaining inventory did not reach the declared threshold")
    definition = evidence.get("available_mass_definition")
    checks["termination_evidence_releasable_definition_present"] = (
        mode == "releasable_inventory"
        and isinstance(definition, str)
        and "releasable mass" in definition.lower()
    )
    releasable_remaining = evidence.get("remaining_releasable_mass_kg")
    checks["termination_evidence_releasable_remaining_closed"] = (
        mode == "releasable_inventory"
        and _finite(releasable_remaining)
        and abs(float(releasable_remaining)) <= MASS_TOLERANCE_KG
    )
    checks["termination_evidence_provider_residual_closed"] = (
        mode == "releasable_inventory"
        and _finite(evidence.get("provider_residual_mass_kg"))
        and abs(float(evidence["provider_residual_mass_kg"])) <= MASS_TOLERANCE_KG
    )
    if mode == "releasable_inventory":
        if not checks["termination_evidence_releasable_definition_present"]:
            gaps.append("provider releasable-inventory definition is missing")
        if not checks["termination_evidence_releasable_remaining_closed"]:
            gaps.append("provider releasable inventory did not close at the release boundary")
        if not checks["termination_evidence_provider_residual_closed"]:
            gaps.append("provider upstream residual mass exceeds tolerance")
    residual = evidence.get("max_abs_mass_residual_kg")
    checks["termination_evidence_mass_residual_closed"] = (
        (
            _finite(residual) and abs(float(residual)) <= MASS_TOLERANCE_KG
        )
        or (
            mode == "releasable_inventory"
            and checks["termination_evidence_provider_residual_closed"]
        )
    )
    if not checks["termination_evidence_mass_residual_closed"]:
        gaps.append("provider termination evidence mass residual exceeds tolerance")
    return checks, gaps, mode


def _audit_one(
    packet: Any,
    *,
    packet_index: int,
    termination_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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

    evidence_checks: dict[str, bool] = {}
    evidence_gaps: list[str] = []
    evidence_mode: str | None = None
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
    elif basis == "model_pressure_equalization":
        checks["pressure_equalization_record_present"] = mass is not None
        checks["pressure_equalization_success_declared"] = bool(
            mass is not None and mass.pressure_equalization_success is True
        )
        checks["pressure_equalization_clock_present"] = bool(
            mass is not None
            and _finite(mass.pressure_equalization_time_s)
            and float(mass.pressure_equalization_time_s) <= float(packet.duration_s)
        )
        checks["pressure_equalization_observation_present"] = bool(
            mass is not None
            and _finite(mass.post_pressure_equalization_observation_s)
            and float(mass.post_pressure_equalization_observation_s) > 0.0
        )
        checks["pressure_equalization_flow_closed"] = bool(
            mass is not None
            and _finite(mass.max_post_pressure_equalization_flow_kg_s)
            and float(mass.max_post_pressure_equalization_flow_kg_s) <= 1.0e-12
        )
        checks["pressure_equalization_pressure_boundary_present"] = bool(
            mass is not None
            and _finite(mass.terminal_source_pressure_pa_abs)
            and _finite(mass.ambient_pressure_pa_abs)
            and float(mass.terminal_source_pressure_pa_abs)
            <= float(mass.ambient_pressure_pa_abs) + 1.0e-3
        )
        for name in (
            "pressure_equalization_record_present",
            "pressure_equalization_success_declared",
            "pressure_equalization_clock_present",
            "pressure_equalization_observation_present",
            "pressure_equalization_flow_closed",
            "pressure_equalization_pressure_boundary_present",
        ):
            if not checks[name]:
                gaps.append(f"{name} is missing or inconsistent")
    elif basis == "inventory_depletion":
        evidence_checks, evidence_gaps, evidence_mode = _inventory_termination_evidence(
            packet, termination_evidence
        )
        threshold_closed = not evidence_gaps
        checks["inventory_record_present"] = mass is not None or threshold_closed
        if mass is None and not threshold_closed:
            gaps.append("provider mass balance is required for inventory depletion")
        if mass is None and threshold_closed:
            checks["inventory_initial_matches_packet"] = evidence_checks[
                "termination_evidence_available_matches_packet"
            ]
            checks["inventory_out_matches_packet"] = evidence_checks[
                "termination_evidence_release_matches_packet"
            ]
            checks["inventory_final_depleted"] = evidence_checks[
                "termination_evidence_remaining_at_or_below_threshold"
            ] or evidence_checks["termination_evidence_releasable_remaining_closed"]
            checks["inventory_residual_reported_closed"] = evidence_checks[
                "termination_evidence_mass_residual_closed"
            ]
        elif mass is not None:
            checks["inventory_initial_matches_packet"] = (
                mass.initial_mass_kg is None
                or _same(mass.initial_mass_kg, packet.available_mass_kg)
            )
            # Native gas-unit providers may define ``available_mass_kg`` as
            # the releasable inventory at the atmospheric boundary while the
            # provider mass ledger retains the larger finite-volume initial
            # inventory and its non-releasable residual.  Accept that split
            # only when the provider's total ledger closes exactly and the
            # releasable-inventory sidecar proves that the releasable remainder
            # is zero.  No duration-based depletion is inferred here.
            if (
                not checks["inventory_initial_matches_packet"]
                and evidence_mode == "releasable_inventory"
            ):
                initial = mass.initial_mass_kg
                final = mass.final_mass_kg
                released = mass.cumulative_mass_out_kg
                total_ledger_closed = (
                    _finite(initial)
                    and _finite(final)
                    and _finite(released)
                    and _same(float(initial), float(final) + float(released))
                )
                checks["inventory_releasable_total_ledger_closed"] = (
                    total_ledger_closed
                    and evidence_checks["termination_evidence_releasable_definition_present"]
                    and evidence_checks["termination_evidence_releasable_remaining_closed"]
                    and evidence_checks["termination_evidence_provider_residual_closed"]
                )
                checks["inventory_initial_matches_packet"] = checks[
                    "inventory_releasable_total_ledger_closed"
                ]
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
            if threshold_closed:
                checks["inventory_final_depleted"] = (
                    evidence_checks["termination_evidence_remaining_at_or_below_threshold"]
                    or evidence_checks["termination_evidence_releasable_remaining_closed"]
                )
            for name in (
                "inventory_initial_matches_packet",
                "inventory_out_matches_packet",
                "inventory_final_depleted",
                "inventory_residual_reported_closed",
            ):
                if not checks[name]:
                    gaps.append(f"{name} is false")
        if mass is None and threshold_closed:
            checks["provider_accounting_residual_closed"] = True
        elif mass is None:
            gaps.extend(evidence_gaps)

    if mass is not None and mass.derived_accounting_residual_kg is not None:
        checks["provider_accounting_residual_closed"] = abs(
            float(mass.derived_accounting_residual_kg)
        ) <= MASS_TOLERANCE_KG
        if not checks["provider_accounting_residual_closed"]:
            gaps.append("provider accounting residual exceeds tolerance")
    elif mass is None and basis == "inventory_depletion" and not evidence_gaps:
        checks["provider_accounting_residual_closed"] = True
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
        "termination_evidence": dict(termination_evidence) if termination_evidence else None,
        "termination_evidence_mode": evidence_mode,
        "termination_evidence_checks": evidence_checks,
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
    *,
    termination_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fail-closed closure audit for a flat or two-sided packet."""
    value = _read(packet, "provider release packet")
    packets = _packet_rows(value)
    rows = [
        _audit_one(
            item,
            packet_index=index,
            termination_evidence=termination_evidence,
        )
        for index, item in enumerate(packets)
    ]
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
