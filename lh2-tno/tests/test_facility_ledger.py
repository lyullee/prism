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
    port_ids=None,
    operating_mode: str | None = None,
):
    atom = {
        "event_id": event_id,
        "asset_id": asset_id,
        "frequency_port_ids": port_ids,
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
    if operating_mode is not None:
        atom["operating_mode"] = operating_mode
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
            **({"port_ids": port_ids} if port_ids is not None else {}),
        }],
        "cases": [{"event_id": event_id, "status": "EXECUTED", "elapsed_ms": 5.0,
                   "frequency_port_ids": port_ids}],
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
    assert result["not_numerically_executed_case_count"] == 0
    assert result["qualified_evidence_withheld_case_count"] == 0
    assert result["numerically_executed_case_count"] == 2
    assert result["risk_atoms_digest"]
    assert result["component_contributions"]["tank-01"]["annual_ir_low_high"]["receptor-a"] == pytest.approx(
        [0.0007, 0.0008]
    )
    assert result["component_contributions"]["pipe-01"]["annual_ir_low_high"]["receptor-a"] == pytest.approx(
        [0.0007, 0.0008]
    )
    assert result["component_contributions"]["tank-01"]["frequency_is_not_reallocated"] is True
    ranking = result["component_risk_ranking"]
    assert ranking["status"] == "AVAILABLE"
    assert ranking["component_count"] == 2
    assert [row["component_id"] for row in ranking["rows"]] == ["pipe-01", "tank-01"]
    assert ranking["rows"][0]["peak_annual_ir_low_high"] == pytest.approx(
        [0.0007, 0.0008]
    )
    assert ranking["rows"][0]["peak_receptor_id_low_high"] == ["receptor-a", "receptor-a"]
    assert ranking["frequency_reallocation_performed"] is False
    assert ranking["facility_ir_fn_promotion"] is False
    assert result["scenario_family_contributions"] == {}
    assert result["population_accounting"]["status"] == "NOT_RECORDED_IN_INPUT"
    assert result["release_termination_inventory_ledger"]["schema_version"] == (
        "prism.release_termination_inventory_ledger.v1"
    )
    assert result["release_termination_inventory_ledger"]["summary"]["case_count"] == 2
    assert result["frequency_port_binding"]["status"] == "ALIGNED"
    assert result["frequency_port_binding"]["mismatch_count"] == 0
    assert result["frequency_port_binding"]["frequency_inference_allowed"] is False
    assert result["frequency_port_binding"]["facility_qra_allowed"] is False
    assert result["scenario_branch_accounting"]["status"] == "EXPLICIT_BRANCH_ACCOUNTING"
    assert result["scenario_branch_accounting"]["cross_product_count"] == 1
    assert result["scenario_branch_accounting"]["release_branches"]["release-1"][
        "risk_atom_count"
    ] == 2
    assert result["scenario_branch_accounting"]["release_branches"]["release-1"][
        "weighted_frequency_per_year"
    ] == pytest.approx(0.002)
    assert result["scenario_branch_accounting"]["ignition_branches"]["direct_fire"][
        "event_count"
    ] == 2
    assert result["conditional_diagnostic_facility_coverage"]["population_status"] == (
        "NOT_RECORDED_IN_INPUT"
    )
    assert result["conditional_diagnostic_facility_expected_death_fn_diagnostics"] == {
        "status": "CURVE_AVAILABLE",
        "endpoint_level_count_low_high": [1, 1],
        "max_expected_deaths_low_high": [1.2, 1.4],
        "curve_uses_threshold": "N >= 1 expected deaths",
    }


