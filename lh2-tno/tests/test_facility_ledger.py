import pytest

from lh2_tno.facility_assessment import build_facility_assessment
from lh2_tno.facility_ledger import (
    FacilityLedgerError,
    merge_facility_campaign_results,
)
from lh2_tno.uncertainty import LiteratureFrequencyScenario, literature_frequency_uncertainty


def _result(
    *,
    event_id: str,
    asset_id: str,
    component_id: str,
    frequency: float,
    conditional_weight: float = 1.0,
    incomplete: bool = False,
):
    atom = {
        "event_id": event_id,
        "asset_id": asset_id,
        "annual_condition_id": "weather-1",
        "release_branch_id": "release-1",
        "ignition_branch": "direct_fire",
        "initiating_frequency_per_year": frequency,
        "conditional_weight": conditional_weight,
        "receptor_harm_low_high": {
            "receptor-a": [0.7, 0.8],
            "receptor-b": [0.5, 0.6],
        },
        "expected_deaths_low_high": [1.2, 1.4],
    }
    return {
        "facility_id": "facility-1",
        "campaign_digest": f"digest-{event_id}",
        "events": [{
            "id": event_id,
            "asset_id": asset_id,
            "model_component_id": component_id,
            "profile": "LH2_PIPE",
            "loc": "AREA_0.01%",
            "basis": "LH2_LITERATURE",
            "base_rate": frequency,
            "rate_unit": "item^-1 year^-1",
            "exposure_multiplier": 1.0,
            "annual_frequency_per_year": frequency,
            "statistic": "published_median",
            "marginal_p05_per_year": frequency * 0.1,
            "marginal_p95_per_year": frequency * 10.0,
            "source": "facility-ledger test source",
            "source_sha256": "a" * 64,
            "catalogue_digest": "b" * 64,
            "release": {"mode": "hole", "hole_diameter_m": 0.01},
            "classification_basis": "facility-ledger test boundary",
            "limitations": ["test only"],
            "physical_validation_claim": False,
        }],
        "cases": [{"event_id": event_id, "status": "EXECUTED", "elapsed_ms": 5.0}],
        "uncomputed_cases": ([{"event_id": event_id, "status": "UNCOMPUTED"}] if incomplete else []),
        "risk_atoms": [atom],
        "declared_scope_numerically_complete": not incomplete,
        "synthetic_release_horizon_present": False,
        "excluded_model_components": {},
        "physical_validation_claim": False,
        "coverage": {
            "by_component": [{
                "component_id": component_id,
                "scope_status": "PARTIAL" if incomplete else "EXECUTED",
            }],
        },
        "timing": {"fresh_physics_cases": 1, "campaign_elapsed_ms": 10.0},
    }


def test_facility_ledger_sums_disjoint_equipment_atoms_once():
    result = merge_facility_campaign_results(
        [
            {"campaign_id": "tank-campaign", "result": _result(
                event_id="event-tank", asset_id="tank-asset", component_id="tank-01",
                frequency=1e-3,
            )},
            {"campaign_id": "pipe-campaign", "result": _result(
                event_id="event-pipe", asset_id="pipe-asset", component_id="pipe-01",
                frequency=2e-3, conditional_weight=0.5,
            )},
        ],
        expected_component_ids=("tank-01", "pipe-01"),
    )

    assert result["status"] == "FACILITY_SCOPE_EXECUTED"
    assert result["facility_total_risk_available"] is True
    assert result["provider_packet_promoted"] is False
    assert result["qualified_facility_qra_available"] is False
    assert result["provider_qualification_blocking_reasons"]
    assert result["known_contribution_annual_ir_low_high"]["receptor-a"] == pytest.approx(
        [0.0014, 0.0016]
    )
    assert result["total_facility_annual_ir_low_high"] == result[
        "known_contribution_annual_ir_low_high"
    ]
    assert result["timing"]["campaign_count"] == 2
    assert result["timing"]["fresh_physics_cases"] == 2
    assert result["timing"]["case_p95_ms"] == pytest.approx(5.0)
    assert result["timing"]["campaign_elapsed_ms"] == pytest.approx(20.0)
    assert result["timing"]["campaign_elapsed_ms_p95"] == pytest.approx(10.0)
    assert result["risk_atoms_digest"]
    assert result["component_contributions"]["tank-01"]["annual_ir_low_high"]["receptor-a"] == pytest.approx(
        [0.0007, 0.0008]
    )
    assert result["component_contributions"]["pipe-01"]["annual_ir_low_high"]["receptor-a"] == pytest.approx(
        [0.0007, 0.0008]
    )
    assert result["component_contributions"]["tank-01"]["frequency_is_not_reallocated"] is True
    assert result["scenario_family_contributions"] == {}


