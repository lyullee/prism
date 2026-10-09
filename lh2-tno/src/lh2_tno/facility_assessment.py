"""Build one auditable facility assessment from evaluated campaign ledgers.

The assessment is an orchestration boundary.  It does not run an equipment
solver, SLABx, weather, ignition, or population model again.  It merges the
already evaluated risk atoms with :mod:`facility_ledger` and, when requested,
passes that ledger to the literature-frequency uncertainty calculator.  A
partial ledger remains partial in the combined artifact.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import canonical_digest
from .facility_ledger import (
    _fn_diagnostics,
    _population_accounting,
    _scenario_branch_accounting,
    merge_facility_campaign_results,
)
from .uncertainty import LiteratureFrequencyScenario, literature_frequency_uncertainty


def build_facility_assessment(
    campaign_results: Sequence[Mapping[str, Any]],
    *,
    expected_component_ids: Sequence[str] = (),
    scope_matrices: Sequence[Mapping[str, Any]] = (),
    required_accident_families: Sequence[str] = (),
    frequency_scenarios: Sequence[LiteratureFrequencyScenario] = (),
    provider_qualification_coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one facility risk, coverage, and frequency-sensitivity artifact.

    ``campaign_results`` must already contain evaluated cases and risk atoms.
    Frequency scenarios only reweight those saved atoms; they never trigger a
    fresh physics calculation.  The caller must provide a complete expected
    component list and any accident-family matrices that are required for a
    facility-total promotion.
    """
    # The CLI commonly receives the output of ``merge_facility_campaigns``.
    # Re-merging that already aggregated ledger as if it were one equipment
    # campaign discards its component coverage rows and turns every component
    # into ``MISSING_COVERAGE_LEDGER``.  Preserve the authoritative facility
    # ledger and only merge when the inputs are actual campaign results.
    if (
        len(campaign_results) == 1
        and campaign_results[0].get("schema_version") == "prism.facility_risk_ledger.v1"
    ):
        ledger = dict(campaign_results[0])
    else:
        ledger = merge_facility_campaign_results(
            campaign_results,
            expected_component_ids=expected_component_ids,
            scope_matrices=scope_matrices,
            required_accident_families=required_accident_families,
        )
    scenarios = tuple(frequency_scenarios)
    uncertainty = (
        literature_frequency_uncertainty(ledger, scenarios)
        if scenarios
        else None
    )
    qualification_gate = None
    if provider_qualification_coverage is not None:
        coverage = provider_qualification_coverage
        exact_match_count = coverage.get("exact_match_count")
        worklist_event_count = coverage.get("worklist_event_count")
        qualified_count = coverage.get("qualified_provider_packet_count")
        unqualified_count = coverage.get("unqualified_exact_match_count")
        ledger_qualified_count = ledger["qualified_provider_packet_case_count"]
        reasons: list[str] = []
        if coverage.get("qualification_assessed") is not True:
            reasons.append("provider qualification coverage was not assessed")
        if coverage.get("qualification_status") != "QUALIFIED_FULL_WORKLIST":
            reasons.append("provider qualification coverage is not a full worklist qualification")
        if not isinstance(exact_match_count, int) or not isinstance(worklist_event_count, int):
            reasons.append("provider qualification coverage lacks integer worklist/exact-match counts")
        elif exact_match_count != worklist_event_count:
            reasons.append("provider qualification coverage has unmatched worklist events")
        if not isinstance(qualified_count, int) or qualified_count <= 0:
            reasons.append("provider qualification coverage has no qualified packets")
        if unqualified_count != 0:
            reasons.append("provider qualification coverage retains unqualified exact matches")
        if isinstance(qualified_count, int) and qualified_count != ledger_qualified_count:
            reasons.append(
                "provider qualification coverage count does not match the merged campaign ledger"
            )
        qualification_gate = {
            "coverage_status": coverage.get("status"),
            "qualification_status": coverage.get("qualification_status"),
            "worklist_event_count": worklist_event_count,
            "exact_match_count": exact_match_count,
            "qualified_provider_packet_count": qualified_count,
            "unqualified_exact_match_count": unqualified_count,
            "ledger_qualified_provider_packet_case_count": ledger_qualified_count,
            "complete": not reasons,
            "blocking_reasons": reasons,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
        }
    qualification_gate_allows_qra = (
        qualification_gate is None or qualification_gate["complete"]
    )
    qualified_facility_qra_available = (
        ledger["qualified_facility_qra_available"]
        and qualification_gate_allows_qra
    )
    # Older saved ledgers predate the explicit F/N diagnostics field.  Keep
    # those artifacts readable and derive the explanation from their retained
    # risk atoms instead of treating the missing metadata as a failed
    # assessment.
    fn_diagnostics = ledger.get(
        "conditional_diagnostic_facility_expected_death_fn_diagnostics"
    )
    if not isinstance(fn_diagnostics, Mapping):
        atoms = ledger.get("risk_atoms", ())
        fn_diagnostics = _fn_diagnostics(
            atoms
            if isinstance(atoms, Sequence) and not isinstance(atoms, (str, bytes))
            else ()
        )
    population_accounting = ledger.get("population_accounting")
    if not isinstance(population_accounting, Mapping):
        atoms = ledger.get("risk_atoms", ())
        atom_rows = (
            atoms
            if isinstance(atoms, Sequence) and not isinstance(atoms, (str, bytes))
            else ()
        )
        receptors = {
            str(receptor_id)
            for atom in atom_rows
            if isinstance(atom, Mapping)
            for receptor_id in (atom.get("receptor_harm_low_high", {}) or {})
        }
        conditions = {
            str(condition.get("id")): condition
            for condition in ledger.get("annual_conditions", ())
            if isinstance(condition, Mapping) and condition.get("id")
        }
        population_accounting = _population_accounting(
            conditions,
            referenced_condition_ids=[
                str(atom.get("annual_condition_id", ""))
                for atom in atom_rows
                if isinstance(atom, Mapping)
            ],
            receptor_ids=receptors,
        )
    scenario_branch_accounting = ledger.get("scenario_branch_accounting")
    if not isinstance(scenario_branch_accounting, Mapping):
        atoms = ledger.get("risk_atoms", ())
        atom_rows = (
            atoms
            if isinstance(atoms, Sequence) and not isinstance(atoms, (str, bytes))
            else ()
        )
        conditions = {
            str(condition.get("id")): condition
            for condition in ledger.get("annual_conditions", ())
            if isinstance(condition, Mapping) and condition.get("id")
        }
        scenario_branch_accounting = _scenario_branch_accounting(atom_rows, conditions)
    assessment = {
        "schema_version": "prism.facility_assessment.v1",
        "status": ledger["status"],
        "facility_id": ledger["facility_id"],
        "facility_total_risk_available": ledger["facility_total_risk_available"],
        "provider_packet_case_count": ledger["provider_packet_case_count"],
        "qualified_provider_packet_case_count": ledger[
            "qualified_provider_packet_case_count"
        ],
        "provider_packet_promoted": ledger["provider_packet_promoted"],
        "qualified_facility_qra_available": qualified_facility_qra_available,
        "complete_facility_qra_claim": qualified_facility_qra_available,
        "provider_qualification_blocking_reasons": ledger[
            "provider_qualification_blocking_reasons"
        ],
        "provider_qualification_coverage": qualification_gate,
        "provider_qualification_coverage_complete": (
            qualification_gate["complete"] if qualification_gate is not None else None
        ),
        "conditional_diagnostic_facility_risk_available": ledger[
            "conditional_diagnostic_facility_risk_available"
        ],
        "conditional_diagnostic_facility_annual_ir_low_high": ledger[
            "conditional_diagnostic_facility_annual_ir_low_high"
        ],
        "conditional_diagnostic_facility_expected_death_fn_low_high": ledger[
            "conditional_diagnostic_facility_expected_death_fn_low_high"
        ],
        "conditional_diagnostic_facility_expected_death_fn_diagnostics": fn_diagnostics,
        "annual_condition_count": population_accounting.get("annual_condition_count", 0),
        "population_accounting": population_accounting,
        "scenario_branch_accounting": scenario_branch_accounting,
        "release_termination_inventory_ledger": ledger.get(
            "release_termination_inventory_ledger"
        ),
        "conditional_diagnostic_facility_coverage": ledger[
            "conditional_diagnostic_facility_coverage"
        ],
        "facility_risk_ledger": ledger,
        "frequency_uncertainty": uncertainty,
        "fresh_physics_executed": False,
        "physical_validation_claim": ledger["physical_validation_claim"],
        "semantics": {
            "orchestration": "campaign results are merged once; no source or consequence model is rerun",
            "partial_scope": "missing equipment, accident families, or event case accounting remains explicit and withholds facility totals",
            "conditional_diagnostic_facility": "the atom-level facility IR/F-N sum is exposed for diagnostics and frequency sensitivity, while qualification blockers continue to withhold the facility total",
            "frequency": "optional literature scenarios reweight saved risk atoms and do not infer missing frequency",
            "provider_packet": ledger["semantics"]["provider_packet"],
            "scenario_branch_accounting": (
                "annual-condition weather, release/termination, and ignition branches are "
                "preserved over the same validated atoms; no frequency inference or branch "
                "reallocation is performed"
            ),
            "release_termination_inventory": (
                "case-level provider duration, termination, isolation, inventory and mass "
                "closure are carried through the merged facility ledger without filling "
                "missing branch values"
            ),
        },
    }
    assessment["assessment_digest"] = canonical_digest(assessment)
    return assessment
