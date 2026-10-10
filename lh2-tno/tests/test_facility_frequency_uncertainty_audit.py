import copy

from lh2_tno.facility_frequency_uncertainty_audit import (
    build_facility_frequency_uncertainty_audit,
)


def _inputs():
    campaign = {
        "facility_id": "facility-1",
        "campaign_digest": "campaign-digest",
        "events": [
            {
                "id": "event-1",
                "asset_id": "tank",
                "model_component_id": "tank",
                "profile": "LH2_VESSEL",
                "loc": "AREA_1%",
                "basis": "LH2_LITERATURE",
                "base_rate": 0.1,
                "rate_unit": "item^-1 year^-1",
                "exposure_multiplier": 1.0,
                "annual_frequency_per_year": 0.1,
                "statistic": "published_median",
                "marginal_p05_per_year": 0.05,
                "marginal_p95_per_year": 0.2,
                "source": "test-source",
                "source_sha256": "test-source-sha256",
                "catalogue_digest": "test-catalogue-digest",
                "release": {"mode": "hole", "hole_diameter_m": 0.01},
                "classification_basis": "test-classification",
                "limitations": [],
            }
        ],
        "known_contribution_annual_ir_low_high": {"worker": [0.05, 0.05]},
        "risk_atoms": [
            {
                "event_id": "event-1",
                "asset_id": "tank",
                "initiating_frequency_per_year": 0.1,
                "conditional_weight": 0.5,
                "receptor_harm_low_high": {"worker": [1.0, 1.0]},
                "expected_deaths_low_high": [1.0, 1.0],
                "scenario_families": ["vessel_hole"],
            }
        ],
        "annual_conditions": [],
        "uncomputed_cases": [],
        "declared_scope_numerically_complete": False,
        "total_facility_annual_ir_low_high": None,
        "provider_packet_promoted": False,
        "qualified_provider_packet_case_count": 0,
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    scenarios = {
        "scenarios": [
            {
                "id": "central",
                "asset_quantiles": {"tank": "published"},
                "event_quantiles": {},
                "provenance": "published rate; no frequency inference",
                "correlation_assumption": "within_asset_shared_quantile",
            },
            {
                "id": "low",
                "asset_quantiles": {"tank": "p05"},
                "event_quantiles": {},
                "provenance": "published p05; no frequency inference",
                "correlation_assumption": "within_asset_shared_quantile",
            },
        ],
        "frequency_inference_performed": False,
        "facility_credible_interval": False,
    }
    return campaign, scenarios


def _stored(campaign, scenarios):
    from lh2_tno.uncertainty import LiteratureFrequencyScenario, literature_frequency_uncertainty

    parsed = tuple(LiteratureFrequencyScenario.model_validate(row) for row in scenarios["scenarios"])
    return literature_frequency_uncertainty(campaign, parsed)


def test_frequency_uncertainty_audit_closes_when_saved_rows_match():
    campaign, scenarios = _inputs()
    result = build_facility_frequency_uncertainty_audit(campaign, scenarios, _stored(campaign, scenarios))
    assert result["status"] == "FACILITY_FREQUENCY_UNCERTAINTY_CLOSED_DIAGNOSTIC"
    assert result["scenario_count"] == 2
    assert result["mismatch_count"] == 0
    assert result["frequency_inference_performed"] is False


def test_frequency_uncertainty_audit_detects_stale_ir():
    campaign, scenarios = _inputs()
    stored = _stored(campaign, scenarios)
    stored = copy.deepcopy(stored)
    stored["scenarios"][0]["conditional_diagnostic_facility_annual_ir_low_high"]["worker"][1] = 0.2
    result = build_facility_frequency_uncertainty_audit(campaign, scenarios, stored)
    assert result["status"] == "BLOCKED_FACILITY_FREQUENCY_UNCERTAINTY_AUDIT"
    assert result["mismatch_count"] > 0


def test_frequency_uncertainty_audit_rejects_inference_flag():
    campaign, scenarios = _inputs()
    scenarios = copy.deepcopy(scenarios)
    scenarios["frequency_inference_performed"] = True
    result = build_facility_frequency_uncertainty_audit(campaign, scenarios, _stored(campaign, scenarios))
    assert result["status"] == "BLOCKED_FACILITY_FREQUENCY_UNCERTAINTY_AUDIT"
    assert any("frequency inference" in reason for reason in result["blocking_reasons"])
