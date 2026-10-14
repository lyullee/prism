from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_compressible_plane_facility_campaign import (  # noqa: E402
    _load_frequency_scenarios,
    load_backend,
)
from lh2_tno.backend import tree_digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_facility_runner_refreshes_backend_pin_only_when_requested(tmp_path):
    package_root = tmp_path / "provider"
    package_root.mkdir()
    (package_root / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    config_path = tmp_path / "backend.json"
    config_path.write_text(
        json.dumps({
            "interpreter": sys.executable,
            "packages": [{
                "name": "provider",
                "root": str(package_root),
                "sha256": "0" * 64,
            }],
            "timeout_s": 30.0,
            "required_versions": {},
        }),
        encoding="utf-8",
    )
    config, refreshed = load_backend(config_path, refresh_pins=True)
    assert config.packages[0].sha256 == tree_digest(package_root)
    assert refreshed[0]["name"] == "provider"

    _, no_refresh = load_backend(config_path, refresh_pins=False)
    assert no_refresh == []


def test_campaign_frequency_scenario_catalog_is_explicit_and_complete():
    scenarios = _load_frequency_scenarios(
        ROOT / "examples" / "compressible_plane_facility_frequency_scenarios.json"
    )
    assert len(scenarios) == 5
    assert {row.correlation_assumption for row in scenarios} == {
        "within_asset_shared_quantile",
        "independent_event_bounds",
    }