def test_facility_ledger_keeps_port_trace_and_withholds_mismatch():
    aligned = merge_facility_campaign_results(
        [{
            "campaign_id": "port-campaign",
            "result": _result(
                event_id="event-port", asset_id="port-asset", component_id="port-01",
                frequency=1e-3, port_ids=["port-01-out"],
            ),
        }],
        expected_component_ids=("port-01",),
    )
    assert aligned["frequency_port_binding"]["status"] == "ALIGNED"
    assert aligned["frequency_port_binding"]["port_scoped_event_count"] == 1
    assert aligned["frequency_port_binding"]["facility_qra_allowed"] is True
    assert aligned["cases"][0]["frequency_port_ids"] == ["port-01-out"]
    assert aligned["risk_atoms"][0]["frequency_port_ids"] == ["port-01-out"]

    mismatched = _result(
        event_id="event-port-bad", asset_id="port-asset-bad", component_id="port-01",
        frequency=1e-3, port_ids=["port-01-out"],
    )
    mismatched["risk_atoms"][0]["frequency_port_ids"] = ["other-out"]
    withheld = merge_facility_campaign_results(
        [{"campaign_id": "port-mismatch", "result": mismatched}],
        expected_component_ids=("port-01",),
    )
    assert withheld["frequency_port_binding"]["status"] == "PORT_BINDING_MISMATCH"
    assert withheld["frequency_port_binding"]["risk_atom_port_binding_mismatch_count"] == 1
    assert withheld["facility_total_risk_available"] is False


def test_facility_ledger_explains_zero_harm_fn_curve_without_promoting_zero_to_missing():
    result = _result(
        event_id="event-zero-harm",
        asset_id="asset-zero-harm",
        component_id="tank-zero-harm",
        frequency=1e-3,
    )
    result["risk_atoms"][0]["receptor_harm_low_high"] = {
        "receptor-a": [0.0, 0.0],
        "receptor-b": [0.0, 0.0],
    }
    result["risk_atoms"][0]["expected_deaths_low_high"] = [0.0, 0.0]
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-zero-harm",)
    )

    assert merged["conditional_diagnostic_facility_risk_available"] is True
    assert merged["conditional_diagnostic_facility_expected_death_fn_low_high"] == [
        {"expected_deaths": [], "cumulative_frequency_per_year": []},
        {"expected_deaths": [], "cumulative_frequency_per_year": []},
    ]
    assert merged["conditional_diagnostic_facility_expected_death_fn_diagnostics"] == {
        "status": "ZERO_EXPECTED_DEATH_AT_DECLARED_RECEPTORS",
        "endpoint_level_count_low_high": [0, 0],
        "max_expected_deaths_low_high": [0.0, 0.0],
        "curve_uses_threshold": "N >= 1 expected deaths",
    }


def test_facility_ledger_preserves_annual_condition_population_provenance():
    result = _result(
        event_id="event-population-provenance",
        asset_id="asset-population-provenance",
        component_id="tank-population-provenance",
        frequency=1e-3,
    )
    result["annual_conditions"] = [{
        "id": "weather-1",
        "annual_probability": 1.0,
        "weather": {"wind_speed_m_s": 3.0, "stability": "D"},
        "population": [
            {"receptor_id": "receptor-a", "persons": 12.0, "presence_probability": 0.5},
            {"receptor_id": "receptor-b", "persons": 4.0, "presence_probability": 1.0},
        ],
        "provenance": "test synthetic condition",
    }]
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-population-provenance",)
    )

    assert merged["annual_condition_count"] == 1
    assert merged["population_accounting"]["status"] == "EXPLICIT_CONDITION_POPULATION"
    assert merged["population_accounting"]["population_row_count"] == 2
    assert merged["population_accounting"]["population_provenance"] == {
        "weather-1": "test synthetic condition"
    }
    assert merged["annual_conditions"][0]["population"][0]["persons"] == 12.0


def test_facility_ledger_marks_condition_population_receptor_mismatch():
    result = _result(
        event_id="event-population-mismatch",
        asset_id="asset-population-mismatch",
        component_id="tank-population-mismatch",
        frequency=1e-3,
    )
    result["annual_conditions"] = [{
        "id": "weather-1",
        "population": [{"receptor_id": "other-receptor", "persons": 1.0}],
    }]
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-population-mismatch",)
    )

    assert merged["population_accounting"]["status"] == "RECEPTOR_POPULATION_MISMATCH"
    assert merged["population_accounting"]["mismatched_receptor_ids"]["weather-1"] == {
        "expected": ["receptor-a", "receptor-b"],
        "observed": ["other-receptor"],
    }


