"""Merge separately executed equipment campaigns into one facility ledger.

Each input is an already evaluated PRISM campaign result.  This module does
not rerun a source or consequence model.  It only combines risk atoms after
checking that event IDs, asset ownership, receptor sets, and completeness
claims are compatible.  Missing equipment or accident families keep the
facility total risk unavailable; known contributions and a separate
conditional diagnostic facility IR/F-N view are still reported explicitly.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from .contracts import canonical_digest
from .release_ledger import (
    build_release_termination_inventory_ledger,
    evaluate_facility_release_boundary,
)


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


def _stage_timing(cases: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Summarize provider/consequence stage timing without claiming throughput.

    A campaign may expose ``stage_elapsed_ms`` for each executed case.  Keep
    each stage's observed samples separate from whole-case timing so a facility
    reviewer can see where fresh physics time was spent.  Missing stage rows
    remain missing; no interpolation or 1 Hz extrapolation is performed.
    """
    values: dict[str, list[float]] = defaultdict(list)
    for case in cases:
        stage_rows = case.get("stage_elapsed_ms")
        if not isinstance(stage_rows, Mapping):
            continue
        for stage, elapsed in stage_rows.items():
            if (
                isinstance(stage, str)
                and stage.strip()
                and isinstance(elapsed, (int, float))
                and not isinstance(elapsed, bool)
                and math.isfinite(float(elapsed))
                and elapsed >= 0
            ):
                values[stage].append(float(elapsed))
    return {
        stage: {
            "sample_count": len(samples),
            "sum_ms": sum(samples),
            "median_ms": median(samples),
            "max_ms": max(samples),
            "p95_ms": _linear_percentile(samples, 0.95),
            "p99_ms": _linear_percentile(samples, 0.99),
        }
        for stage, samples in sorted(values.items())
    }


def _unwrap_campaign(row: Mapping[str, Any], index: int) -> tuple[str, Mapping[str, Any]]:
    """Accept a result directly or ``{"campaign_id", "result"}`` wrapper."""
    result = row.get("result")
    if isinstance(result, Mapping):
        campaign_id = row.get("campaign_id") or result.get("campaign_digest")
        return str(campaign_id or f"campaign-{index + 1}"), result
    campaign_id = row.get("campaign_id") or row.get("campaign_digest")
    return str(campaign_id or f"campaign-{index + 1}"), row