def test_facility_ledger_promotes_qualified_qra_only_after_packet_and_validation_gates():
    result = _result(
        event_id="event-qualified", asset_id="asset-qualified",
        component_id="tank-qualified", frequency=1e-3,
    )
    result.update(
        physical_validation_claim=True,
        provider_packet_case_count=1,
        qualified_provider_packet_case_count=1,
        provider_packet_promoted=True,
        provider_packet_missing_evidence_cases=[],
    )
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-qualified",)
    )
    assert merged["provider_packet_promoted"] is True
    assert merged["qualified_provider_packet_case_count"] == 1
    assert merged["qualified_facility_qra_available"] is True
    assert merged["complete_facility_qra_claim"] is True


def test_facility_ledger_reports_scenario_family_views_without_double_counting():
    result = _result(
        event_id="event-tank-family", asset_id="tank-asset-family",
        component_id="tank-01", frequency=1e-3,
    )
    result["risk_atoms"][0]["scenario_families"] = ["vessel_hole", "liquid_two_phase"]
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-01",)
    )
    assert set(merged["scenario_family_contributions"]) == {
        "vessel_hole", "liquid_two_phase"
    }
    assert merged["scenario_family_contributions"]["vessel_hole"][
        "annual_ir_low_high"
    ] == merged["scenario_family_contributions"]["liquid_two_phase"][
        "annual_ir_low_high"
    ]
    assert merged["semantics"]["scenario_family_contributions"]


def test_facility_ledger_rejects_duplicate_event_or_atom():
    first = _result(
        event_id="event-duplicate", asset_id="asset-1", component_id="component-1", frequency=1e-3
    )
    second = _result(
        event_id="event-duplicate", asset_id="asset-2", component_id="component-2", frequency=2e-3
    )
    with pytest.raises(FacilityLedgerError, match="duplicate event ID"):
        merge_facility_campaign_results([
            {"campaign_id": "first", "result": first},
            {"campaign_id": "second", "result": second},
        ])

    duplicate_atom = _result(
        event_id="event-one", asset_id="asset-1", component_id="component-1", frequency=1e-3
    )
    duplicate_atom["risk_atoms"].append(dict(duplicate_atom["risk_atoms"][0]))
    with pytest.raises(FacilityLedgerError, match="duplicate risk atom"):
        merge_facility_campaign_results([duplicate_atom])


def test_facility_ledger_withholds_total_for_missing_component_and_family():
    result = merge_facility_campaign_results(
        [_result(
            event_id="event-tank", asset_id="tank-asset", component_id="tank-01",
            frequency=1e-3, incomplete=True,
        )],
        expected_component_ids=("tank-01", "pipe-01"),
        scope_matrices=[{
            "rows": [{"family": "vessel_hole", "status": "EXECUTED"}],
        }],
        required_accident_families=("vessel_hole", "pipe_hole"),
    )

    assert result["status"] == "PARTIAL_FACILITY_SCOPE"
    assert result["total_facility_annual_ir_low_high"] is None
    assert result["known_contribution_annual_ir_low_high"]["receptor-a"][0] == pytest.approx(0.0007)
    assert result["conditional_diagnostic_facility_risk_available"] is True
    assert result["conditional_diagnostic_facility_annual_ir_low_high"] == result[
        "known_contribution_annual_ir_low_high"
    ]
    assert result["conditional_diagnostic_facility_coverage"]["uncomputed_case_count"] == 1
    assert result["conditional_diagnostic_facility_coverage"]["overlapping_case_uncomputed_count"] == 1
    assert result["conditional_diagnostic_facility_coverage"]["operator_limited_case_count"] == 0
    assert len(result["scope_matrix_digests"]) == 1
    assert "missing expected components: pipe-01" in result["blocking_reasons"]
    assert "accident family pipe_hole: missing scope matrix" in result["blocking_reasons"]
    assert result["component_statuses"]["tank-01"] == "PARTIAL"


