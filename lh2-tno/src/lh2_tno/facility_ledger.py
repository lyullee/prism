"""Merge separately executed equipment campaigns into one facility ledger.

Each input is an already evaluated PRISM campaign result.  This module does
not rerun a source or consequence model.  It only combines risk atoms after
checking that event IDs, asset ownership, receptor sets, and completeness
claims are compatible.  Missing equipment or accident families keep the
facility total risk unavailable; known contributions are still reported as a
separate, explicitly partial quantity.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from .contracts import canonical_digest


class FacilityLedgerError(ValueError):
    """Raised when independent campaign ledgers cannot be merged safely."""


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FacilityLedgerError(f"{label} must be a finite nonnegative number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise FacilityLedgerError(f"{label} must be a finite nonnegative number")
    return number


def _linear_percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _unwrap_campaign(row: Mapping[str, Any], index: int) -> tuple[str, Mapping[str, Any]]:
    """Accept a result directly or ``{"campaign_id", "result"}`` wrapper."""
    result = row.get("result")
    if isinstance(result, Mapping):
        campaign_id = row.get("campaign_id") or result.get("campaign_digest")
        return str(campaign_id or f"campaign-{index + 1}"), result
    campaign_id = row.get("campaign_id") or row.get("campaign_digest")
    return str(campaign_id or f"campaign-{index + 1}"), row


def _validate_atoms(
    atoms: Sequence[Any],
    *,
    event_ids: set[str],
    receptor_ids: set[str] | None,
    seen_atom_keys: set[tuple[str, str, str, str]],
) -> tuple[set[str], list[str]]:
    discovered_receptors: set[str] = set()
    errors: list[str] = []
    for index, atom in enumerate(atoms):
        if not isinstance(atom, Mapping):
            raise FacilityLedgerError(f"risk atom {index} must be an object")
        event_id = str(atom.get("event_id", ""))
        if not event_id or event_id not in event_ids:
            raise FacilityLedgerError(f"risk atom {index} references an unknown event")
        condition_id = str(atom.get("annual_condition_id", ""))
        branch_id = str(atom.get("release_branch_id", ""))
        ignition_id = str(atom.get("ignition_branch", ""))
        key = (event_id, condition_id, branch_id, ignition_id)
        if key in seen_atom_keys:
            raise FacilityLedgerError(
                "duplicate risk atom across campaign results: " + "/".join(key)
            )
        seen_atom_keys.add(key)
        frequency = _finite_nonnegative(
            atom.get("initiating_frequency_per_year"),
            f"risk atom {index} initiating_frequency_per_year",
        )
        conditional_weight = _finite_nonnegative(
            atom.get("conditional_weight"),
            f"risk atom {index} conditional_weight",
        )
        harm = atom.get("receptor_harm_low_high")
        deaths = atom.get("expected_deaths_low_high")
        if not isinstance(harm, Mapping) or not isinstance(deaths, Sequence) or isinstance(deaths, (str, bytes)):
            raise FacilityLedgerError(
                f"risk atom {index} must contain receptor harm and expected-death endpoints"
            )
        if len(deaths) != 2:
            raise FacilityLedgerError(f"risk atom {index} requires two expected-death endpoints")
        for endpoint, value in enumerate(deaths):
            _finite_nonnegative(value, f"risk atom {index} expected_deaths_low_high[{endpoint}]")
        atom_receptors = {str(key) for key in harm}
        if not atom_receptors:
            raise FacilityLedgerError(f"risk atom {index} must contain at least one receptor")
        discovered_receptors.update(atom_receptors)
        if receptor_ids is not None and atom_receptors != receptor_ids:
            raise FacilityLedgerError("campaign risk atoms do not share one receptor set")
        for receptor_id, endpoints in harm.items():
            if not isinstance(endpoints, Sequence) or isinstance(endpoints, (str, bytes)) or len(endpoints) != 2:
                raise FacilityLedgerError(
                    f"risk atom {index} receptor {receptor_id} requires two harm endpoints"
                )
            for endpoint, value in enumerate(endpoints):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise FacilityLedgerError(
                        f"risk atom {index} receptor {receptor_id} harm endpoint is invalid"
                    )
                if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                    raise FacilityLedgerError(
                        f"risk atom {index} receptor {receptor_id} harm endpoint is outside [0, 1]"
                    )
        if not math.isclose(
            float(atom.get("expected_deaths_low_high", [0.0, 0.0])[0]),
            sum(float(harm[receptor][0]) for receptor in harm),
            rel_tol=1e-8,
            abs_tol=1e-12,
        ):
            raise FacilityLedgerError(
                f"risk atom {index} low expected deaths do not close over receptors"
            )
        if not math.isclose(
            float(atom.get("expected_deaths_low_high", [0.0, 0.0])[1]),
            sum(float(harm[receptor][1]) for receptor in harm),
            rel_tol=1e-8,
            abs_tol=1e-12,
        ):
            raise FacilityLedgerError(
                f"risk atom {index} high expected deaths do not close over receptors"
            )
        # Keep this local variable explicit: it documents that frequency and
        # conditional weight are intentionally multiplied only during risk
        # aggregation, never during packet or event merging.
        _ = frequency * conditional_weight
    return discovered_receptors, errors


def _fn_curve(atoms: Sequence[Mapping[str, Any]], endpoint: int) -> dict[str, list[float]]:
    outcomes = []
    for atom in atoms:
        frequency = float(atom["initiating_frequency_per_year"]) * float(atom["conditional_weight"])
        deaths = float(atom["expected_deaths_low_high"][endpoint])
        outcomes.append((deaths, frequency))
    levels = sorted({deaths for deaths, _ in outcomes if deaths >= 1.0})
    return {
        "expected_deaths": levels,
        "cumulative_frequency_per_year": [
            sum(frequency for deaths, frequency in outcomes if deaths >= level)
            for level in levels
        ],
    }


def merge_facility_campaign_results(
    campaign_results: Sequence[Mapping[str, Any]],
    *,
    expected_component_ids: Sequence[str] = (),
    scope_matrices: Sequence[Mapping[str, Any]] = (),
    required_accident_families: Sequence[str] = (),
) -> dict[str, Any]:
    """Merge independent equipment results without hiding incomplete scope.

    ``campaign_results`` may contain direct campaign-result objects or wrappers
    with ``campaign_id`` and ``result``.  Each result must have a unique event
    and asset ownership boundary.  The returned known contribution is the
    linear sum of all validated atoms.  ``total_facility_*`` is populated only
    when every expected component and requested accident family is complete,
    no source result is synthetic or incomplete, and no exclusion remains.
    """
    if not campaign_results:
        raise FacilityLedgerError("at least one campaign result is required")

    campaign_rows: list[tuple[str, Mapping[str, Any]]] = [
        _unwrap_campaign(row, index) for index, row in enumerate(campaign_results)
    ]
    campaign_ids = [campaign_id for campaign_id, _ in campaign_rows]
    if len(set(campaign_ids)) != len(campaign_ids):
        raise FacilityLedgerError("campaign IDs must be unique")

    facility_ids = {str(result.get("facility_id", "")) for _, result in campaign_rows}
    if len(facility_ids) != 1 or "" in facility_ids:
        raise FacilityLedgerError("all campaign results must identify one common facility")
    facility_id = next(iter(facility_ids))

    merged_events: list[dict[str, Any]] = []
    merged_cases: list[dict[str, Any]] = []
    merged_missing: list[dict[str, Any]] = []
    merged_atoms: list[dict[str, Any]] = []
    merged_exclusions: dict[str, str] = {}
    seen_event_ids: set[str] = set()
    seen_assets: dict[str, str] = {}
    seen_components: set[str] = set()
    seen_atom_keys: set[tuple[str, str, str, str]] = set()
    receptor_ids: set[str] | None = None
    source_complete = True
    source_synthetic = False
    source_physical_validation = True
    blocking_reasons: list[str] = []
    timing_values: list[float] = []
    component_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_digests: list[str] = []
    event_accounting: dict[str, dict[str, int]] = {}

    for campaign_id, result in campaign_rows:
        events = result.get("events")
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            raise FacilityLedgerError(f"campaign {campaign_id} has no event list")
        local_event_ids: set[str] = set()
        for event in events:
            if not isinstance(event, Mapping) or not event.get("id"):
                raise FacilityLedgerError(f"campaign {campaign_id} contains an invalid event")
            event_id = str(event["id"])
            if event_id in seen_event_ids or event_id in local_event_ids:
                raise FacilityLedgerError(f"duplicate event ID across facility campaigns: {event_id}")
            local_event_ids.add(event_id)
            seen_event_ids.add(event_id)
            asset_id = str(event.get("asset_id", ""))
            if not asset_id:
                raise FacilityLedgerError(f"event {event_id} has no asset ID")
            component_id = str(event.get("model_component_id", ""))
            if not component_id:
                raise FacilityLedgerError(f"event {event_id} has no model component ID")
            seen_components.add(component_id)
            owner = seen_assets.get(asset_id)
            if owner is not None and owner != campaign_id:
                raise FacilityLedgerError(
                    f"asset {asset_id} appears in multiple campaign results; provide one disjoint physical scope"
                )
            seen_assets[asset_id] = campaign_id
            merged_events.append(dict(event))

        atoms = result.get("risk_atoms", [])
        if not isinstance(atoms, Sequence) or isinstance(atoms, (str, bytes)):
            raise FacilityLedgerError(f"campaign {campaign_id} has no risk atom list")
        discovered, _ = _validate_atoms(
            atoms,
            event_ids=local_event_ids,
            receptor_ids=receptor_ids,
            seen_atom_keys=seen_atom_keys,
        )
        if receptor_ids is None:
            receptor_ids = discovered
        merged_atoms.extend(dict(atom) for atom in atoms)

        for key in ("cases", "uncomputed_cases"):
            rows = result.get(key, [])
            if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
                raise FacilityLedgerError(f"campaign {campaign_id} has an invalid {key} list")
            target = merged_cases if key == "cases" else merged_missing
            for row_index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    raise FacilityLedgerError(
                        f"campaign {campaign_id} {key}[{row_index}] must be an object"
                    )
                row_event_id = row.get("event_id")
                if not row_event_id or str(row_event_id) not in local_event_ids:
                    raise FacilityLedgerError(
                        f"campaign {campaign_id} {key}[{row_index}] references an unknown event"
                    )
                target.append(dict(row))
        accounted_case_event_ids = {
            str(row.get("event_id"))
            for row in result.get("cases", [])
            if isinstance(row, Mapping) and row.get("event_id")
        }
        accounted_uncomputed_event_ids = {
            str(row.get("event_id"))
            for row in result.get("uncomputed_cases", [])
            if isinstance(row, Mapping) and row.get("event_id")
        }
        missing_event_ids = sorted(
            local_event_ids - accounted_case_event_ids - accounted_uncomputed_event_ids
        )
        event_accounting[campaign_id] = {
            "generated_event_count": len(local_event_ids),
            "case_event_count": len(accounted_case_event_ids & local_event_ids),
            "uncomputed_event_count": len(accounted_uncomputed_event_ids & local_event_ids),
            "unaccounted_event_count": len(missing_event_ids),
        }
        if missing_event_ids:
            source_complete = False
            blocking_reasons.append(
                f"campaign {campaign_id}: events lack case or uncomputed-case accounting: "
                + ", ".join(missing_event_ids)
            )
        for component_id, reason in dict(result.get("excluded_model_components", {})).items():
            previous = merged_exclusions.get(str(component_id))
            if previous is not None and previous != str(reason):
                raise FacilityLedgerError(
                    f"component {component_id} has conflicting exclusion reasons"
                )
            merged_exclusions[str(component_id)] = str(reason)

        coverage = result.get("coverage", {})
        if isinstance(coverage, Mapping):
            rows = coverage.get("by_component", [])
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                for row in rows:
                    if isinstance(row, Mapping) and row.get("component_id"):
                        component_rows[str(row["component_id"])].append(dict(row))
        complete = result.get("declared_scope_numerically_complete") is True
        if not complete:
            source_complete = False
            blocking_reasons.append(f"campaign {campaign_id}: declared scope is incomplete")
        if result.get("uncomputed_cases"):
            source_complete = False
            blocking_reasons.append(f"campaign {campaign_id}: uncomputed cases remain")
        if result.get("excluded_model_components"):
            source_complete = False
            blocking_reasons.append(f"campaign {campaign_id}: excluded components remain")
        if result.get("synthetic_release_horizon_present") is True:
            source_synthetic = True
            source_complete = False
            blocking_reasons.append(f"campaign {campaign_id}: synthetic release horizon")
        source_physical_validation &= result.get("physical_validation_claim") is True
        digest = result.get("campaign_digest")
        if digest:
            source_digests.append(str(digest))
        timing = result.get("timing", {})
        if isinstance(timing, Mapping):
            elapsed = timing.get("campaign_elapsed_ms")
            if isinstance(elapsed, (int, float)) and math.isfinite(float(elapsed)) and elapsed >= 0:
                timing_values.append(float(elapsed))

    if receptor_ids is None or not receptor_ids:
        raise FacilityLedgerError("facility campaigns contain no receptor risk atoms")
    expected_components = {str(component_id) for component_id in expected_component_ids}
    observed_components = set(seen_components)
    if not expected_components:
        source_complete = False
        blocking_reasons.append("full expected component list was not supplied")
    if expected_components - observed_components:
        source_complete = False
        blocking_reasons.append(
            "missing expected components: " + ", ".join(sorted(expected_components - observed_components))
        )
    if expected_components and observed_components - expected_components:
        source_complete = False
        blocking_reasons.append(
            "unexpected components: " + ", ".join(sorted(observed_components - expected_components))
        )

    component_statuses: dict[str, str] = {}
    for component_id, rows in sorted(component_rows.items()):
        statuses = {str(row.get("scope_status")) for row in rows}
        if len(rows) > 1:
            source_complete = False
            blocking_reasons.append(
                f"component {component_id} appears in multiple coverage ledgers"
            )
        component_statuses[component_id] = "EXECUTED" if statuses == {"EXECUTED"} else "PARTIAL"
        if component_statuses[component_id] != "EXECUTED":
            source_complete = False
            blocking_reasons.append(f"component {component_id}: {component_statuses[component_id]}")

    family_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for matrix in scope_matrices:
        if not isinstance(matrix, Mapping):
            raise FacilityLedgerError("scope matrix entries must be objects")
        for row in matrix.get("rows", ()):  # type: ignore[union-attr]
            if isinstance(row, Mapping) and row.get("family"):
                family_rows[str(row["family"])].append(row)
    family_statuses: dict[str, str] = {}
    for family in required_accident_families:
        rows = family_rows.get(str(family), [])
        if not rows:
            family_statuses[str(family)] = "MISSING_SCOPE_MATRIX"
            source_complete = False
            blocking_reasons.append(f"accident family {family}: missing scope matrix")
        elif all(row.get("status") == "EXECUTED" for row in rows):
            family_statuses[str(family)] = "EXECUTED"
        else:
            family_statuses[str(family)] = "PARTIAL"
            source_complete = False
            blocking_reasons.append(f"accident family {family}: PARTIAL")

    endpoint_ir = {receptor_id: [0.0, 0.0] for receptor_id in sorted(receptor_ids)}
    event_component = {
        str(event["id"]): str(event["model_component_id"])
        for event in merged_events
    }
    component_atoms: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for atom in merged_atoms:
        weight = float(atom["initiating_frequency_per_year"]) * float(atom["conditional_weight"])
        harm = atom["receptor_harm_low_high"]
        component_atoms[event_component[str(atom["event_id"])]].append(atom)
        for endpoint in range(2):
            for receptor_id in endpoint_ir:
                endpoint_ir[receptor_id][endpoint] += weight * float(harm[receptor_id][endpoint])
    fn = [_fn_curve(merged_atoms, endpoint) for endpoint in range(2)]
    component_contributions: dict[str, dict[str, Any]] = {}
    for component_id in sorted(observed_components):
        atoms = component_atoms.get(component_id, [])
        component_ir = {receptor_id: [0.0, 0.0] for receptor_id in sorted(receptor_ids)}
        for atom in atoms:
            weight = float(atom["initiating_frequency_per_year"]) * float(atom["conditional_weight"])
            harm = atom["receptor_harm_low_high"]
            for endpoint in range(2):
                for receptor_id in component_ir:
                    component_ir[receptor_id][endpoint] += weight * float(harm[receptor_id][endpoint])
        component_contributions[component_id] = {
            "event_count": sum(
                1 for event in merged_events
                if str(event["model_component_id"]) == component_id
            ),
            "risk_atom_count": len(atoms),
            "annual_ir_low_high": component_ir,
            "expected_death_fn_low_high": [
                _fn_curve(atoms, endpoint) for endpoint in range(2)
            ],
            "frequency_is_not_reallocated": True,
        }
    total_available = source_complete and not source_synthetic and not merged_exclusions
    unique_blocking = list(dict.fromkeys(blocking_reasons))
    timing = {
        "campaign_count": len(campaign_rows),
        "campaign_elapsed_ms_sum": sum(timing_values),
        "campaign_elapsed_ms_min": min(timing_values) if timing_values else None,
        "campaign_elapsed_ms_median": median(timing_values) if timing_values else None,
        "campaign_elapsed_ms_max": max(timing_values) if timing_values else None,
        "campaign_elapsed_ms_p95": _linear_percentile(timing_values, 0.95),
        "campaign_elapsed_ms_p99": _linear_percentile(timing_values, 0.99),
        "distribution": "across separately executed equipment campaigns; not repeated-run latency",
    }
    known_ir = {receptor_id: values[:] for receptor_id, values in endpoint_ir.items()}
    return {
        "schema_version": "prism.facility_risk_ledger.v1",
        "status": "FACILITY_SCOPE_EXECUTED" if total_available else "PARTIAL_FACILITY_SCOPE",
        "facility_id": facility_id,
        "campaign_ids": campaign_ids,
        "campaign_digests": source_digests,
        "campaign_digest": canonical_digest({"campaign_ids": campaign_ids, "campaign_digests": source_digests}),
        "event_accounting": event_accounting,
        "event_count": len(merged_events),
        "case_count": len(merged_cases),
        "uncomputed_case_count": len(merged_missing),
        "events": merged_events,
        "cases": merged_cases,
        "uncomputed_cases": merged_missing,
        "risk_atoms": merged_atoms,
        "risk_atoms_digest": canonical_digest(merged_atoms),
        "component_contributions": component_contributions,
        "observed_asset_ids": sorted(seen_assets),
        "observed_component_ids": sorted(observed_components),
        "expected_component_ids": sorted(expected_components),
        "component_statuses": component_statuses,
        "excluded_model_components": merged_exclusions,
        "required_accident_families": [str(family) for family in required_accident_families],
        "accident_family_statuses": family_statuses,
        "declared_scope_numerically_complete": total_available,
        "known_contribution_annual_ir_low_high": known_ir,
        "known_contribution_expected_death_fn_low_high": fn,
        "declared_scope_annual_ir_low_high": known_ir if total_available else None,
        "declared_scope_expected_death_fn_low_high": fn if total_available else None,
        "total_facility_annual_ir_low_high": known_ir if total_available else None,
        "total_facility_expected_death_fn_low_high": fn if total_available else None,
        "physical_validation_claim": source_physical_validation and total_available,
        "synthetic_release_horizon_present": source_synthetic,
        "facility_total_risk_available": total_available,
        "blocking_reasons": unique_blocking,
        "timing": timing,
        "semantics": {
            "risk_sum": "validated risk atoms are summed once across disjoint equipment campaigns",
            "missing_scope": "missing or incomplete equipment/families remain partial and never become zero risk",
            "frequency": "each atom retains its initiating event frequency; no frequency inference or reallocation is performed",
            "fn": "expected-death F-N curves use the same atom-level convention as the campaign backend",
        },
    }
