"""Independently audit literature-frequency sensitivity for a facility ledger.

The existing uncertainty calculation intentionally reweights saved risk atoms
without rerunning consequence physics.  This module reruns that accounting
calculation from the saved campaign and scenario definitions, then compares it
with the stored facility assessment.  It never creates a frequency, a
confidence interval, or a qualified facility-QRA result.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from .uncertainty import LiteratureFrequencyScenario, literature_frequency_uncertainty


FACILITY_FREQUENCY_AUDIT_SCHEMA = "prism.facility_frequency_uncertainty_audit.v1"


class FacilityFrequencyUncertaintyAuditError(ValueError):
    """Raised when frequency sensitivity inputs cannot be audited safely."""


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


def _compare_value(left: Any, right: Any, path: str, mismatches: list[str]) -> None:
    if _finite(left) and _finite(right):
        if not _same_number(left, right):
            mismatches.append(f"{path} differs")
        return
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(map(str, left)) != set(map(str, right)):
            mismatches.append(f"{path} keys differ")
            return
        for key in right:
            left_key = key if key in left else next((candidate for candidate in left if str(candidate) == str(key)), key)
            _compare_value(left.get(left_key), right.get(key), f"{path}.{key}", mismatches)
        return
    if isinstance(left, Sequence) and not isinstance(left, (str, bytes)) and isinstance(right, Sequence) and not isinstance(right, (str, bytes)):
        if len(left) != len(right):
            mismatches.append(f"{path} length differs")
            return
        for index, (left_value, right_value) in enumerate(zip(left, right)):
            _compare_value(left_value, right_value, f"{path}[{index}]", mismatches)
        return
    if left != right:
        mismatches.append(f"{path} differs")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FacilityFrequencyUncertaintyAuditError(f"{label} must be an object")
    return value


def _family_frequency_coverage(campaign: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize explicit family-to-event frequency coverage.

    Families are read only from risk-atom metadata.  This intentionally does
    not derive a family from an event ID, component kind, or release name.
    Missing labels and missing event identities remain visible in the summary.
    """

    events = {
        str(row.get("id")): row
        for row in campaign.get("events", ())
        if isinstance(row, Mapping) and row.get("id")
    }
    rows: dict[str, dict[str, Any]] = {}
    unclassified_atom_count = 0
    for atom in campaign.get("risk_atoms", ()):
        if not isinstance(atom, Mapping):
            continue
        raw_families = atom.get("scenario_families")
        families = (
            tuple(sorted({str(value).strip() for value in raw_families if str(value).strip()}))
            if isinstance(raw_families, Sequence) and not isinstance(raw_families, (str, bytes))
            else ()
        )
        if not families:
            unclassified_atom_count += 1
            continue
        event_id = str(atom.get("event_id") or "")
        event = events.get(event_id)
        for family in families:
            row = rows.setdefault(
                family,
                {
                    "risk_atom_count": 0,
                    "event_ids": set(),
                    "missing_event_ids": set(),
                    "published_bound_event_count": 0,
                    "published_rate_only_event_count": 0,
                },
            )
            row["risk_atom_count"] += 1
            if event is None:
                row["missing_event_ids"].add(event_id)
                continue
            row["event_ids"].add(event_id)
            p05 = event.get("marginal_p05_per_year")
            p95 = event.get("marginal_p95_per_year")
            if (
                _finite(p05)
                and _finite(p95)
                and float(p05) <= float(p95)
            ):
                row["published_bound_event_count"] += 1
            else:
                row["published_rate_only_event_count"] += 1

    coverage: dict[str, Any] = {}
    for family, raw in sorted(rows.items()):
        missing_events = sorted(raw["missing_event_ids"])
        status = (
            "MISSING_EVENT_FREQUENCY"
            if missing_events
            else "PUBLISHED_BOUNDS_COMPLETE"
            if raw["published_rate_only_event_count"] == 0
            else "PUBLISHED_RATE_ONLY"
        )
        coverage[family] = {
            "status": status,
            "risk_atom_count": raw["risk_atom_count"],
            "event_ids": sorted(raw["event_ids"]),
            "missing_event_ids": missing_events,
            "published_bound_event_count": raw["published_bound_event_count"],
            "published_rate_only_event_count": raw["published_rate_only_event_count"],
        }
    return {
        "families": coverage,
        "unclassified_atom_count": unclassified_atom_count,
        "frequency_inference_performed": False,
        "family_labels_are_explicit": True,
    }


