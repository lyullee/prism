"""Regression tests for the digitized GH2 literature benchmark package."""

import math

import pytest

import literature_benchmarks as B


SUMMARY = B.metric_summary()


def test_reference_row_counts_are_stable():
    summary = SUMMARY
    metrics = summary["metrics_by_qoi"]
    assert summary["n_rows"] == 516
    assert metrics["han_lfl_distance_m"]["n"] == 12
    assert metrics["ruggles_inverse_centerline_mass_fraction"]["n"] == 32
    assert metrics["ruggles_half_width_mm"]["n"] == 33
    assert metrics["proust_mass_flow_g_s"]["n"] == 13
    assert metrics["proust_mass_flow_line_loss_g_s"]["n"] == 13
    assert metrics["proust_mass_flow_cd061_sensitivity_g_s"]["n"] == 13
    for qoi in B.PROUST_MODEL_QOIS:
        assert metrics[qoi]["n"] == 64
    assert metrics["ekoto_source_mass_flow_kg_s"]["n"] == 2
    for qoi in B.EKOTO_MODEL_QOIS:
        assert metrics[qoi]["n"] == 2
    for qoi in B.ROYLE_MODEL_QOIS:
        assert metrics[qoi]["n"] == 4


def test_dispersion_benchmarks_preserve_mixed_result():
    summary = SUMMARY
    result = summary["screening_by_qoi"]
    metrics = summary["metrics_by_qoi"]
    assert result["han_lfl_distance_m"]["passes_all"]
    assert result["ruggles_half_width_mm"]["passes_all"]
    assert not result[
        "ruggles_inverse_centerline_mass_fraction"
    ]["passes_all"]
    assert math.isclose(
        metrics["ruggles_half_width_mm"]["normalized_rmse"],
        0.034706879486657474,
        rel_tol=1e-12,
    )
    assert metrics[
        "ruggles_inverse_centerline_mass_fraction"
    ]["normalized_mean_bias"] > 0.30


def test_measured_flow_separates_flame_model_from_source_term():
    summary = SUMMARY
    result = summary["screening_by_qoi"]
    metrics = summary["metrics_by_qoi"]
    assert not result["proust_mass_flow_g_s"]["passes_all"]
    assert result[
        "proust_flame_delichatsios_measured_flow"
    ]["passes_all"]
    assert result[
        "proust_flame_molkov_fit_measured_flow"
    ]["passes_all"]
    assert not result[
        "proust_flame_molkov_conservative_measured_flow"
    ]["passes_all"]
    assert metrics[
        "proust_flame_delichatsios_measured_flow"
    ]["model_envelope_coverage"] == 1.0


def test_combined_fit_is_flagged_as_error_cancellation_not_validation():
    summary = SUMMARY
    metrics = summary["metrics_by_qoi"]
    combined = metrics["proust_flame_molkov_fit_predicted_flow"]
    isolated = metrics["proust_flame_molkov_fit_measured_flow"]
    source = metrics["proust_mass_flow_g_s"]
    assert combined["normalized_rmse"] < isolated["normalized_rmse"]
    assert source["normalized_mean_bias"] > 0.80
    assert any(
        "cancellation" in warning for warning in summary["interpretation"]
    )


def test_reported_feed_line_does_not_close_proust_source_residual():
    summary = SUMMARY
    metrics = summary["metrics_by_qoi"]
    direct = metrics["proust_mass_flow_g_s"]
    with_line = metrics["proust_mass_flow_line_loss_g_s"]
    assert with_line["normalized_rmse"] < direct["normalized_rmse"]
    assert with_line["normalized_mean_bias"] > 0.70
    assert with_line["normalized_rmse"] > 0.90
    assert any(
        "pipe-loss explanation is rejected" in warning
        for warning in summary["interpretation"]
    )


def test_cd061_is_a_passing_sensitivity_not_apparatus_validation():
    metrics = SUMMARY["metrics_by_qoi"]
    decisions = SUMMARY["screening_by_qoi"]
    qoi = "proust_mass_flow_cd061_sensitivity_g_s"
    assert decisions[qoi]["passes_all"]
    assert metrics[qoi]["normalized_mean_bias"] == pytest.approx(
        0.09881496011995677, rel=1e-10
    )
    assert any(
        "not apparatus validation" in warning
        for warning in SUMMARY["interpretation"]
    )


def test_pressure_resolved_residual_rejects_a_single_physical_cd_story():
    residual = SUMMARY["proust_source_residual"]
    assert residual["effective_cd_direct_min"] < 0.49
    assert residual["effective_cd_direct_max"] > 0.65
    assert residual["reported_line_residual_explained_fraction"] < 0.05
    assert residual["required_equivalent_minor_loss_k_min"] > 300
    assert residual["required_equivalent_minor_loss_k_max"] > 700
    assert residual["fitted_constant_cd_same_series"] == pytest.approx(
        0.532106, rel=2e-6
    )


def test_ekoto_extends_measured_flow_flame_component_to_20p9_mm():
    metrics = SUMMARY["metrics_by_qoi"]
    decisions = SUMMARY["screening_by_qoi"]
    assert decisions["ekoto_flame_delichatsios_measured_flow"]["passes_all"]
    assert decisions["ekoto_flame_molkov_fit_measured_flow"]["passes_all"]
    assert not decisions[
        "ekoto_flame_molkov_conservative_measured_flow"
    ]["passes_all"]
    assert metrics[
        "ekoto_flame_delichatsios_measured_flow"
    ]["normalized_rmse"] == pytest.approx(0.05587577845, rel=1e-9)


def test_royle_is_retained_as_source_sensitivity_not_full_chain_validation():
    decisions = SUMMARY["screening_by_qoi"]
    assert not decisions[
        "royle_unattached_flame_delichatsios_cd1_assumed_288k"
    ]["passes_all"]
    assert decisions[
        "royle_unattached_flame_delichatsios_cd061_assumed_288k"
    ]["passes_all"]
    assert any(
        "not full-chain validation" in warning
        for warning in SUMMARY["interpretation"]
    )
    royle_rows = [
        row for row in B.observations() if row.test_id == "ROYLE-d6.4"
    ]
    assert royle_rows
    assert all("12 mm" in row.condition_note for row in royle_rows)