def test_facility_ledger_accepts_not_applicable_accident_family():
    result = _result(
        event_id="event-without-pump", asset_id="tank-asset", component_id="tank-01",
        frequency=1e-3,
    )
    merged = merge_facility_campaign_results(
        [{"campaign_id": "tank-only", "result": result}],
        expected_component_ids=("tank-01",),
        scope_matrices=[{
            "rows": [{"family": "pump_hole", "status": "NOT_APPLICABLE"}],
        }],
        required_accident_families=("pump_hole",),
    )
    assert merged["accident_family_statuses"]["pump_hole"] == "NOT_APPLICABLE"
    assert merged["status"] == "FACILITY_SCOPE_EXECUTED"
    assert merged["facility_total_risk_available"] is True


def test_facility_ledger_withholds_total_when_event_case_accounting_is_missing():
    result = _result(
        event_id="event-without-case", asset_id="asset-1", component_id="tank-01",
        frequency=1e-3,
    )
    result["cases"] = []
    result["declared_scope_numerically_complete"] = True
    merged = merge_facility_campaign_results(
        [result],
        expected_component_ids=("tank-01",),
    )

    assert merged["status"] == "PARTIAL_FACILITY_SCOPE"
    assert merged["facility_total_risk_available"] is False
    accounting = next(iter(merged["event_accounting"].values()))
    assert accounting["unaccounted_event_count"] == 1
    assert any("events lack case or uncomputed-case accounting" in reason for reason in merged["blocking_reasons"])


def test_facility_ledger_rejects_malformed_case_accounting_rows():
    result = _result(
        event_id="event-case", asset_id="asset-case", component_id="tank-01",
        frequency=1e-3,
    )
    result["cases"] = [None]
    with pytest.raises(FacilityLedgerError, match=r"cases\[0\] must be an object"):
        merge_facility_campaign_results([result], expected_component_ids=("tank-01",))

    result = _result(
        event_id="event-case", asset_id="asset-case", component_id="tank-01",
        frequency=1e-3,
    )
    result["uncomputed_cases"] = [{"event_id": "event-not-generated", "status": "UNCOMPUTED"}]
    with pytest.raises(FacilityLedgerError, match=r"uncomputed_cases\[0\] references an unknown event"):
        merge_facility_campaign_results([result], expected_component_ids=("tank-01",))


def test_facility_ledger_withholds_total_when_component_coverage_row_is_missing():
    result = _result(
        event_id="event-no-coverage", asset_id="asset-no-coverage", component_id="tank-01",
        frequency=1e-3,
    )
    result.pop("coverage")
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-01",)
    )

    assert merged["facility_total_risk_available"] is False
    assert merged["component_statuses"]["tank-01"] == "MISSING_COVERAGE_LEDGER"
    assert "component tank-01: missing coverage ledger row" in merged["blocking_reasons"]


def test_facility_ledger_labels_explicit_component_exclusion_without_calling_it_partial():
    result = _result(
        event_id="event-excluded-interface", asset_id="asset-interface",
        component_id="tank-01", frequency=1e-3,
    )
    result["coverage"]["by_component"][0]["scope_status"] = "EXCLUDED"
    result["excluded_model_components"] = {"tank-01": "interface boundary has no accidental release mode"}
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-01",)
    )
    assert merged["component_statuses"]["tank-01"] == "EXCLUDED"
    assert any("excluded components remain" in reason for reason in merged["blocking_reasons"])