def build_facility_frequency_uncertainty_audit(
    campaign_result: Mapping[str, Any],
    frequency_scenarios: Mapping[str, Any],
    stored_frequency_uncertainty: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute and compare the saved conditional frequency-sensitivity ledger."""
    campaign = _object(campaign_result, "campaign_result")
    scenario_source = _object(frequency_scenarios, "frequency_scenarios")
    stored = _object(stored_frequency_uncertainty, "stored_frequency_uncertainty")
    raw_scenarios = scenario_source.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise FacilityFrequencyUncertaintyAuditError(
            "frequency_scenarios.scenarios must be a nonempty array"
        )
    try:
        scenarios = tuple(
            LiteratureFrequencyScenario.model_validate(row) for row in raw_scenarios
        )
        recomputed = literature_frequency_uncertainty(campaign, scenarios)
    except (TypeError, ValueError, KeyError) as error:
        raise FacilityFrequencyUncertaintyAuditError(str(error)) from error

    mismatches: list[str] = []
    if stored.get("campaign_digest") != recomputed.get("campaign_digest"):
        mismatches.append("campaign digest differs")
    if stored.get("physical_risk_atoms_digest") != recomputed.get("physical_risk_atoms_digest"):
        mismatches.append("physical risk atom digest differs")
    for field in (
        "correlation_comparison_present",
        "facility_credible_interval",
        "statistical_confidence_interval",
        "fresh_physics_executed",
        "asset_rank_stability",
        "scenario_family_rank_stability",
    ):
        _compare_value(stored.get(field), recomputed.get(field), field, mismatches)

    stored_rows = stored.get("scenarios")
    recomputed_rows = recomputed.get("scenarios")
    if not isinstance(stored_rows, list) or not isinstance(recomputed_rows, list):
        mismatches.append("stored or recomputed scenario rows are missing")
        stored_rows = []
        recomputed_rows = []
    if len(stored_rows) != len(recomputed_rows):
        mismatches.append("scenario count differs")
    scenario_fields = (
        "scenario",
        "event_frequency_per_year",
        "known_annual_ir_low_high",
        "known_expected_death_fn_low_high",
        "conditional_diagnostic_facility_annual_ir_low_high",
        "conditional_diagnostic_facility_expected_death_fn_low_high",
        "asset_known_annual_expected_fatalities_low_high",
        "asset_rank_by_known_expected_fatalities_low_high",
        "scenario_family_known_expected_fatalities_low_high",
        "scenario_family_rank_by_known_expected_fatalities_low_high",
    )
    for index, expected in enumerate(recomputed_rows):
        if index >= len(stored_rows):
            break
        actual = stored_rows[index]
        if not isinstance(actual, Mapping):
            mismatches.append(f"scenario[{index}] is not an object")
            continue
        for field in scenario_fields:
            _compare_value(
                actual.get(field),
                expected.get(field),
                f"scenarios[{index}].{field}",
                mismatches,
            )

    invariant_reasons: list[str] = []
    if scenario_source.get("frequency_inference_performed") is not False:
        invariant_reasons.append("scenario source permits frequency inference")
    if scenario_source.get("facility_credible_interval") is not False:
        invariant_reasons.append("scenario source permits a facility credible interval")
    if recomputed.get("fresh_physics_executed") is not False:
        invariant_reasons.append("frequency sensitivity reran fresh physics")
    if recomputed.get("statistical_confidence_interval") is not False:
        invariant_reasons.append("frequency sensitivity created a statistical confidence interval")
    if recomputed.get("facility_credible_interval") is not False:
        invariant_reasons.append("frequency sensitivity created a facility credible interval")
    for index, row in enumerate(raw_scenarios):
        provenance = row.get("provenance") if isinstance(row, Mapping) else None
        if not isinstance(provenance, str) or "no frequency inference" not in provenance.lower():
            invariant_reasons.append(f"scenario[{index}] lacks no-frequency-inference provenance")
    mismatches.extend(invariant_reasons)
    blocking = list(dict.fromkeys(mismatches))
    closed = bool(recomputed_rows) and not blocking
    family_frequency_coverage = _family_frequency_coverage(campaign)
    return {
        "schema_version": FACILITY_FREQUENCY_AUDIT_SCHEMA,
        "status": (
            "FACILITY_FREQUENCY_UNCERTAINTY_CLOSED_DIAGNOSTIC"
            if closed
            else "BLOCKED_FACILITY_FREQUENCY_UNCERTAINTY_AUDIT"
        ),
        "facility_id": campaign.get("facility_id"),
        "scenario_count": len(recomputed_rows),
        "scenario_ids": [
            row.get("id") for row in raw_scenarios if isinstance(row, Mapping)
        ],
        "risk_atom_count": len(campaign.get("risk_atoms", []))
        if isinstance(campaign.get("risk_atoms"), list)
        else None,
        "recomputed_campaign_digest": recomputed.get("campaign_digest"),
        "stored_campaign_digest": stored.get("campaign_digest"),
        "recomputed_physical_risk_atoms_digest": recomputed.get("physical_risk_atoms_digest"),
        "stored_physical_risk_atoms_digest": stored.get("physical_risk_atoms_digest"),
        "correlation_comparison_present": recomputed.get("correlation_comparison_present"),
        "facility_credible_interval": recomputed.get("facility_credible_interval"),
        "statistical_confidence_interval": recomputed.get("statistical_confidence_interval"),
        "fresh_physics_executed": recomputed.get("fresh_physics_executed"),
        "mismatch_count": len(blocking),
        "blocking_reasons": blocking,
        "frequency_inference_performed": False,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "diagnostic_only": True,
        "scenario_family_frequency_coverage": family_frequency_coverage,
        "interpretation": (
            "Published and fixed literature-frequency scenarios reproduce the saved conditional "
            "IR/F-N sensitivity without rerunning physics or inferring missing frequency. "
            "Scope, provider, validation and facility-QRA gates remain independent."
        ),
    }


__all__ = [
    "FACILITY_FREQUENCY_AUDIT_SCHEMA",
    "FacilityFrequencyUncertaintyAuditError",
    "build_facility_frequency_uncertainty_audit",
]
