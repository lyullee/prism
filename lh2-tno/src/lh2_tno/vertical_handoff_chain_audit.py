"""Audit the operator-limited vertical-handoff events in the facility ledger.

The generic facility campaign contains five vertical-handoff events whose
native ``resolved_release.v1`` records live in a separate diagnostic catalog.
This module joins those records by provider result digest and checks the same
release -> termination/inventory -> final-harm identity used by the qualified
packet closure audit.  The records remain synthetic/operator-limited and can
never promote provider qualification, frequency, physical validation, or
facility QRA.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from .chain_closure_audit import _aggregate_ir, _atom_identity_matches_case, _fn_curve


VERTICAL_HANDOFF_CHAIN_AUDIT_SCHEMA = "prism.vertical_handoff_chain_audit.v1"
VERTICAL_HANDOFF_PREFIX = "generic-lh2-full-scope-example/vertical-handoff/"


class VerticalHandoffChainAuditError(ValueError):
    """Raised when a vertical-handoff audit input is malformed."""


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _same_number(left: Any, right: Any, *, rel_tol: float = 1.0e-8, abs_tol: float = 1.0e-12) -> bool:
    return _finite(left) and _finite(right) and math.isclose(
        float(left), float(right), rel_tol=rel_tol, abs_tol=abs_tol
    )


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise VerticalHandoffChainAuditError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise VerticalHandoffChainAuditError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _catalog_rows(catalog: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Normalize a catalog keyed by source event ID or a release array."""
    if isinstance(catalog.get("releases"), list):
        return _rows(catalog["releases"], "release_catalog.releases")
    if isinstance(catalog.get("release_sets"), list):
        rows = [
            endpoint
            for release_set in catalog["release_sets"]
            if isinstance(release_set, Mapping)
            for endpoint in release_set.get("releases", ())
        ]
        return _rows(rows, "release_catalog.release_sets.releases")
    rows = []
    for source_event_id, row in catalog.items():
        if isinstance(row, Mapping):
            rows.append({"_catalog_key": str(source_event_id), **row})
    if not rows:
        raise VerticalHandoffChainAuditError("release_catalog has no release rows")
    return rows


