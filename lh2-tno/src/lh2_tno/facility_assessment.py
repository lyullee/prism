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
from .facility_ledger import merge_facility_campaign_results
from .uncertainty import LiteratureFrequencyScenario, literature_frequency_uncertainty


def build_facility_assessment(
    campaign_results: Sequence[Mapping[str, Any]],
    *,
    expected_component_ids: Sequence[str] = (),
    scope_matrices: Sequence[Mapping[str, Any]] = (),
    required_accident_families: Sequence[str] = (),
    frequency_scenarios: Sequence[LiteratureFrequencyScenario] = (),
) -> dict[str, Any]:
    """Return one facility risk, coverage, and frequency-sensitivity artifact.

    ``campaign_results`` must already contain evaluated cases and risk atoms.
    Frequency scenarios only reweight those saved atoms; they never trigger a
    fresh physics calculation.  The caller must provide a complete expected
    component list and any accident-family matrices that are required for a
    facility-total promotion.
    """
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
    assessment = {
        "schema_version": "prism.facility_assessment.v1",
        "status": ledger["status"],
        "facility_id": ledger["facility_id"],
        "facility_total_risk_available": ledger["facility_total_risk_available"],
        "conditional_diagnostic_facility_risk_available": ledger[
            "conditional_diagnostic_facility_risk_available"
        ],
        "conditional_diagnostic_facility_annual_ir_low_high": ledger[
            "conditional_diagnostic_facility_annual_ir_low_high"
        ],
        "conditional_diagnostic_facility_expected_death_fn_low_high": ledger[
            "conditional_diagnostic_facility_expected_death_fn_low_high"
        ],
        "conditional_diagnostic_facility_coverage": ledger[
            "conditional_diagnostic_facility_coverage"
        ],
        "facility_risk_ledger": ledger,
        "frequency_uncertainty": uncertainty,
        "fresh_physics_executed": False,
        "physical_validation_claim": False,
        "semantics": {
            "orchestration": "campaign results are merged once; no source or consequence model is rerun",
            "partial_scope": "missing equipment, accident families, or event case accounting remains explicit and withholds facility totals",
            "conditional_diagnostic_facility": "the atom-level facility IR/F-N sum is exposed for diagnostics and frequency sensitivity, while qualification blockers continue to withhold the facility total",
            "frequency": "optional literature scenarios reweight saved risk atoms and do not infer missing frequency",
        },
    }
    assessment["assessment_digest"] = canonical_digest(assessment)
    return assessment
