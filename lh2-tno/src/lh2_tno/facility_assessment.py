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
    _stage_timing,
    merge_facility_campaign_results,
)
from .release_ledger import build_release_termination_inventory_ledger
from .uncertainty import LiteratureFrequencyScenario, literature_frequency_uncertainty


def build_facility_assessment(
    campaign_results: Sequence[Mapping[str, Any]],
    *,
    expected_component_ids: Sequence[str] = (),
    scope_matrices: Sequence[Mapping[str, Any]] = (),
    required_accident_families: Sequence[str] = (),
    frequency_scenarios: Sequence[LiteratureFrequencyScenario] = (),
    provider_qualification_coverage: Mapping[str, Any] | None = None,
    facility_case_packet_coverage: Mapping[str, Any] | None = None,
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
    ledger_case_count = ledger.get("provider_packet_case_count")
    case_coverage_gate = None
    if facility_case_packet_coverage is not None:
        coverage = facility_case_packet_coverage
        case_request_count = coverage.get("case_request_count")
        qualified_case_count = coverage.get("qualified_provider_case_count")
        qualified_event_count = coverage.get("qualified_provider_event_count")
        reasons: list[str] = []
        if coverage.get("schema") != "prism.facility_case_provider_coverage.v1":
            reasons.append("facility case packet coverage has an unexpected schema")
        if coverage.get("status") != "QUALIFIED_FULL_CASE_COVERAGE":
            reasons.append("facility case packet coverage is not full qualified coverage")
        if not isinstance(case_request_count, int) or case_request_count <= 0:
            reasons.append("facility case packet coverage lacks a positive case request count")
        if qualified_case_count != case_request_count:
            reasons.append("facility case packet coverage has cases without qualified packets")
        if not isinstance(qualified_event_count, int) or qualified_event_count <= 0:
            reasons.append("facility case packet coverage has no qualified provider events")
        if isinstance(ledger_case_count, int) and case_request_count != ledger_case_count:
            reasons.append("facility case packet coverage count does not match the merged facility ledger")
        policy = coverage.get("promotion_policy")
        if not isinstance(policy, Mapping):
            reasons.append("facility case packet coverage lacks its promotion policy")
            policy = {}
        if policy.get("frequency_is_not_assigned") is not True:
            reasons.append("facility case packet coverage does not close the frequency boundary")
        if policy.get("physical_validation_claim") is not False:
            reasons.append("facility case packet coverage contains a physical-validation claim")
        if policy.get("facility_ir_fn_promotion") != (
            "requires this full case gate plus independent scope and validation gates"
        ):
            reasons.append("facility case packet coverage does not define the IR/F-N promotion boundary")
        case_coverage_gate = {
            "schema": coverage.get("schema"),
            "coverage_status": coverage.get("status"),
            "case_request_count": case_request_count,
            "ledger_provider_packet_case_count": ledger_case_count,
            "qualified_provider_event_count": qualified_event_count,
            "qualified_provider_case_count": qualified_case_count,
            "provider_evidence_row_count": coverage.get("provider_evidence_row_count"),
            "status_counts": coverage.get("status_counts"),
            "complete": not reasons,
            "blocking_reasons": reasons,
            "frequency_inference_performed": False,
            "frequency_is_not_assigned": policy.get("frequency_is_not_assigned"),
            "physical_validation_claim": False,
            "facility_ir_fn_promotion": policy.get("facility_ir_fn_promotion"),
        }
    elif isinstance(ledger_case_count, int) and ledger_case_count > 0:
        case_coverage_gate = {
            "schema": None,
            "coverage_status": "MISSING_REPORT",
            "case_request_count": None,
            "ledger_provider_packet_case_count": ledger_case_count,
            "qualified_provider_event_count": 0,
            "qualified_provider_case_count": 0,
            "provider_evidence_row_count": 0,
            "status_counts": {},
            "complete": False,
            "blocking_reasons": [
                "facility case packet coverage report is required when provider cases are present"
            ],
            "frequency_inference_performed": False,
            "frequency_is_not_assigned": None,
            "physical_validation_claim": False,
            "facility_ir_fn_promotion": None,
        }
    case_coverage_allows_qra = (
        case_coverage_gate is None or case_coverage_gate["complete"]
    )
    qualified_facility_qra_available = (
        ledger["qualified_facility_qra_available"]
        and qualification_gate_allows_qra
        and case_coverage_allows_qra
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
    release_termination_inventory_ledger = ledger.get(
        "release_termination_inventory_ledger"
    )
    if not isinstance(release_termination_inventory_ledger, Mapping):
        cases = ledger.get("cases", ())
        uncomputed_cases = ledger.get("uncomputed_cases", ())
        case_rows = (
            cases
            if isinstance(cases, Sequence) and not isinstance(cases, (str, bytes))
            else ()
        )
        withheld_rows = (
            uncomputed_cases
            if isinstance(uncomputed_cases, Sequence)
            and not isinstance(uncomputed_cases, (str, bytes))
            else ()
        )
        release_termination_inventory_ledger = build_release_termination_inventory_ledger(
            case_rows,
            withheld_cases=withheld_rows,
        )
    timing = ledger.get("timing")
    timing = dict(timing) if isinstance(timing, Mapping) else {}
    if not isinstance(timing.get("stage_elapsed_ms"), Mapping):
        cases = ledger.get("cases", ())
        case_rows = (
            cases
            if isinstance(cases, Sequence) and not isinstance(cases, (str, bytes))
            else ()
        )
        timing["stage_elapsed_ms"] = _stage_timing(case_rows)
        ledger["timing"] = timing
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
        "facility_case_packet_coverage": case_coverage_gate,
        "facility_case_packet_coverage_complete": (
            case_coverage_gate["complete"] if case_coverage_gate is not None else None
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
        "release_termination_inventory_ledger": release_termination_inventory_ledger,
        "conditional_diagnostic_facility_coverage": ledger[
            "conditional_diagnostic_facility_coverage"
        ],
        "component_risk_ranking": ledger.get(
            "component_risk_ranking",
            {
                "status": "NO_RISK_ATOMS",
                "component_count": 0,
                "ranking_basis": (
                    "descending peak receptor annual IR at the high uncertainty endpoint; "
                    "diagnostic triage only"
                ),
                "frequency_reallocation_performed": False,
                "facility_ir_fn_promotion": False,
                "rows": [],
            },
        ),
        "timing": timing,
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
            "facility_case_packet_coverage": (
                "exact facility case identity must be qualified before the facility QRA gate can open; "
                "missing cases remain explicit and do not infer frequency or physical validation"
            ),
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
            "timing": (
                "facility timing preserves observed whole-case and stage elapsed values; "
                "it does not claim repeated-run throughput or fresh-physics 1 Hz service"
            ),
        },
    }
    assessment["assessment_digest"] = canonical_digest(assessment)
    return assessment