def _case_identity(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the stable identity used for facility case accounting.

    One event can intentionally be evaluated for more than one weather,
    release-branch, or ignition branch.  Event ID alone therefore collapses
    distinct numerical cases.  Keep the same dimensions used by risk atoms;
    fall back to the event ID only for legacy rows that do not carry the
    dimensions yet.
    """
    event_id = str(row.get("event_id", ""))
    condition_id = row.get("annual_condition_id")
    branch_id = row.get("release_branch_id")
    ignition_id = row.get("ignition_branch")
    if any(value is not None and str(value) for value in (condition_id, branch_id, ignition_id)):
        return (
            event_id,
            str(condition_id or ""),
            str(branch_id or ""),
            str(ignition_id or ""),
        )
    return (event_id,)


def _strict_port_ids(value: Any, label: str) -> tuple[str, ...] | None:
    """Normalize an optional reviewed accident-port list without inference."""
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise FacilityLedgerError(f"{label} must be a non-empty string array or null")
    ports = tuple(value)
    if not ports or any(not isinstance(port, str) or not port.strip() for port in ports):
        raise FacilityLedgerError(f"{label} must be a non-empty string array or null")
    if len(set(ports)) != len(ports):
        raise FacilityLedgerError(f"{label} must not contain duplicate ports")
    return ports


def _case_component_id(
    row: Mapping[str, Any], event_component: Mapping[str, str]
) -> str:
    """Resolve the equipment model that owns a case row.

    Native provider packets carry their component in ``provider_packet_identity``;
    older campaign rows may expose it directly or only through the event.  The
    event fallback keeps the ledger compatible with those legacy rows while an
    explicit ``UNMAPPED_COMPONENT`` value makes a broken handoff visible.
    """
    provider_identity = row.get("provider_packet_identity")
    if isinstance(provider_identity, Mapping):
        component_id = provider_identity.get("component_id")
        if component_id:
            return str(component_id)
    for key in ("component_id", "model_component_id"):
        component_id = row.get(key)
        if component_id:
            return str(component_id)
    event_id = str(row.get("event_id", ""))
    return str(event_component.get(event_id, "UNMAPPED_COMPONENT"))


def _component_gate_categories(
    *,
    status: str,
    strict_uncomputed_case_count: int,
    operator_limited_case_count: int,
    domain_incomplete_case_count: int,
    failed_case_count: int,
) -> list[str]:
    """Classify component blockers using the facility evidence taxonomy."""
    categories: list[str] = []
    if strict_uncomputed_case_count:
        categories.append("MISSING_PROVIDER_CASES")
    if operator_limited_case_count:
        categories.append("OPERATOR_LIMITED_INPUT")
    if domain_incomplete_case_count:
        categories.append("DOMAIN_INCOMPLETE")
    if failed_case_count:
        categories.append("FAILED_PROVIDER_CASE")
    if status not in {"EXECUTED", "NOT_APPLICABLE"} and not categories:
        categories.append("FAMILY_SCOPE_PARTIAL")
    return categories


def _validate_atoms(
    atoms: Sequence[Any],
    *,
    event_ids: set[str],
    receptor_ids: set[str] | None,
    seen_atom_keys: set[tuple[str, str, str, str]],
    annual_conditions: Mapping[str, Mapping[str, Any]] | None = None,
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
        if not condition_id or not branch_id or not ignition_id:
            raise FacilityLedgerError(
                f"risk atom {index} requires annual condition, release branch, and ignition branch IDs"
            )
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
        expected_deaths = atom.get("expected_deaths_low_high", [0.0, 0.0])
        expected_reference = {
            endpoint: sum(float(harm[receptor][endpoint]) for receptor in harm)
            for endpoint in range(2)
        }
        # Realtime campaign bindings may carry an explicit population-weighted
        # F/N value.  Legacy atoms retain the historical receptor-harm sum
        # contract unless they opt into this basis, so existing saved ledgers
        # remain readable while the facility bridge can preserve population.
        if atom.get("expected_deaths_basis") == "population_weighted":
            condition_id = str(atom.get("annual_condition_id", ""))
            condition = (annual_conditions or {}).get(condition_id)
            population = condition.get("population") if isinstance(condition, Mapping) else None
            if not isinstance(population, Sequence) or isinstance(population, (str, bytes)):
                raise FacilityLedgerError(
                    f"risk atom {index} population-weighted expected deaths require condition population"
                )
            population_by_receptor: dict[str, float] = {}
            for population_row in population:
                if not isinstance(population_row, Mapping) or not population_row.get("receptor_id"):
                    raise FacilityLedgerError(
                        f"risk atom {index} condition population row is invalid"
                    )
                receptor_id = str(population_row["receptor_id"])
                persons = population_row.get("persons")
                presence = population_row.get("presence_probability", 1.0)
                if (
                    isinstance(persons, bool)
                    or not isinstance(persons, (int, float))
                    or not math.isfinite(float(persons))
                    or float(persons) < 0.0
                    or isinstance(presence, bool)
                    or not isinstance(presence, (int, float))
                    or not math.isfinite(float(presence))
                    or not 0.0 <= float(presence) <= 1.0
                ):
                    raise FacilityLedgerError(
                        f"risk atom {index} condition population values are invalid"
                    )
                population_by_receptor[receptor_id] = float(persons) * float(presence)
            if set(population_by_receptor) != atom_receptors:
                raise FacilityLedgerError(
                    f"risk atom {index} population receptor set does not match harm receptors"
                )
            expected_reference = {
                endpoint: sum(
                    population_by_receptor[receptor]
                    * float(harm[receptor][endpoint])
                    for receptor in harm
                )
                for endpoint in range(2)
            }
        if not math.isclose(
            float(expected_deaths[0]),
            expected_reference[0],
            rel_tol=1e-8,
            abs_tol=1e-12,
        ):
            raise FacilityLedgerError(
                f"risk atom {index} low expected deaths do not close over receptors"
            )
        if not math.isclose(
            float(expected_deaths[1]),
            expected_reference[1],
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


def _population_accounting(
    conditions: Mapping[str, Mapping[str, Any]],
    *,
    referenced_condition_ids: Sequence[str],
    receptor_ids: set[str],
) -> dict[str, Any]:
    """Describe whether annual-condition population reached the facility ledger.

    Expected deaths are retained on each risk atom for backward compatibility,
    but a facility result is easier to audit when the annual-condition weather
    and population rows are carried alongside those atoms.  This helper is
    deliberately diagnostic: it never invents population for a missing or
    mismatched condition.
    """
    referenced = sorted({str(condition_id) for condition_id in referenced_condition_ids})
    missing_condition_ids: list[str] = []
    missing_population_ids: list[str] = []
    mismatched_receptor_ids: dict[str, dict[str, list[str]]] = {}
    invalid_population_rows: dict[str, list[int]] = {}
    rebound_diagnostic_ids: list[str] = []
    population_row_count = 0
    population_receptor_ids: set[str] = set()
    provenance: dict[str, str] = {}

    for condition_id in referenced:
        condition = conditions.get(condition_id)
        if condition is None:
            missing_condition_ids.append(condition_id)
            continue
        if condition.get("provenance"):
            provenance[condition_id] = str(condition["provenance"])
        population_rebind = condition.get("population_rebind")
        if isinstance(population_rebind, Mapping) and population_rebind.get("status") == (
            "MANY_TO_ONE_DIAGNOSTIC"
        ):
            rebound_diagnostic_ids.append(condition_id)
        population = condition.get("population")
        if not isinstance(population, Sequence) or isinstance(population, (str, bytes)):
            missing_population_ids.append(condition_id)
            continue
        row_ids: set[str] = set()
        for row_index, row in enumerate(population):
            if not isinstance(row, Mapping) or not row.get("receptor_id"):
                invalid_population_rows.setdefault(condition_id, []).append(row_index)
                continue
            receptor_id = str(row["receptor_id"])
            row_ids.add(receptor_id)
            population_receptor_ids.add(receptor_id)
            population_row_count += 1
            persons = row.get("persons")
            presence = row.get("presence_probability", 1.0)
            if (
                isinstance(persons, bool)
                or not isinstance(persons, (int, float))
                or not math.isfinite(float(persons))
                or float(persons) < 0.0
                or isinstance(presence, bool)
                or not isinstance(presence, (int, float))
                or not math.isfinite(float(presence))
                or not 0.0 <= float(presence) <= 1.0
            ):
                invalid_population_rows.setdefault(condition_id, []).append(row_index)
        if row_ids != receptor_ids:
            mismatched_receptor_ids[condition_id] = {
                "expected": sorted(receptor_ids),
                "observed": sorted(row_ids),
            }

    if not referenced:
        status = "NO_RISK_ATOMS"
    elif not conditions:
        status = "NOT_RECORDED_IN_INPUT"
    elif missing_condition_ids or missing_population_ids or invalid_population_rows:
        status = "MISSING_CONDITION_POPULATION"
    elif mismatched_receptor_ids:
        status = "RECEPTOR_POPULATION_MISMATCH"
    elif rebound_diagnostic_ids:
        status = "RECEPTOR_POPULATION_REBOUND_DIAGNOSTIC"
    else:
        status = "EXPLICIT_CONDITION_POPULATION"
    return {
        "status": status,
        "annual_condition_count": len(conditions),
        "referenced_condition_count": len(referenced),
        "referenced_condition_ids": referenced,
        "missing_condition_ids": missing_condition_ids,
        "missing_population_condition_ids": missing_population_ids,
        "mismatched_receptor_ids": mismatched_receptor_ids,
        "invalid_population_rows": invalid_population_rows,
        "rebound_diagnostic_condition_ids": rebound_diagnostic_ids,
        "population_row_count": population_row_count,
        "population_receptor_ids": sorted(population_receptor_ids),
        "population_provenance": provenance,
        "receptor_ids": sorted(receptor_ids),
    }


def _scenario_branch_accounting(
    atoms: Sequence[Mapping[str, Any]],
    conditions: Mapping[str, Mapping[str, Any]],
    *,
    event_frequencies: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Preserve the condition, release, and ignition dimensions of each atom.

    The facility IR/F-N sum is intentionally performed over risk atoms.  This
    companion ledger makes the dimensions behind that sum inspectable without
    inventing a frequency.  An optional scenario frequency map is used only by
    literature sensitivity outputs to show the same branch topology under a
    published reweighting.  A release branch is the explicit
    isolation/termination branch carried by the provider packet identity; an
    ignition branch is the conditional outcome label on the atom.  Family
    views remain attached to atoms and are never summed as independent risk.
    """
    if not atoms:
        return {
            "status": "NO_RISK_ATOMS",
            "annual_conditions": {},
            "release_branches": {},
            "ignition_branches": {},
            "cross_product_count": 0,
            "missing_dimension_atom_count": 0,
        }

    condition_groups: dict[str, dict[str, Any]] = {}
    release_groups: dict[str, dict[str, Any]] = {}
    ignition_groups: dict[str, dict[str, Any]] = {}
    cross_product: set[tuple[str, str, str]] = set()
    missing_dimension_atom_count = 0

    def _group(group: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
        return group.setdefault(
            key,
            {
                "event_ids": set(),
                "risk_atom_count": 0,
                "conditional_weight_sum": 0.0,
                "weighted_frequency_per_year": 0.0,
                "annual_condition_ids": set(),
                "release_branch_ids": set(),
                "ignition_branches": set(),
                "scenario_families": set(),
            },
        )

    def _families(atom: Mapping[str, Any]) -> set[str]:
        values = atom.get("scenario_families", ())
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            return set()
        return {str(value) for value in values if isinstance(value, str) and value.strip()}

    for atom in atoms:
        event_id = str(atom.get("event_id", ""))
        condition_id = str(atom.get("annual_condition_id", ""))
        release_id = str(atom.get("release_branch_id", ""))
        ignition_id = str(atom.get("ignition_branch", ""))
        if not condition_id or not release_id or not ignition_id:
            missing_dimension_atom_count += 1
        families = _families(atom)
        cross_product.add((condition_id, release_id, ignition_id))
        conditional_weight = float(atom.get("conditional_weight", 0.0))
        initiating_frequency = (
            float(event_frequencies[event_id])
            if event_frequencies is not None and event_id in event_frequencies
            else float(atom.get("initiating_frequency_per_year", 0.0))
        )

        condition_row = _group(condition_groups, condition_id)
        condition_row["event_ids"].add(event_id)
        condition_row["risk_atom_count"] += 1
        condition_row["conditional_weight_sum"] += conditional_weight
        condition_row["weighted_frequency_per_year"] += initiating_frequency * conditional_weight
        condition_row["release_branch_ids"].add(release_id)
        condition_row["ignition_branches"].add(ignition_id)
        condition_row["scenario_families"].update(families)

        release_row = _group(release_groups, release_id)
        release_row["event_ids"].add(event_id)
        release_row["risk_atom_count"] += 1
        release_row["conditional_weight_sum"] += conditional_weight
        release_row["weighted_frequency_per_year"] += initiating_frequency * conditional_weight
        release_row["annual_condition_ids"].add(condition_id)
        release_row["ignition_branches"].add(ignition_id)
        release_row["scenario_families"].update(families)
        identity = atom.get("provider_packet_identity")
        termination_bases = identity.get("termination_bases", ()) if isinstance(identity, Mapping) else ()
        if isinstance(termination_bases, Sequence) and not isinstance(termination_bases, (str, bytes)):
            counts = release_row.setdefault("termination_basis_counts", defaultdict(int))
            for basis in termination_bases:
                if isinstance(basis, str) and basis.strip():
                    counts[str(basis)] += 1

        ignition_row = _group(ignition_groups, ignition_id)
        ignition_row["event_ids"].add(event_id)
        ignition_row["risk_atom_count"] += 1
        ignition_row["conditional_weight_sum"] += conditional_weight
        ignition_row["weighted_frequency_per_year"] += initiating_frequency * conditional_weight
        ignition_row["annual_condition_ids"].add(condition_id)
        ignition_row["release_branch_ids"].add(release_id)
        ignition_row["scenario_families"].update(families)
        deaths = atom.get("expected_deaths_low_high", ())
        if isinstance(deaths, Sequence) and not isinstance(deaths, (str, bytes)) and any(
            isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0.0
            for value in deaths
        ):
            ignition_row["positive_harm_atom_count"] = ignition_row.get("positive_harm_atom_count", 0) + 1

    def _finalize(group: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for key in sorted(group):
            row = group[key]
            value = {
                "event_count": len(row["event_ids"]),
                "risk_atom_count": int(row["risk_atom_count"]),
                "conditional_weight_sum": float(row["conditional_weight_sum"]),
                "weighted_frequency_per_year": float(row["weighted_frequency_per_year"]),
                "annual_condition_ids": sorted(row.get("annual_condition_ids", ())),
                "release_branch_ids": sorted(row.get("release_branch_ids", ())),
                "ignition_branches": sorted(row.get("ignition_branches", ())),
                "scenario_families": sorted(row.get("scenario_families", ())),
            }
            if "termination_basis_counts" in row:
                value["termination_basis_counts"] = dict(sorted(row["termination_basis_counts"].items()))
            if "positive_harm_atom_count" in row:
                value["positive_harm_atom_count"] = int(row["positive_harm_atom_count"])
            output[key] = value
        return output

    condition_output: dict[str, dict[str, Any]] = {}
    for condition_id, row in _finalize(condition_groups).items():
        source = conditions.get(condition_id, {})
        condition_output[condition_id] = {
            "annual_probability": source.get("annual_probability"),
            "weather": source.get("weather", source.get("weather_state")),
            "provenance": source.get("provenance"),
            **row,
        }
    return {
        "status": (
            "BRANCH_DIMENSIONS_MISSING"
            if missing_dimension_atom_count
            else "EXPLICIT_BRANCH_ACCOUNTING"
        ),
        "annual_conditions": condition_output,
        "release_branches": _finalize(release_groups),
        "ignition_branches": _finalize(ignition_groups),
        "cross_product_count": len(cross_product),
        "missing_dimension_atom_count": missing_dimension_atom_count,
        "frequency_reallocation_performed": False,
    }


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


def _fn_diagnostics(
    atoms: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Explain an empty F/N curve instead of treating it as missing work.

    PRISM keeps F/N levels at ``N >= 1``.  A valid consequence calculation can
    therefore produce an empty curve when every declared receptor has zero
    harm, or when all expected-death values are positive but below one.  The
    status and maxima make that distinction machine-readable while preserving
    the conventional curve representation.
    """
    curves = [_fn_curve(atoms, endpoint) for endpoint in range(2)]
    maxima = [
        max(
            (float(atom["expected_deaths_low_high"][endpoint]) for atom in atoms),
            default=0.0,
        )
        for endpoint in range(2)
    ]
    level_counts = [len(curve["expected_deaths"]) for curve in curves]
    if not atoms:
        status = "NO_RISK_ATOMS"
    elif any(level_counts):
        status = "CURVE_AVAILABLE"
    elif any(value > 0.0 for value in maxima):
        status = "SUB_ONE_EXPECTED_DEATH_LEVEL_ONLY"
    else:
        status = "ZERO_EXPECTED_DEATH_AT_DECLARED_RECEPTORS"
    return {
        "status": status,
        "endpoint_level_count_low_high": level_counts,
        "max_expected_deaths_low_high": maxima,
        "curve_uses_threshold": "N >= 1 expected deaths",
    }


def _component_risk_ranking(
    component_contributions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Rank equipment by its peak conditional diagnostic IR contribution.

    The ranking is a triage view over already evaluated risk atoms.  It uses
    the largest receptor IR for each uncertainty endpoint, so receptor risks
    are not summed across people or locations.  It does not reallocate
    frequency, fill missing components, or open the facility QRA gate.
    """
    rows: list[dict[str, Any]] = []
    for component_id, contribution in sorted(component_contributions.items()):
        annual_ir = contribution.get("annual_ir_low_high", {})
        receptor_rows = (
            annual_ir.items() if isinstance(annual_ir, Mapping) else ()
        )
        peaks: list[float] = []
        peak_receptors: list[str | None] = []
        for endpoint in range(2):
            candidates: list[tuple[float, str]] = []
            for receptor_id, values in receptor_rows:
                if (
                    isinstance(values, Sequence)
                    and not isinstance(values, (str, bytes))
                    and len(values) == 2
                    and isinstance(values[endpoint], (int, float))
                    and not isinstance(values[endpoint], bool)
                ):
                    candidates.append((float(values[endpoint]), str(receptor_id)))
            if candidates:
                peak_value, receptor_id = max(candidates, key=lambda row: (row[0], row[1]))
                peaks.append(peak_value)
                peak_receptors.append(receptor_id)
            else:
                peaks.append(0.0)
                peak_receptors.append(None)
        coverage = contribution.get("coverage", {})
        rows.append(
            {
                "component_id": str(component_id),
                "event_count": int(contribution.get("event_count", 0)),
                "risk_atom_count": int(contribution.get("risk_atom_count", 0)),
                "status": coverage.get("status"),
                "peak_annual_ir_low_high": peaks,
                "peak_receptor_id_low_high": peak_receptors,
                "conditional_case_count": coverage.get("conditional_case_count", 0),
                "strict_uncomputed_case_count": coverage.get("strict_uncomputed_case_count", 0),
                "frequency_is_not_reallocated": True,
            }
        )
    rows.sort(
        key=lambda row: (
            -float(row["peak_annual_ir_low_high"][1]),
            -float(row["peak_annual_ir_low_high"][0]),
            row["component_id"],
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {
        "status": "AVAILABLE" if rows else "NO_RISK_ATOMS",
        "component_count": len(rows),
        "ranking_basis": (
            "descending peak receptor annual IR at the high uncertainty endpoint; "
            "diagnostic triage only"
        ),
        "frequency_reallocation_performed": False,
        "facility_ir_fn_promotion": False,
        "rows": rows,
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
    source_provider_packet_promoted = True
    provider_packet_case_count = 0
    qualified_provider_packet_case_count = 0
    provider_qualification_blocking_reasons: list[str] = []
    blocking_reasons: list[str] = []
    timing_values: list[float] = []
    fresh_physics_case_counts: list[int] = []
    case_elapsed_values: list[float] = []
    component_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_digests: list[str] = []
    event_accounting: dict[str, dict[str, int]] = {}
    merged_annual_conditions: dict[str, dict[str, Any]] = {}
    event_port_ids: dict[str, tuple[str, ...] | None] = {}

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
            event_port_ids[event_id] = _strict_port_ids(
                event.get("port_ids"), f"event {event_id} port_ids"
            )
            seen_components.add(component_id)
            owner = seen_assets.get(asset_id)
            if owner is not None and owner != campaign_id:
                raise FacilityLedgerError(
                    f"asset {asset_id} appears in multiple campaign results; provide one disjoint physical scope"
                )
            seen_assets[asset_id] = campaign_id
            merged_events.append(dict(event))

        annual_conditions = result.get("annual_conditions", [])
        if not isinstance(annual_conditions, Sequence) or isinstance(
            annual_conditions, (str, bytes)
        ):
            raise FacilityLedgerError(
                f"campaign {campaign_id} has an invalid annual_conditions list"
            )
        for condition_index, condition in enumerate(annual_conditions):
            if not isinstance(condition, Mapping) or not condition.get("id"):
                raise FacilityLedgerError(
                    f"campaign {campaign_id} annual_conditions[{condition_index}] must contain an id"
                )
            condition_id = str(condition["id"])
            normalized_condition = dict(condition)
            previous_condition = merged_annual_conditions.get(condition_id)
            if previous_condition is not None and canonical_digest(previous_condition) != canonical_digest(
                normalized_condition
            ):
                raise FacilityLedgerError(
                    f"annual condition {condition_id} has conflicting metadata across campaigns"
                )
            merged_annual_conditions[condition_id] = normalized_condition

        atoms = result.get("risk_atoms", [])
        if not isinstance(atoms, Sequence) or isinstance(atoms, (str, bytes)):
            raise FacilityLedgerError(f"campaign {campaign_id} has no risk atom list")
        discovered, _ = _validate_atoms(
            atoms,
            event_ids=local_event_ids,
            receptor_ids=receptor_ids,
            seen_atom_keys=seen_atom_keys,
            annual_conditions=merged_annual_conditions,
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
        packet_case_count = result.get("provider_packet_case_count", 0)
        qualified_packet_case_count = result.get("qualified_provider_packet_case_count", 0)
        if (
            isinstance(packet_case_count, bool)
            or not isinstance(packet_case_count, int)
            or packet_case_count < 0
            or isinstance(qualified_packet_case_count, bool)
            or not isinstance(qualified_packet_case_count, int)
            or qualified_packet_case_count < 0
            or qualified_packet_case_count > packet_case_count
        ):
            raise FacilityLedgerError(
                f"campaign {campaign_id} has invalid provider packet qualification counts"
            )
        provider_packet_case_count += packet_case_count
        qualified_provider_packet_case_count += qualified_packet_case_count
        if result.get("provider_packet_promoted") is not True:
            source_provider_packet_promoted = False
            provider_qualification_blocking_reasons.append(
                f"campaign {campaign_id}: qualified provider packet promotion is unavailable"
            )
        if result.get("provider_packet_missing_evidence_cases"):
            source_provider_packet_promoted = False
            provider_qualification_blocking_reasons.append(
                f"campaign {campaign_id}: provider packet evidence does not match all consumed packets"
            )
        digest = result.get("campaign_digest")
        if digest:
            source_digests.append(str(digest))
        timing = result.get("timing", {})
        if isinstance(timing, Mapping):
            elapsed = timing.get("campaign_elapsed_ms")
            if isinstance(elapsed, (int, float)) and math.isfinite(float(elapsed)) and elapsed >= 0:
                timing_values.append(float(elapsed))
            fresh_cases = timing.get("fresh_physics_cases")
            if (
                isinstance(fresh_cases, int)
                and not isinstance(fresh_cases, bool)
                and fresh_cases >= 0
            ):
                fresh_physics_case_counts.append(fresh_cases)
            for case_row in result.get("cases", []):
                if not isinstance(case_row, Mapping):
                    continue
                case_elapsed = case_row.get("elapsed_ms")
                if (
                    isinstance(case_elapsed, (int, float))
                    and math.isfinite(float(case_elapsed))
                    and case_elapsed >= 0
                ):
                    case_elapsed_values.append(float(case_elapsed))

    # Preserve the reviewed accident exit all the way through the merged
    # facility ledger.  A port-scoped event without the same port list on its
    # cases or risk atoms is withheld rather than repaired or rebound.
    port_binding_mismatches: list[dict[str, Any]] = []
    for row_kind, rows in (
        ("case", [*merged_cases, *merged_missing]),
        ("risk_atom", merged_atoms),
    ):
        for row in rows:
            event_id = str(row.get("event_id", ""))
            expected = event_port_ids.get(event_id)
            actual = _strict_port_ids(
                row.get("frequency_port_ids"),
                f"{row_kind} {event_id} frequency_port_ids",
            )
            if actual != expected:
                port_binding_mismatches.append(
                    {
                        "row_kind": row_kind,
                        "event_id": event_id,
                        "expected_port_ids": None if expected is None else list(expected),
                        "actual_port_ids": None if actual is None else list(actual),
                    }
                )
    frequency_port_binding = {
        "schema_version": "prism.frequency_port_binding.v1",
        "port_scoped_event_count": sum(value is not None for value in event_port_ids.values()),
        "port_unbound_event_count": sum(value is None for value in event_port_ids.values()),
        "all_events_port_scoped": all(value is not None for value in event_port_ids.values()),
        "case_port_binding_mismatch_count": sum(
            row["row_kind"] == "case" for row in port_binding_mismatches
        ),
        "risk_atom_port_binding_mismatch_count": sum(
            row["row_kind"] == "risk_atom" for row in port_binding_mismatches
        ),
        "mismatch_count": len(port_binding_mismatches),
        "mismatch_examples": port_binding_mismatches[:10],
        "status": "ALIGNED" if not port_binding_mismatches else "PORT_BINDING_MISMATCH",
        "policy": (
            "Facility merge preserves reviewed event port_ids in cases and risk_atoms; "
            "missing or mismatched rows are withheld and no accident port is inferred."
        ),
    }
    if port_binding_mismatches:
        source_complete = False
        blocking_reasons.append(
            "facility frequency port binding mismatch between events and cases/risk atoms"
        )

    if receptor_ids is None or not receptor_ids:
        raise FacilityLedgerError("facility campaigns contain no receptor risk atoms")
    referenced_condition_ids = [
        str(atom.get("annual_condition_id", "")) for atom in merged_atoms
    ]
    population_accounting = _population_accounting(
        merged_annual_conditions,
        referenced_condition_ids=referenced_condition_ids,
        receptor_ids=receptor_ids,
    )
    scenario_branch_accounting = _scenario_branch_accounting(
        merged_atoms,
        merged_annual_conditions,
    )
    release_termination_inventory_ledger = build_release_termination_inventory_ledger(
        merged_cases,
        withheld_cases=merged_missing,
    )
    strict_release_boundary = evaluate_facility_release_boundary(
        release_termination_inventory_ledger
    )
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
        if statuses == {"EXECUTED"}:
            component_statuses[component_id] = "EXECUTED"
        elif statuses == {"EXCLUDED"}:
            # Preserve an explicit non-release/interface exclusion as its own
            # status.  It still blocks qualified facility promotion under the
            # fail-closed policy, but must not be misreported as a partial
            # physics execution.
            component_statuses[component_id] = "EXCLUDED"
        else:
            component_statuses[component_id] = "PARTIAL"
        if component_statuses[component_id] != "EXECUTED":
            source_complete = False
            blocking_reasons.append(f"component {component_id}: {component_statuses[component_id]}")
    for component_id in sorted(expected_components):
        if component_id not in component_rows:
            component_statuses[component_id] = "MISSING_COVERAGE_LEDGER"
            source_complete = False
            blocking_reasons.append(
                f"component {component_id}: missing coverage ledger row"
            )

    family_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    scope_matrix_digests: list[str] = []
    for matrix in scope_matrices:
        if not isinstance(matrix, Mapping):
            raise FacilityLedgerError("scope matrix entries must be objects")
        scope_matrix_digests.append(canonical_digest(matrix))
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
        elif all(row.get("status") in {"EXECUTED", "NOT_APPLICABLE"} for row in rows):
            # A family absent from every contributing manifest is a declared
            # scope exclusion, not an uncomputed accident. When at least one
            # campaign contains the family, retain EXECUTED as the aggregate
            # status even if another disjoint campaign reports it as absent.
            family_statuses[str(family)] = (
                "EXECUTED"
                if any(row.get("status") == "EXECUTED" for row in rows)
                else "NOT_APPLICABLE"
            )
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
    family_atoms: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for atom in merged_atoms:
        weight = float(atom["initiating_frequency_per_year"]) * float(atom["conditional_weight"])
        harm = atom["receptor_harm_low_high"]
        component_atoms[event_component[str(atom["event_id"])]].append(atom)
        families = atom.get("scenario_families", ())
        if isinstance(families, Sequence) and not isinstance(families, (str, bytes)):
            for family in families:
                if isinstance(family, str) and family.strip():
                    family_atoms[family].append(atom)
        for endpoint in range(2):
            for receptor_id in endpoint_ir:
                endpoint_ir[receptor_id][endpoint] += weight * float(harm[receptor_id][endpoint])
    fn_diagnostics = _fn_diagnostics(merged_atoms)
    fn = [_fn_curve(merged_atoms, endpoint) for endpoint in range(2)]
    # Keep a separate facility-level diagnostic view of the atoms that were
    # actually evaluated.  This is deliberately not promoted to
    # ``total_facility_*`` when the declared scope has blockers (for example
    # an operator-limited release or a synthetic diagnostic horizon).  The
    # diagnostic view is useful for wiring the facility aggregation and for
    # sensitivity studies while making the qualification boundary explicit.
    # A campaign may retain the same case in both ``cases`` and
    # ``uncomputed_cases`` to preserve an operator-limited/diagnostic reason.
    # Count one status per *case identity* for coverage summaries, preferring
    # the evaluated case row when both rows exist.  Event ID alone is not a
    # case identity because one event can have multiple weather or release
    # branches; the raw row counts remain available separately above.
    case_status_by_identity: dict[tuple[str, ...], str] = {}
    for case in merged_cases:
        case_status_by_identity[_case_identity(case)] = str(case.get("status", "UNKNOWN"))
    overlapping_case_uncomputed_count = 0
    uncomputed_status_counts: dict[str, int] = defaultdict(int)
    for case in merged_missing:
        identity = _case_identity(case)
        uncomputed_status_counts[str(case.get("status", "UNKNOWN"))] += 1
        if identity in case_status_by_identity:
            overlapping_case_uncomputed_count += 1
            continue
        case_status_by_identity[identity] = str(case.get("status", "UNKNOWN"))
    case_status_counts: dict[str, int] = defaultdict(int)
    for status in case_status_by_identity.values():
        case_status_counts[status] += 1
    conditional_case_count = len(case_status_by_identity)
    conditional_executed_case_count = sum(
        status.startswith("EXECUTED") for status in case_status_by_identity.values()
    )
    conditional_uncomputed_case_count = conditional_case_count - conditional_executed_case_count
    operator_limited_case_count = sum(
        count for status, count in case_status_counts.items()
        if "OPERATOR_LIMITED" in status
    )
    explicit_uncomputed_status_count = sum(
        count for status, count in case_status_counts.items()
        if "UNCOMPUTED" in status
    )
    failed_case_count = sum(
        count for status, count in case_status_counts.items()
        if "FAILED" in status
    )
    domain_incomplete_case_count = sum(
        count for status, count in case_status_counts.items()
        if "DOMAIN_INCOMPLETE" in status
    )
    # Keep numerical execution separate from qualification evidence.  An
    # operator-limited or domain-incomplete row has a computed diagnostic
    # result, but its evidence is withheld from qualified-facility promotion.
    not_numerically_executed_case_count = explicit_uncomputed_status_count + failed_case_count
    qualified_evidence_withheld_case_count = (
        operator_limited_case_count + domain_incomplete_case_count
    )
    numerically_executed_case_count = conditional_executed_case_count
    # Keep the same case identity and fail-closed semantics at equipment
    # level.  This is the machine-readable answer to "which equipment was
    # actually joined to the facility chain?" and prevents a facility total
    # from hiding a missing or operator-limited component handoff.
    component_case_status_by_identity: dict[str, dict[tuple[str, ...], str]] = defaultdict(dict)
    component_strict_uncomputed_counts: dict[str, int] = defaultdict(int)
    component_strict_uncomputed_status_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for case in merged_cases:
        component_id = _case_component_id(case, event_component)
        identity = _case_identity(case)
        status = str(case.get("status", "UNKNOWN"))
        previous = component_case_status_by_identity[component_id].get(identity)
        if previous is None or (
            not previous.startswith("EXECUTED") and status.startswith("EXECUTED")
        ):
            component_case_status_by_identity[component_id][identity] = status
    for case in merged_missing:
        component_id = _case_component_id(case, event_component)
        identity = _case_identity(case)
        status = str(case.get("status", "UNKNOWN"))
        component_strict_uncomputed_counts[component_id] += 1
        component_strict_uncomputed_status_counts[component_id][status] += 1
        previous = component_case_status_by_identity[component_id].get(identity)
        if previous is None:
            component_case_status_by_identity[component_id][identity] = status

    component_event_ids: dict[str, set[str]] = defaultdict(set)
    for event in merged_events:
        component_event_ids[str(event["model_component_id"])].add(str(event["id"]))
    component_coverage: dict[str, dict[str, Any]] = {}
    coverage_component_ids = (
        set(expected_components)
        | set(observed_components)
        | set(component_statuses)
        | set(component_case_status_by_identity)
        | set(component_atoms)
    )
    for component_id in sorted(coverage_component_ids):
        statuses_for_component = component_case_status_by_identity.get(component_id, {})
        status_counts: dict[str, int] = defaultdict(int)
        for status in statuses_for_component.values():
            status_counts[status] += 1
        component_conditional_case_count = len(statuses_for_component)
        component_conditional_executed_case_count = sum(
            status.startswith("EXECUTED") for status in statuses_for_component.values()
        )
        component_conditional_uncomputed_case_count = (
            component_conditional_case_count - component_conditional_executed_case_count
        )
        component_operator_limited_count = sum(
            count for status, count in status_counts.items()
            if "OPERATOR_LIMITED" in status
        )
        component_domain_incomplete_count = sum(
            count for status, count in status_counts.items()
            if "DOMAIN_INCOMPLETE" in status
        )
        component_failed_count = sum(
            count for status, count in status_counts.items()
            if "FAILED" in status
        )
        component_not_numerically_executed_count = sum(
            count for status, count in status_counts.items()
            if status in {"UNCOMPUTED", "FAILED"}
        )
        component_numerically_executed_count = component_conditional_executed_case_count
        component_qualified_evidence_withheld_count = (
            component_operator_limited_count + component_domain_incomplete_count
        )
        component_status = component_statuses.get(
            component_id,
            "MISSING_COVERAGE_LEDGER" if component_id in expected_components else "UNKNOWN_COMPONENT",
        )
        strict_count = component_strict_uncomputed_counts.get(component_id, 0)
        component_coverage[component_id] = {
            "component_id": component_id,
            "status": component_status,
            "event_count": len(component_event_ids.get(component_id, set())),
            "event_ids": sorted(component_event_ids.get(component_id, set())),
            "conditional_case_count": component_conditional_case_count,
            "conditional_executed_case_count": component_conditional_executed_case_count,
            "conditional_uncomputed_case_count": component_conditional_uncomputed_case_count,
            "strict_uncomputed_case_count": strict_count,
            "operator_limited_case_count": component_operator_limited_count,
            "domain_incomplete_case_count": component_domain_incomplete_count,
            "failed_case_count": component_failed_count,
            "not_numerically_executed_case_count": component_not_numerically_executed_count,
            "qualified_evidence_withheld_case_count": component_qualified_evidence_withheld_count,
            "numerically_executed_case_count": component_numerically_executed_count,
            "risk_atom_count": len(component_atoms.get(component_id, [])),
            "case_status_counts": dict(sorted(status_counts.items())),
            "strict_uncomputed_status_counts": dict(
                sorted(component_strict_uncomputed_status_counts.get(component_id, {}).items())
            ),
            "strict_gate_categories": _component_gate_categories(
                status=component_status,
                strict_uncomputed_case_count=strict_count,
                operator_limited_case_count=component_operator_limited_count,
                domain_incomplete_case_count=component_domain_incomplete_count,
                failed_case_count=component_failed_count,
            ),
            "frequency_is_not_reallocated": True,
        }
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
            "coverage": component_coverage.get(component_id, {}),
        }
    component_risk_ranking = _component_risk_ranking(component_contributions)
    scenario_family_contributions: dict[str, dict[str, Any]] = {}
    for family, atoms in sorted(family_atoms.items()):
        family_ir = {
            receptor_id: [0.0, 0.0] for receptor_id in sorted(receptor_ids)
        }
        for atom in atoms:
            weight = float(atom["initiating_frequency_per_year"]) * float(atom["conditional_weight"])
            harm = atom["receptor_harm_low_high"]
            for endpoint in range(2):
                for receptor_id in family_ir:
                    family_ir[receptor_id][endpoint] += weight * float(
                        harm[receptor_id][endpoint]
                    )
        scenario_family_contributions[family] = {
            "event_count": len({str(atom["event_id"]) for atom in atoms}),
            "risk_atom_count": len(atoms),
            "annual_ir_low_high": family_ir,
            "expected_death_fn_low_high": [
                _fn_curve(atoms, endpoint) for endpoint in range(2)
            ],
            "frequency_is_not_reallocated": True,
        }
    total_available = source_complete and not source_synthetic and not merged_exclusions
    provider_packet_promoted = (
        source_provider_packet_promoted
        and provider_packet_case_count > 0
        and provider_packet_case_count == qualified_provider_packet_case_count
    )
    qualified_facility_qra_available = (
        total_available and provider_packet_promoted and source_physical_validation
    )
    unique_blocking = list(dict.fromkeys(blocking_reasons))
    timing = {
        "campaign_count": len(campaign_rows),
        "fresh_physics_cases": sum(fresh_physics_case_counts),
        "case_min_ms": min(case_elapsed_values) if case_elapsed_values else None,
        "case_median_ms": median(case_elapsed_values) if case_elapsed_values else None,
        "case_max_ms": max(case_elapsed_values) if case_elapsed_values else None,
        "case_p95_ms": _linear_percentile(case_elapsed_values, 0.95),
        "case_p99_ms": _linear_percentile(case_elapsed_values, 0.99),
        "campaign_elapsed_ms": sum(timing_values),
        "campaign_elapsed_ms_sum": sum(timing_values),
        "campaign_elapsed_ms_min": min(timing_values) if timing_values else None,
        "campaign_elapsed_ms_median": median(timing_values) if timing_values else None,
        "campaign_elapsed_ms_max": max(timing_values) if timing_values else None,
        "campaign_elapsed_ms_p95": _linear_percentile(timing_values, 0.95),
        "campaign_elapsed_ms_p99": _linear_percentile(timing_values, 0.99),
        "stage_elapsed_ms": _stage_timing(merged_cases),
        "distribution": "across separately executed equipment campaigns; not repeated-run latency",
    }
    known_ir = {receptor_id: values[:] for receptor_id, values in endpoint_ir.items()}
    conditional_diagnostic_coverage = {
        "event_count": len(merged_events),
        "case_count": len(merged_cases),
        "uncomputed_case_count": len(merged_missing),
        "strict_uncomputed_case_count": len(merged_missing),
        "conditional_case_count": conditional_case_count,
        "conditional_executed_case_count": conditional_executed_case_count,
        "conditional_uncomputed_case_count": conditional_uncomputed_case_count,
        "overlapping_case_uncomputed_count": overlapping_case_uncomputed_count,
        "risk_atom_count": len(merged_atoms),
        "annual_condition_count": population_accounting["annual_condition_count"],
        "population_status": population_accounting["status"],
        "population_row_count": population_accounting["population_row_count"],
        "scenario_branch_status": scenario_branch_accounting["status"],
        "scenario_branch_cross_product_count": scenario_branch_accounting["cross_product_count"],
        "release_termination_inventory_summary": release_termination_inventory_ledger[
            "summary"
        ],
        "stage_timing": timing["stage_elapsed_ms"],
        "case_status_counts": dict(sorted(case_status_counts.items())),
        "uncomputed_status_counts": dict(sorted(uncomputed_status_counts.items())),
        "operator_limited_case_count": operator_limited_case_count,
        "domain_incomplete_case_count": domain_incomplete_case_count,
        "explicit_uncomputed_status_count": explicit_uncomputed_status_count,
        "failed_case_count": failed_case_count,
        "not_numerically_executed_case_count": not_numerically_executed_case_count,
        "qualified_evidence_withheld_case_count": qualified_evidence_withheld_case_count,
        "numerically_executed_case_count": numerically_executed_case_count,
        "observed_component_count": len(observed_components),
        "expected_component_count": len(expected_components),
        "component_status_counts": {
            status: sum(value == status for value in component_statuses.values())
            for status in sorted(set(component_statuses.values()))
        },
        "component_case_accounting": component_coverage,
        "required_accident_family_count": len(required_accident_families),
        "scope_blocker_count": len(unique_blocking),
    }
    return {
        "schema_version": "prism.facility_risk_ledger.v1",
        "status": "FACILITY_SCOPE_EXECUTED" if total_available else "PARTIAL_FACILITY_SCOPE",
        "facility_id": facility_id,
        "campaign_ids": campaign_ids,
        "campaign_digests": source_digests,
        "campaign_digest": canonical_digest({"campaign_ids": campaign_ids, "campaign_digests": source_digests}),
        "event_accounting": event_accounting,
        "frequency_port_binding": frequency_port_binding,
        "event_count": len(merged_events),
        "case_count": len(merged_cases),
        "uncomputed_case_count": len(merged_missing),
        "conditional_case_count": conditional_case_count,
        "conditional_executed_case_count": conditional_executed_case_count,
        "conditional_uncomputed_case_count": conditional_uncomputed_case_count,
        "not_numerically_executed_case_count": not_numerically_executed_case_count,
        "qualified_evidence_withheld_case_count": qualified_evidence_withheld_case_count,
        "numerically_executed_case_count": numerically_executed_case_count,
        "events": merged_events,
        "annual_conditions": [
            merged_annual_conditions[condition_id]
            for condition_id in sorted(merged_annual_conditions)
        ],
        "annual_condition_count": population_accounting["annual_condition_count"],
        "population_accounting": population_accounting,
        "scenario_branch_accounting": scenario_branch_accounting,
        "release_termination_inventory_ledger": release_termination_inventory_ledger,
        "strict_release_boundary": strict_release_boundary,
        "cases": merged_cases,
        "uncomputed_cases": merged_missing,
        "risk_atoms": merged_atoms,
        "risk_atoms_digest": canonical_digest(merged_atoms),
        "component_contributions": component_contributions,
        "component_risk_ranking": component_risk_ranking,
        "component_coverage_schema": "prism.component_coverage.v1",
        "component_coverage": component_coverage,
        "scenario_family_contributions": scenario_family_contributions,
        "observed_asset_ids": sorted(seen_assets),
        "observed_component_ids": sorted(observed_components),
        "expected_component_ids": sorted(expected_components),
        "component_statuses": component_statuses,
        "excluded_model_components": merged_exclusions,
        "required_accident_families": [str(family) for family in required_accident_families],
        "scope_matrix_digests": scope_matrix_digests,
        "accident_family_statuses": family_statuses,
        "declared_scope_numerically_complete": total_available,
        "known_contribution_annual_ir_low_high": known_ir,
        "known_contribution_expected_death_fn_low_high": fn,
        "conditional_diagnostic_facility_annual_ir_low_high": known_ir,
        "conditional_diagnostic_facility_expected_death_fn_low_high": fn,
        "conditional_diagnostic_facility_expected_death_fn_diagnostics": fn_diagnostics,
        "conditional_diagnostic_facility_risk_available": bool(merged_atoms),
        "conditional_diagnostic_facility_basis": (
            "linear sum of validated risk atoms from the evaluated equipment campaigns; "
            "scope blockers are retained and this view is not a qualified facility total"
        ),
        "conditional_diagnostic_case_accounting": (
            "conditional_case_count uses event, annual condition, release branch, and ignition "
            "branch identity; strict_uncomputed_case_count retains duplicate evidence rows "
            "used to explain operator-limited or domain-incomplete status"
        ),
        "conditional_diagnostic_facility_coverage": conditional_diagnostic_coverage,
        "declared_scope_annual_ir_low_high": known_ir if total_available else None,
        "declared_scope_expected_death_fn_low_high": fn if total_available else None,
        "total_facility_annual_ir_low_high": known_ir if total_available else None,
        "total_facility_expected_death_fn_low_high": fn if total_available else None,
        "physical_validation_claim": source_physical_validation and total_available,
        "provider_packet_case_count": provider_packet_case_count,
        "qualified_provider_packet_case_count": qualified_provider_packet_case_count,
        "provider_packet_promoted": provider_packet_promoted,
        "qualified_facility_qra_available": qualified_facility_qra_available,
        "complete_facility_qra_claim": qualified_facility_qra_available,
        "provider_qualification_blocking_reasons": list(dict.fromkeys(provider_qualification_blocking_reasons)),
        "synthetic_release_horizon_present": source_synthetic,
        "facility_total_risk_available": total_available,
        "blocking_reasons": unique_blocking,
        "timing": timing,
        "semantics": {
            "risk_sum": "validated risk atoms are summed once across disjoint equipment campaigns",
            "missing_scope": "missing or incomplete equipment/families remain partial and never become zero risk",
            "frequency": "each atom retains its initiating event frequency; no frequency inference or reallocation is performed",
            "frequency_port_binding": (
                "reviewed event port_ids are carried into cases and risk_atoms and checked again "
                "at facility merge; missing or mismatched port rows withhold the facility scope"
            ),
            "provider_packet": (
                "qualified provider packet evidence is counted separately from the numerical risk sum; "
                "a provider release history never creates or changes an initiating frequency"
            ),
            "fn": "expected-death F-N curves use the same atom-level convention as the campaign backend",
            "conditional_diagnostic_facility": (
                "facility IR/F-N is calculated from the atoms that reached the risk ledger, "
                "but remains diagnostic-only whenever declared scope, physical validation, "
                "or release-horizon blockers are present"
            ),
            "timing": (
                "whole-case and per-stage elapsed milliseconds are observed execution evidence; "
                "they are not repeated-run latency, throughput, or a fresh-physics 1 Hz claim"
            ),
            "component_coverage": (
                "each case is assigned to its provider component when available, then to its "
                "event component; conditional case identities are deduplicated, while strict "
                "uncomputed counts retain raw evidence rows and never create a frequency"
            ),
            "scenario_family_contributions": (
                "risk atoms retain their declared scenario_families; overlapping physical "
                "families are views of the same atoms and must not be summed across families"
            ),
            "component_risk_ranking": (
                "equipment rows are ranked by peak receptor IR from the same conditional "
                "risk atoms; this is a diagnostic triage view and never reallocates frequency "
                "or promotes facility IR/F-N"
            ),
            "scenario_branch_accounting": (
                "annual-condition weather, release/termination, and ignition branches are "
                "preserved as diagnostics over the same risk atoms; no branch frequency is "
                "inferred, reallocated, or double-counted"
            ),
            "release_termination_inventory": (
                "case-level provider duration, termination, isolation, inventory and mass "
                "closure are retained in one facility ledger; withheld copies remain in the "
                "summary and are never converted to zero risk"
            ),
        },
    }
