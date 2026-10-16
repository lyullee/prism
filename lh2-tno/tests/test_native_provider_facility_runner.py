from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "run_native_dynamic_pipe_gas_facility_frequency_case.py"
)
_SPEC = importlib.util.spec_from_file_location("native_provider_facility_runner", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_published_bounds_create_three_frequency_scenarios() -> None:
    scenarios = _MODULE._default_scenarios(
        "asset-1",
        [
            {
                "asset_id": "asset-1",
                "marginal_p05_per_year": 1.0e-6,
                "marginal_p95_per_year": 1.0e-4,
            }
        ],
    )
    assert [scenario.asset_quantiles["asset-1"] for scenario in scenarios] == [
        "published",
        "p05",
        "p95",
    ]


def test_unbounded_catalogue_asset_is_explicitly_fixed() -> None:
    scenarios = _MODULE._default_scenarios(
        "pump-asset",
        [
            {
                "asset_id": "pump-asset",
                "marginal_p05_per_year": None,
                "marginal_p95_per_year": None,
            }
        ],
    )
    assert len(scenarios) == 1
    assert scenarios[0].asset_quantiles == {"pump-asset": "fixed"}
    assert "no complete published p05/p95 bounds" in scenarios[0].provenance


def test_liquid_provider_defaults_preserve_pool_compatibility_boundary() -> None:
    packet_path = (
        Path(__file__).parents[1]
        / "results"
        / "20261016"
        / "native_mapped_pump_actual_smoke"
        / "resolved_release.json"
    )
    if not packet_path.exists():
        return
    packet = _MODULE.load_provider_release(packet_path)
    defaults = _MODULE._request_defaults({}, packet)
    assert defaults["source_operator"] == "equipment_liquid_release"
    assert defaults["pool"]["fluid"] == "Hydrogen"
    assert defaults["pool"]["footprint_origin"] == "declared_sensitivity"