def test_facility_assessment_derives_fn_diagnostics_for_legacy_saved_ledger():
    result = _result(
        event_id="event-legacy-fn-diagnostics",
        asset_id="asset-legacy-fn-diagnostics",
        component_id="tank-legacy-fn-diagnostics",
        frequency=1e-3,
    )
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-legacy-fn-diagnostics",)
    )
    merged["cases"][0]["stage_elapsed_ms"] = {"source": 4.0}
    merged["timing"].pop("stage_elapsed_ms", None)
    merged.pop("conditional_diagnostic_facility_expected_death_fn_diagnostics")
    assessment = build_facility_assessment([merged])

    assert assessment[
        "conditional_diagnostic_facility_expected_death_fn_diagnostics"
    ]["status"] == "CURVE_AVAILABLE"
    assert assessment["scenario_branch_accounting"]["status"] == (
        "EXPLICIT_BRANCH_ACCOUNTING"
    )
    merged.pop("release_termination_inventory_ledger")
    assessment = build_facility_assessment([merged])
    assert assessment["release_termination_inventory_ledger"]["schema_version"] == (
        "prism.release_termination_inventory_ledger.v1"
    )
    assert assessment["release_termination_inventory_ledger"]["summary"]["case_count"] == 1
    assert assessment["timing"]["stage_elapsed_ms"]["source"]["p95_ms"] == pytest.approx(4.0)


def test_facility_ledger_exposes_component_case_accounting_and_gate_categories():
    result = _result(
        event_id="event-component-ledger",
        asset_id="asset-component-ledger",
        component_id="pipe-01",
        frequency=1e-3,
        incomplete=True,
    )
    result["cases"][0]["status"] = "EXECUTED_OPERATOR_LIMITED"
    result["cases"][0]["provider_packet_identity"] = {"component_id": "pipe-01"}
    result["uncomputed_cases"][0]["status"] = "EXECUTED_OPERATOR_LIMITED"
    result["uncomputed_cases"][0]["provider_packet_identity"] = {"component_id": "pipe-01"}
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("pipe-01", "tank-01")
    )

    coverage = merged["component_coverage"]["pipe-01"]
    assert merged["component_coverage_schema"] == "prism.component_coverage.v1"
    assert coverage["event_count"] == 1
    assert coverage["conditional_case_count"] == 1
    assert coverage["conditional_executed_case_count"] == 1
    assert coverage["conditional_uncomputed_case_count"] == 0
    assert coverage["strict_uncomputed_case_count"] == 1
    assert coverage["operator_limited_case_count"] == 1
    assert coverage["not_numerically_executed_case_count"] == 0
    assert coverage["qualified_evidence_withheld_case_count"] == 1
    assert coverage["numerically_executed_case_count"] == 1
    assert coverage["strict_gate_categories"] == [
        "MISSING_PROVIDER_CASES", "OPERATOR_LIMITED_INPUT"
    ]
    assert merged["component_contributions"]["pipe-01"]["coverage"] == coverage

    missing = merged["component_coverage"]["tank-01"]
    assert missing["status"] == "MISSING_COVERAGE_LEDGER"
    assert missing["conditional_case_count"] == 0
    assert missing["strict_gate_categories"] == ["FAMILY_SCOPE_PARTIAL"]


def test_facility_ledger_assigns_legacy_case_rows_from_event_component():
    result = _result(
        event_id="event-legacy-component",
        asset_id="asset-legacy-component",
        component_id="tank-legacy",
        frequency=1e-3,
    )
    result["cases"][0].pop("provider_packet_identity", None)
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-legacy",)
    )
    coverage = merged["conditional_diagnostic_facility_coverage"][
        "component_case_accounting"
    ]["tank-legacy"]
    assert coverage["conditional_executed_case_count"] == 1
    assert coverage["event_ids"] == ["event-legacy-component"]


