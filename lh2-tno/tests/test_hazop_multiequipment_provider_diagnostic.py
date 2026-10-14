from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from lh2_tno.equipment_manifest import EquipmentManifest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_hazop_lh2_multiequipment_provider_diagnostic.py"
SPEC = importlib.util.spec_from_file_location("hazop_multi_provider_diagnostic", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture()
def manifest() -> EquipmentManifest:
    return EquipmentManifest.from_json(ROOT / "examples" / "generic_lh2_near_receptor_manifest.json")


def _condition(*, probability: float = 1.0, receptor_id: str = "worker-01") -> dict:
    return {
        "id": "site-D-3ms",
        "annual_probability": probability,
        "weather": {
            "wind_speed_m_s": 3.0,
            "wind_from_bearing_deg": 270.0,
            "measurement_height_m": 10.0,
            "roughness_m": 0.03,
            "stability": "D",
            "relative_humidity": 0.5,
        },
        "population": [
            {
                "receptor_id": receptor_id,
                "persons": 1.0,
                "presence_probability": 1.0,
                "provenance": "reviewed test condition",
            }
        ],
        "provenance": "reviewed test condition",
    }


def test_loader_accepts_one_explicit_site_condition(tmp_path: Path, manifest: EquipmentManifest) -> None:
    path = tmp_path / "annual_conditions.json"
    path.write_text(json.dumps([_condition()]), encoding="utf-8")

    conditions, source = MODULE._load_annual_conditions(
        path,
        defaults={"weather": {}},
        manifest=manifest,
    )

    assert [row["id"] for row in conditions] == ["site-D-3ms"]
    assert source["source"] == "caller_file"
    assert source["condition_count"] == 1


def test_loader_rejects_non_closing_annual_probabilities(
    tmp_path: Path, manifest: EquipmentManifest
) -> None:
    path = tmp_path / "annual_conditions.json"
    path.write_text(json.dumps([_condition(probability=0.5)]), encoding="utf-8")

    with pytest.raises(ValueError, match="probabilities must close to one"):
        MODULE._load_annual_conditions(
            path,
            defaults={"weather": {}},
            manifest=manifest,
        )


def test_loader_rejects_receptor_population_set_drift(
    tmp_path: Path, manifest: EquipmentManifest
) -> None:
    first = _condition()
    second = _condition(receptor_id="public-01")
    second["id"] = "site-E-4ms"
    second["annual_probability"] = 0.5
    first["annual_probability"] = 0.5
    path = tmp_path / "annual_conditions.json"
    path.write_text(json.dumps([first, second]), encoding="utf-8")

    with pytest.raises(ValueError, match="same receptor population set"):
        MODULE._load_annual_conditions(
            path,
            defaults={"weather": {}},
            manifest=manifest,
        )


def test_loader_rejects_first_condition_weather_drift(
    tmp_path: Path, manifest: EquipmentManifest
) -> None:
    condition = _condition()
    condition["weather"]["wind_speed_m_s"] = 7.0
    path = tmp_path / "annual_conditions.json"
    path.write_text(json.dumps([condition]), encoding="utf-8")

    with pytest.raises(ValueError, match="first annual condition weather differs"):
        MODULE._load_annual_conditions(
            path,
            defaults={"weather": {"wind_speed_m_s": 3.0}},
            manifest=manifest,
        )


def test_scope_catalog_keeps_applicable_undispatched_families_explicit(
    manifest: EquipmentManifest,
) -> None:
    catalog = MODULE._build_scope_catalog(
        manifest,
        {
            "risk_atoms": [
                {
                    "component_id": "storage-tank-01",
                    "scenario_family": "vessel_hole",
                }
            ]
        },
    )

    assert catalog["scenario_count"] == 12
    assert catalog["policy"]["missing_family_is_not_substituted"] is True
    rows = {row["family"]: row for row in catalog["rows"]}
    assert rows["vessel_hole"]["status"] == "DISPATCHED_DIAGNOSTIC"
    assert rows["pipe_hole"]["status"] == "APPLICABLE_NOT_DISPATCHED"
    assert rows["vertical_handoff"]["status"] == "APPLICABLE_NOT_DISPATCHED"


def test_runtime_hazop_selection_is_reaudited_from_the_same_mode_frames() -> None:
    table = {
        "schema_version": "prism.hazop_operating_mode_selection.v1",
        "id": "test-multi-hazop",
        "facility_id": "test-facility",
        "operating_modes": ["receiving", "supply", "standby"],
        "configuration_origin": "synthetic",
        "source_provenance": "test HAZOP table",
        "rows": [MODULE._scenario_row(spec) for spec in MODULE.COMPONENT_SPECS],
    }
    frames_output = MODULE.build_observed_state_runtime_frames(
        MODULE._runtime_sources(MODULE.COMPONENT_SPECS)
    )
    report = MODULE._audit_runtime_hazop_selection(
        table,
        frames_output,
        now_s=12.1,
    )
    assert report["status"] == "OBSERVED_HAZOP_MODE_SCENARIOS_SELECTED"
    assert report["evaluated_frame_count"] == len(MODULE.COMPONENT_SPECS)
    assert report["selected_scenario_count"] == len(MODULE.COMPONENT_SPECS)
    assert report["policy"]["operating_mode_inferred"] is False