def _digests(identity: Mapping[str, Any]) -> tuple[str, ...]:
    value = identity.get("provider_result_digests", ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _case_packet_mismatches(catalog_row: Mapping[str, Any], case: Mapping[str, Any]) -> list[str]:
    identity = case.get("provider_packet_identity")
    if not isinstance(identity, Mapping):
        return ["case provider_packet_identity missing"]
    mismatches: list[str] = []
    catalog_digest = catalog_row.get("provider_result_digest")
    if catalog_digest not in _digests(identity):
        mismatches.append("provider result digest differs from catalog")
    for field in ("duration_s", "available_mass_kg", "cumulative_mass_out_kg"):
        values = identity.get(field)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or len(values) != 1:
            mismatches.append(f"case identity {field} missing")
        elif not _same_number(values[0], catalog_row.get(field)):
            mismatches.append(f"case identity {field} differs from catalog")
    termination = case.get("termination")
    if not isinstance(termination, Mapping) or not _same_number(
        termination.get("time_s"), catalog_row.get("duration_s")
    ):
        mismatches.append("termination time differs from catalog duration")
    mass_ledger = case.get("mass_ledger")
    if not isinstance(mass_ledger, Mapping) or not _same_number(
        mass_ledger.get("released_kg"), catalog_row.get("cumulative_mass_out_kg")
    ):
        mismatches.append("released mass differs from catalog cumulative mass")
    return mismatches


def build_vertical_handoff_chain_audit(
    campaign_result: Mapping[str, Any],
    release_catalog: Mapping[str, Any],
    *,
    event_prefix: str = VERTICAL_HANDOFF_PREFIX,
    base_chain_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a diagnostic closure record for the five vertical events."""
    if not isinstance(campaign_result, Mapping):
        raise VerticalHandoffChainAuditError("campaign_result must be an object")
    if not isinstance(release_catalog, Mapping):
        raise VerticalHandoffChainAuditError("release_catalog must be an object")
    events = _rows(campaign_result.get("events"), "campaign_result.events")
    cases = _rows(campaign_result.get("cases"), "campaign_result.cases")
    atoms = _rows(campaign_result.get("risk_atoms"), "campaign_result.risk_atoms")
    catalog_rows = _catalog_rows(release_catalog)
    catalog_by_digest = {
        str(row.get("provider_result_digest")): row
        for row in catalog_rows
        if isinstance(row.get("provider_result_digest"), str)
    }
    event_rows_by_id = {
        str(row.get("id")): row for row in events if str(row.get("id", "")).startswith(event_prefix)
    }
    cases_by_event: dict[str, list[Mapping[str, Any]]] = {}
    atoms_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for case in cases:
        event_id = str(case.get("event_id", ""))
        if event_id.startswith(event_prefix):
            cases_by_event.setdefault(event_id, []).append(case)
    for atom in atoms:
        event_id = str(atom.get("event_id", ""))
        if event_id.startswith(event_prefix):
            atoms_by_event.setdefault(event_id, []).append(atom)

    audit_rows: list[dict[str, Any]] = []
    mismatch_event_ids: list[str] = []
    closed_event_count = 0
    handoff_field_count = 0
    for event_id in sorted(event_rows_by_id):
        event_cases = cases_by_event.get(event_id, [])
        event_atoms = atoms_by_event.get(event_id, [])
        reasons: list[str] = []
        digests = {
            digest
            for case in event_cases
            for digest in _digests(case.get("provider_packet_identity", {}))
        }
        matching_catalog = [catalog_by_digest[digest] for digest in digests if digest in catalog_by_digest]
        if len(matching_catalog) != 1:
            reasons.append("event does not resolve to exactly one catalog release digest")
        else:
            catalog_row = matching_catalog[0]
            for case in event_cases:
                reasons.extend(_case_packet_mismatches(catalog_row, case))
            if not isinstance(catalog_row.get("vertical_handoff"), Mapping):
                reasons.append("vertical_handoff boundary missing")
            else:
                states = catalog_row["vertical_handoff"].get("states")
                if not isinstance(states, list) or len(states) < 2:
                    reasons.append("vertical_handoff state history missing")
                else:
                    handoff_field_count += 1
        if not event_cases:
            reasons.append("no campaign case")
        if not event_atoms:
            reasons.append("no final-harm atom")
        for atom in event_atoms:
            harm = atom.get("receptor_harm_low_high")
            deaths = atom.get("expected_deaths_low_high")
            if not isinstance(harm, Mapping) or not isinstance(deaths, Sequence) or len(deaths) != 2:
                reasons.append("final damage fields missing")
            if not any(_atom_identity_matches_case(atom, case) for case in event_cases):
                reasons.append("risk atom provider/case identity mismatch")
        reasons = list(dict.fromkeys(reasons))
        closed = not reasons
        if closed:
            closed_event_count += 1
        else:
            mismatch_event_ids.append(event_id)
        audit_rows.append(
            {
                "event_id": event_id,
                "component_id": event_rows_by_id[event_id].get("model_component_id"),
                "case_count": len(event_cases),
                "risk_atom_count": len(event_atoms),
                "catalog_release_count": len(matching_catalog),
                "status": (
                    "CLOSED_OPERATOR_LIMITED_DIAGNOSTIC" if closed else "CHAIN_MISMATCH"
                ),
                "blocking_reasons": reasons,
                "qualified_provider_packet": False,
                "frequency_from_provider_packet": False,
                "physical_validation_claim": False,
            }
        )

    vertical_atoms = [atom for atom in atoms if str(atom.get("event_id", "")).startswith(event_prefix)]
    vertical_ir = _aggregate_ir(vertical_atoms)
    vertical_fn = [_fn_curve(vertical_atoms, index) for index in range(2)]
    base_closed = (
        isinstance(base_chain_audit, Mapping)
        and base_chain_audit.get("status") == "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED"
    )
    vertical_events_closed = closed_event_count == len(event_rows_by_id) and not mismatch_event_ids
    all_declared_events_closed = base_closed and vertical_events_closed
    return {
        "schema_version": VERTICAL_HANDOFF_CHAIN_AUDIT_SCHEMA,
        "status": (
            "VERTICAL_OPERATOR_LIMITED_CHAIN_CLOSED"
            if vertical_events_closed
            else "BLOCKED_VERTICAL_CHAIN_CLOSURE"
        ),
        "facility_id": campaign_result.get("facility_id"),
        "event_prefix": event_prefix,
        "vertical_event_count": len(event_rows_by_id),
        "vertical_chain_closed_event_count": closed_event_count,
        "vertical_chain_mismatch_event_ids": mismatch_event_ids,
        "vertical_case_count": sum(len(cases_by_event.get(event_id, ())) for event_id in event_rows_by_id),
        "vertical_risk_atom_count": len(vertical_atoms),
        "vertical_handoff_state_history_event_count": handoff_field_count,
        "event_rows": audit_rows,
        "vertical_conditional_ir_low_high": vertical_ir,
        "vertical_expected_death_fn_low_high": vertical_fn,
        "base_packet_chain_status": base_chain_audit.get("status") if isinstance(base_chain_audit, Mapping) else None,
        "all_declared_events_diagnostic_chain_closed": all_declared_events_closed,
        "qualified_provider_packet_count": 0,
        "provider_packet_qualification_claim": False,
        "frequency_from_provider_packet": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "The five vertical-handoff events are joined to their native release catalog by "
            "provider result digest and checked through termination/inventory and final-harm atoms. "
            "They remain synthetic/operator-limited diagnostics; the result does not create a "
            "provider packet, infer frequency, or promote facility IR/F-N."
        ),
    }


__all__ = [
    "VERTICAL_HANDOFF_CHAIN_AUDIT_SCHEMA",
    "VERTICAL_HANDOFF_PREFIX",
    "VerticalHandoffChainAuditError",
    "build_vertical_handoff_chain_audit",
]