def test_facility_ledger_promotes_qualified_qra_only_after_packet_and_validation_gates():
    result = _result(
        event_id="event-qualified", asset_id="asset-qualified",
        component_id="tank-qualified", frequency=1e-3,
        port_ids=["tank-qualified-accident-out"],
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
    assert result["conditional_diagnostic_facility_coverage"]["strict_uncomputed_case_count"] == 1
    assert result["conditional_diagnostic_facility_coverage"]["conditional_case_count"] == 1
    assert result["conditional_diagnostic_facility_coverage"]["conditional_executed_case_count"] == 1
    assert result["conditional_diagnostic_facility_coverage"]["conditional_uncomputed_case_count"] == 0
    assert result["conditional_diagnostic_facility_coverage"]["overlapping_case_uncomputed_count"] == 1
    assert result["conditional_diagnostic_facility_coverage"]["operator_limited_case_count"] == 0
    assert len(result["scope_matrix_digests"]) == 1
    assert "missing expected components: pipe-01" in result["blocking_reasons"]
    assert "accident family pipe_hole: missing scope matrix" in result["blocking_reasons"]
    assert result["component_statuses"]["tank-01"] == "PARTIAL"


def test_facility_ledger_keeps_weather_and_release_branches_as_distinct_cases():
    result = _result(
        event_id="event-multi-case", asset_id="asset-multi-case",
        component_id="tank-multi-case", frequency=1e-3,
    )
    second = dict(result["cases"][0])
    second.update({"annual_condition_id": "weather-2", "release_branch_id": "release-2"})
    result["cases"].append(second)
    second_missing = dict(second)
    second_missing["status"] = "UNCOMPUTED"
    result["uncomputed_cases"].append(second_missing)
    result["declared_scope_numerically_complete"] = False
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-multi-case",)
    )

    coverage = merged["conditional_diagnostic_facility_coverage"]
    assert coverage["case_count"] == 2
    assert coverage["conditional_case_count"] == 2
    assert coverage["conditional_executed_case_count"] == 2
    assert coverage["conditional_uncomputed_case_count"] == 0
    assert coverage["strict_uncomputed_case_count"] == 1
    assert coverage["overlapping_case_uncomputed_count"] == 1


def test_facility_ledger_preserves_weather_and_termination_branch_metadata():
    result = _result(
        event_id="event-branches", asset_id="asset-branches", component_id="tank-branches",
        frequency=1e-3,
    )
    result["annual_conditions"] = [{
        "id": "weather-1",
        "annual_probability": 0.7,
        "weather": {"wind_speed_m_per_s": 3.0, "stability_class": "D"},
        "provenance": "literature-weather-bin",
    }]
    result["risk_atoms"][0]["provider_packet_identity"] = {
        "termination_bases": ["explicit_provider_termination", "model_pressure_equalization"],
    }
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-branches",)
    )

    branches = merged["scenario_branch_accounting"]
    assert branches["status"] == "EXPLICIT_BRANCH_ACCOUNTING"
    assert branches["cross_product_count"] == 1
    assert branches["annual_conditions"]["weather-1"]["annual_probability"] == pytest.approx(0.7)
    assert branches["annual_conditions"]["weather-1"]["weather"]["wind_speed_m_per_s"] == pytest.approx(3.0)
    assert branches["release_branches"]["release-1"]["termination_basis_counts"] == {
        "explicit_provider_termination": 1,
        "model_pressure_equalization": 1,
    }
    assert branches["release_branches"]["release-1"]["weighted_frequency_per_year"] == pytest.approx(1e-3)
    assert branches["ignition_branches"]["direct_fire"]["positive_harm_atom_count"] == 1


def test_facility_ledger_preserves_operating_modes_in_each_branch_view():
    merged = merge_facility_campaign_results(
        [
            {
                "campaign_id": "receiving-campaign",
                "result": _result(
                    event_id="event-receiving",
                    asset_id="asset-receiving",
                    component_id="tank-mode",
                    frequency=1e-3,
                    operating_mode="receiving",
                ),
            },
            {
                "campaign_id": "supply-campaign",
                "result": _result(
                    event_id="event-supply",
                    asset_id="asset-supply",
                    component_id="tank-mode",
                    frequency=2e-3,
                    operating_mode="supply",
                ),
            },
        ],
        expected_component_ids=("tank-mode",),
    )

    branches = merged["scenario_branch_accounting"]
    assert branches["annual_conditions"]["weather-1"]["operating_modes"] == [
        "receiving",
        "supply",
    ]
    assert branches["release_branches"]["release-1"]["operating_modes"] == [
        "receiving",
        "supply",
    ]
    assert branches["ignition_branches"]["direct_fire"]["operating_modes"] == [
        "receiving",
        "supply",
    ]
    assert branches["release_branches"]["release-1"][
        "weighted_frequency_per_year"
    ] == pytest.approx(3e-3)


