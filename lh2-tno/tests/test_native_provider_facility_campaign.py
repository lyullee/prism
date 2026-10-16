from __future__ import annotations

from scripts.run_native_provider_facility_campaign import _facility_frequency_scenarios


def test_multi_equipment_frequency_scenarios_keep_missing_bounds_fixed() -> None:
    events = [
        {"asset_id": "pump", "marginal_p05_per_year": None, "marginal_p95_per_year": None},
        {"asset_id": "valve", "marginal_p05_per_year": 1.0e-5, "marginal_p95_per_year": 1.0e-3},
        {"asset_id": "valve", "marginal_p05_per_year": 2.0e-6, "marginal_p95_per_year": 2.0e-4},
    ]

    scenarios = _facility_frequency_scenarios(events)

    assert [scenario.id for scenario in scenarios] == [
        "native-provider-facility-published",
        "native-provider-facility-p05",
        "native-provider-facility-p95",
    ]
    assert all(scenario.asset_quantiles["pump"] == "fixed" for scenario in scenarios)
    assert scenarios[0].asset_quantiles["valve"] == "published"
    assert scenarios[1].asset_quantiles["valve"] == "p05"
    assert scenarios[2].asset_quantiles["valve"] == "p95"


def test_multi_equipment_frequency_scenarios_use_fixed_when_no_bounds_exist() -> None:
    scenarios = _facility_frequency_scenarios([
        {"asset_id": "pump", "marginal_p05_per_year": None, "marginal_p95_per_year": None},
    ])

    assert len(scenarios) == 1
    assert scenarios[0].id == "native-provider-facility-fixed"
    assert scenarios[0].asset_quantiles == {"pump": "fixed"}
