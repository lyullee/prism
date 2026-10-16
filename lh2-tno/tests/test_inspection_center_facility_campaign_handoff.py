from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import sys


def test_facility_campaign_handoff_preserves_normal_components_and_population_boundary():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from build_inspection_center_facility_campaign_handoff import run

    output = root / ".tmp_test_inspection_center_facility_campaign_handoff.json"
    try:
        result = run(
            Namespace(
                bridge=root / "examples/inspection_center_facility_hazop_bridge.json",
                annual_conditions=root / "results/20261009/generic_full_scope_worklist/campaign_result.json",
                frequency_scenarios=root / "results/20261110/native_full_scope_frequency_assessment_latest2/frequency_scenarios.json",
                output=output,
            )
        )
    finally:
        output.unlink(missing_ok=True)

    assert result["status"] == "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    assert result["campaign"]["status"] == "PARTIAL_DECLARED_SCOPE"
    assert result["facility_ledger"]["status"] == "PARTIAL_FACILITY_SCOPE"
    assert result["facility_ledger"]["population_accounting"]["status"] == (
        "EXPLICIT_CONDITION_POPULATION"
    )
    assert result["facility_ledger"]["total_facility_annual_ir_low_high"] is None
    assert result["facility_ledger"]["total_facility_expected_death_fn_low_high"] is None
    assert result["equipment_state_release_audit"]["status"] == (
        "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
    )
    assert result["equipment_state_release_audit"]["complete_case_count"] == 1
    assert result["risk_atom_chain_audit"]["status"] == "PARTIAL_RISK_ATOM_CHAIN"
    assert result["facility_campaign_handoff_audit"]["facility_qra_claim"] is False
    assert result["frequency_uncertainty"]["status"] == (
        "LITERATURE_SCENARIO_SENSITIVITY_AVAILABLE"
    )
    assert result["frequency_uncertainty"]["marginal_p05_per_year"] is None
    assert result["frequency_uncertainty"]["marginal_p95_per_year"] is None
    assert all(
        row["status"] == "FIXED_CATALOGUE_RATE_SCENARIO"
        for row in result["frequency_uncertainty"]["rows"]
    )
    assert set(result["facility_campaign_handoff_audit"]["withheld_normal_component_ids"]) == {
        "lh2-intake-tank",
        "lh2-storage-vent",
    }