def test_facility_ledger_carries_release_duration_isolation_and_inventory_rows():
    result = _result(
        event_id="event-release-ledger", asset_id="asset-release-ledger",
        component_id="tank-release-ledger", frequency=1e-3,
    )
    result["cases"][0].update({
        "termination": {
            "basis": "reviewed_isolation_success",
            "time_s": 0.25,
            "provenance": "provider valve closure ledger",
        },
        "mass_ledger": {"released_kg": 0.2, "end_to_end_residual_kg": 0.0},
        "provider_packet_identity": {
            "event_id": "event-release-ledger",
            "component_id": "tank-release-ledger",
            "provider_result_digests": ["b" * 64],
            "termination_bases": ["reviewed_isolation_success"],
            "duration_s": [0.25],
            "available_mass_kg": [10.0],
            "cumulative_mass_out_kg": [0.2],
        },
    })
    result["risk_atoms"][0]["provider_packet_identity"] = result["cases"][0][
        "provider_packet_identity"
    ]
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-release-ledger",)
    )

    release = merged["release_termination_inventory_ledger"]
    assert release["summary"]["complete_row_count"] == 1
    assert release["summary"]["termination_basis_counts"] == {
        "reviewed_isolation_success": 1
    }
    row = release["rows"][0]
    assert row["isolation_status"] == "provider_declared_isolation_success"
    assert row["provider"]["duration_s"] == [0.25]
    assert row["provider"]["residual_mass_kg"] == [9.8]


def test_facility_ledger_preserves_stage_timing_without_one_hz_claim():
    result = _result(
        event_id="event-stage-timing", asset_id="asset-stage-timing",
        component_id="tank-stage-timing", frequency=1e-3,
    )
    result["cases"][0]["stage_elapsed_ms"] = {
        "provider_release": 12.0,
        "slabx_consequence": 8.0,
        "harm_aggregation": 2.0,
    }
    merged = merge_facility_campaign_results(
        [result], expected_component_ids=("tank-stage-timing",)
    )

    stage = merged["timing"]["stage_elapsed_ms"]
    assert stage["provider_release"]["sample_count"] == 1
    assert stage["provider_release"]["p95_ms"] == pytest.approx(12.0)
    assert stage["slabx_consequence"]["sum_ms"] == pytest.approx(8.0)
    assert merged["semantics"]["timing"].endswith("1 Hz claim")
    assert merged["conditional_diagnostic_facility_coverage"]["stage_timing"] == stage


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
    assert assessment["frequency_port_binding"]["status"] == "ALIGNED"
    assert assessment["frequency_port_binding"] == assessment["facility_risk_ledger"]["frequency_port_binding"]
    assert assessment["facility_risk_ledger"]["component_contributions"]["tank-01"]
    assert assessment["assessment_digest"]


def test_facility_assessment_preserves_an_existing_facility_ledger():
    first = _result(
        event_id="event-existing-ledger-a",
        asset_id="asset-existing-ledger-a",
        component_id="tank-existing-ledger",
        frequency=1e-3,
    )
    second = _result(
        event_id="event-existing-ledger-b",
        asset_id="asset-existing-ledger-b",
        component_id="pipe-existing-ledger",
        frequency=2e-3,
    )
    ledger = merge_facility_campaign_results(
        [
            {"campaign_id": "tank-campaign", "result": first},
            {"campaign_id": "pipe-campaign", "result": second},
        ],
        expected_component_ids=("tank-existing-ledger", "pipe-existing-ledger"),
    )

    assessment = build_facility_assessment(
        [ledger],
        expected_component_ids=("tank-existing-ledger", "pipe-existing-ledger"),
    )

    assert assessment["facility_risk_ledger"]["campaign_ids"] == ledger["campaign_ids"]
    assert assessment["facility_risk_ledger"]["component_statuses"] == ledger[
        "component_statuses"
    ]
    assert assessment["conditional_diagnostic_facility_coverage"][
        "component_status_counts"
    ] == {"EXECUTED": 2}