def test_facility_ledger_can_feed_frequency_uncertainty_without_physics_rerun():
    result = merge_facility_campaign_results(
        [_result(
            event_id="event-tank", asset_id="tank-asset", component_id="tank-01",
            frequency=1e-3,
        )],
        expected_component_ids=("tank-01",),
    )
    asset = result["events"][0]["asset_id"]
    uncertainty = literature_frequency_uncertainty(
        result,
        (
            LiteratureFrequencyScenario(
                id="shared-low",
                asset_quantiles={asset: "p05"},
                provenance="published test bounds",
            ),
            LiteratureFrequencyScenario(
                id="independent-low",
                event_quantiles={result["events"][0]["id"]: "p05"},
                provenance="published test bounds",
                correlation_assumption="independent_event_bounds",
            ),
        ),
    )
    assert uncertainty["fresh_physics_executed"] is False
    assert uncertainty["correlation_comparison_present"] is True
    assert all(
        row["total_facility_annual_ir_low_high"] is not None
        for row in uncertainty["scenarios"]
    )
    assert uncertainty["facility_credible_interval"] is False


def test_facility_assessment_combines_ledger_and_frequency_scenarios():
    result = _result(
        event_id="event-assessment", asset_id="asset-assessment", component_id="tank-01",
        frequency=1e-3,
    )
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=("tank-01",),
        frequency_scenarios=(
            LiteratureFrequencyScenario(
                id="published",
                asset_quantiles={"asset-assessment": "published"},
                provenance="test published rate",
            ),
        ),
    )

    assert assessment["schema_version"] == "prism.facility_assessment.v1"
    assert assessment["status"] == "FACILITY_SCOPE_EXECUTED"
    assert assessment["facility_total_risk_available"] is True
    assert assessment["provider_packet_promoted"] is False
    assert assessment["qualified_facility_qra_available"] is False
    assert assessment["conditional_diagnostic_facility_risk_available"] is True
    assert assessment["conditional_diagnostic_facility_annual_ir_low_high"] == assessment[
        "facility_risk_ledger"
    ]["known_contribution_annual_ir_low_high"]
    assert assessment["fresh_physics_executed"] is False
    assert assessment["frequency_uncertainty"]["fresh_physics_executed"] is False
    assert assessment["facility_risk_ledger"]["component_contributions"]["tank-01"]
    assert assessment["assessment_digest"]


def test_facility_assessment_reconciles_provider_qualification_coverage():
    result = _result(
        event_id="event-qualified-coverage",
        asset_id="asset-qualified-coverage",
        component_id="tank-qualified-coverage",
        frequency=1e-3,
    )
    result.update(
        physical_validation_claim=True,
        provider_packet_case_count=1,
        qualified_provider_packet_case_count=1,
        provider_packet_promoted=True,
        provider_packet_missing_evidence_cases=[],
    )
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=("tank-qualified-coverage",),
        provider_qualification_coverage={
            "status": "FULLY_MATCHED",
            "qualification_assessed": True,
            "qualification_status": "QUALIFIED_FULL_WORKLIST",
            "worklist_event_count": 1,
            "exact_match_count": 1,
            "qualified_provider_packet_count": 1,
            "unqualified_exact_match_count": 0,
        },
    )

    gate = assessment["provider_qualification_coverage"]
    assert gate["complete"] is True
    assert gate["ledger_qualified_provider_packet_case_count"] == 1
    assert assessment["qualified_facility_qra_available"] is True


def test_facility_assessment_withholds_provider_qualification_coverage_on_count_mismatch():
    result = _result(
        event_id="event-mismatched-coverage",
        asset_id="asset-mismatched-coverage",
        component_id="tank-mismatched-coverage",
        frequency=1e-3,
    )
    result.update(
        physical_validation_claim=True,
        provider_packet_case_count=1,
        qualified_provider_packet_case_count=1,
        provider_packet_promoted=True,
        provider_packet_missing_evidence_cases=[],
    )
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=("tank-mismatched-coverage",),
        provider_qualification_coverage={
            "status": "FULLY_MATCHED",
            "qualification_assessed": True,
            "qualification_status": "QUALIFIED_FULL_WORKLIST",
            "worklist_event_count": 2,
            "exact_match_count": 2,
            "qualified_provider_packet_count": 2,
            "unqualified_exact_match_count": 0,
        },
    )

    gate = assessment["provider_qualification_coverage"]
    assert gate["complete"] is False
    assert any("does not match" in reason for reason in gate["blocking_reasons"])
    assert assessment["qualified_facility_qra_available"] is False
    assert assessment["complete_facility_qra_claim"] is False