def test_facility_assessment_reconciles_provider_qualification_coverage():
    result = _result(
        event_id="event-qualified-coverage",
        asset_id="asset-qualified-coverage",
        component_id="tank-qualified-coverage",
        frequency=1e-3,
        port_ids=["tank-qualified-coverage-accident-out"],
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
        facility_case_packet_coverage={
            "schema": "prism.facility_case_provider_coverage.v1",
            "status": "QUALIFIED_FULL_CASE_COVERAGE",
            "case_request_count": 1,
            "qualified_provider_event_count": 1,
            "qualified_provider_case_count": 1,
            "provider_evidence_row_count": 1,
            "promotion_policy": {
                "frequency_is_not_assigned": True,
                "physical_validation_claim": False,
                "facility_ir_fn_promotion": (
                    "requires this full case gate plus independent scope and validation gates"
                ),
            },
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


def test_facility_assessment_requires_case_coverage_report_for_provider_cases():
    result = _result(
        event_id="event-case-coverage-required",
        asset_id="asset-case-coverage-required",
        component_id="tank-case-coverage-required",
        frequency=1e-3,
    )
    result.update(
        provider_packet_case_count=1,
        qualified_provider_packet_case_count=1,
        provider_packet_promoted=True,
        provider_packet_missing_evidence_cases=[],
    )
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=("tank-case-coverage-required",),
    )

    gate = assessment["facility_case_packet_coverage"]
    assert gate["coverage_status"] == "MISSING_REPORT"
    assert gate["complete"] is False
    assert assessment["qualified_facility_qra_available"] is False


def test_facility_assessment_reconciles_case_packet_coverage_and_withholds_qra():
    result = _result(
        event_id="event-case-coverage",
        asset_id="asset-case-coverage",
        component_id="tank-case-coverage",
        frequency=1e-3,
    )
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=("tank-case-coverage",),
        facility_case_packet_coverage={
            "schema": "prism.facility_case_provider_coverage.v1",
            "status": "NO_CASE_MATCH",
            "case_request_count": 1,
            "qualified_provider_event_count": 0,
            "qualified_provider_case_count": 0,
            "provider_evidence_row_count": 0,
            "status_counts": {"MISSING_QUALIFIED_PROVIDER_EVIDENCE": 1},
            "promotion_policy": {
                "frequency_is_not_assigned": True,
                "physical_validation_claim": False,
                "facility_ir_fn_promotion": (
                    "requires this full case gate plus independent scope and validation gates"
                ),
            },
        },
    )
    gate = assessment["facility_case_packet_coverage"]
    assert gate["complete"] is False
    assert any("not full qualified coverage" in reason for reason in gate["blocking_reasons"])
    assert assessment["facility_case_packet_coverage_complete"] is False
    assert assessment["qualified_facility_qra_available"] is False
    assert assessment["complete_facility_qra_claim"] is False
    assert assessment["strict_release_boundary"] == assessment["facility_risk_ledger"][
        "strict_release_boundary"
    ]


def test_facility_assessment_accepts_exact_full_case_packet_coverage():
    result = _result(
        event_id="event-case-coverage-full",
        asset_id="asset-case-coverage-full",
        component_id="tank-case-coverage-full",
        frequency=1e-3,
        port_ids=["tank-case-coverage-full-accident-out"],
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
        expected_component_ids=("tank-case-coverage-full",),
        provider_qualification_coverage={
            "status": "FULLY_MATCHED",
            "qualification_assessed": True,
            "qualification_status": "QUALIFIED_FULL_WORKLIST",
            "worklist_event_count": 1,
            "exact_match_count": 1,
            "qualified_provider_packet_count": 1,
            "unqualified_exact_match_count": 0,
        },
        facility_case_packet_coverage={
            "schema": "prism.facility_case_provider_coverage.v1",
            "status": "QUALIFIED_FULL_CASE_COVERAGE",
            "case_request_count": 1,
            "qualified_provider_event_count": 1,
            "qualified_provider_case_count": 1,
            "provider_evidence_row_count": 1,
            "status_counts": {"QUALIFIED_CASE_COVERAGE": 1},
            "promotion_policy": {
                "frequency_is_not_assigned": True,
                "physical_validation_claim": False,
                "facility_ir_fn_promotion": (
                    "requires this full case gate plus independent scope and validation gates"
                ),
            },
        },
    )
    assert assessment["facility_case_packet_coverage_complete"] is True
    assert assessment["qualified_facility_qra_available"] is True
