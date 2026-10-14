"""Run one explicit current/forecast HAZOP-to-SLABx-LH2 diagnostic.

This is a reproducible integration example, not a facility-QRA promotion
command.  The HAZOP row selects a liquid/two-phase family, the resolver reads
one existing provider packet, and the frequency binding reads one generated
literature event.  No value is inferred from the pressure signal.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.consequences import ConsequenceRequest  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.hazop_forecast import build_hazop_forecast_runtime_evaluator  # noqa: E402
from lh2_tno.hazop_campaign import build_hazop_facility_campaign_result  # noqa: E402
from lh2_tno.integrated_risk import run_hazop_integrated_risk  # noqa: E402
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import provider_release_resolver_from_packet  # noqa: E402
from lh2_tno.service import (  # noqa: E402
    ConsequenceService,
    RealtimeConsequenceMonitor,
    RealtimeFrequencyBinding,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_backend(path: Path) -> BackendConfig:
    raw = _load(path)
    for package in raw.get("packages", []):
        root = Path(package["root"])
        package["sha256"] = tree_digest(root)
    return BackendConfig.model_validate_json(json.dumps(raw, ensure_ascii=False))


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _runtime_source() -> dict:
    return {
        "source_id": "synthetic-monitoring-storage-tank-01",
        "source_path": "synthetic://prism/hazop-provider-diagnostic",
        "source_sha256": "c" * 64,
        "format": "json",
        "component_id": "storage-tank-01",
        "origin": "synthetic",
        "samples": [
            {
                "captured_at_s": 12.0,
                "operating_mode": "receiving",
                "values": {
                    "tank_pressure": {
                        "quantity": "pressure",
                        "value_si": 650000.0,
                        "sensor_location": "storage-tank-01.vapour",
                        "quality": "valid",
                    }
                },
            }
        ],
    }


def _facility_campaign_evaluator(*, event: object, scenario_id: str, annual_conditions: list[dict]) -> object:
    """Build the explicit HAZOP-to-facility handoff for this diagnostic.

    The current consequence result owns branch-specific harm.  The callback
    only packages that already-computed harm with one explicitly declared
    synthetic weather/population condition; it does not create frequency or
    extrapolate a facility total.
    """
    def evaluate(current: dict) -> dict:
        component = current["components"]["storage-tank-01"]
        branch = component["branches"][0]
        consequence_data = branch["result"]["consequence"]["data"]
        receptor_rows = consequence_data.get("receptors", [])
        branch_harm: dict[str, dict[str, list[float]]] = {}
        for receptor in receptor_rows:
            values = receptor.get("branch_harm_low_high")
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError("provider consequence receptor lacks two branch harm endpoints")
            branch_harm[str(receptor["id"])] = {
                name: [float(values[0][name]), float(values[1][name])]
                for name in ("direct_fire", "delayed_flash_fire", "delayed_explosion", "no_ignition")
            }
        scenario_family = str(branch["scenario_family"])
        binding = {
            "component_id": "storage-tank-01",
            "operating_mode": "receiving",
            "hazop_scenario_id": scenario_id,
            "event_id": str(event.id),
            "asset_id": str(event.asset_id),
            "annual_condition_id": annual_conditions[0]["id"],
            "release_branch_id": "provider-inventory-depletion",
            "release_branch_probability": 1.0,
            "ignition_branch_probabilities": consequence_data["ignition_branch_probabilities"],
            "branch_harm_low_high": branch_harm,
            "scenario_families": [scenario_family],
        }
        return build_hazop_facility_campaign_result(
            current,
            annual_conditions=annual_conditions,
            scenario_bindings=[binding],
            expected_component_ids=("storage-tank-01",),
        )

    return evaluate


def run(args: argparse.Namespace) -> dict:
    table = _load(args.table)
    forecast_table = {"storage-tank-01": table}
    manifest = EquipmentManifest.from_json(args.manifest)
    facility = manifest.to_facility()
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    event = next(
        event
        for event in generate_events(facility, plan)
        if event.id.endswith("/storage-shell/AREA_0.01%")
    )
    frequency_binding = RealtimeFrequencyBinding.from_frequency_event(
        event,
        annual_condition_probability=1.0,
        release_branch_probability=1.0,
        occupancy_probability=1.0,
    )

    defaults = _load(args.provider_defaults)
    # The provider packet declares positive ground-liquid arrival but does not
    # carry a resolved pool footprint.  Keep the chain fail-closed by adding a
    # declared sensitivity boundary explicitly for this synthetic diagnostic.
    # This is a scenario assumption, not a footprint inferred from sensors or
    # from the literature frequency event.
    defaults["pool"] = {
        "footprint_origin": "declared_sensitivity",
        "fluid": "Hydrogen",
        "fluid_translation": "none",
        "radius_m": 0.005,
        "conductivity_w_mk": 0.6,
        "diffusivity_m2_s": 1.5e-7,
        "initial_temperature_k": 288.15,
        "domain_radius_m": 0.25,
        "radial_step_m": 0.00025,
        "maximum_time_step_s": 0.01,
    }
    defaults["source_operator"] = "equipment_liquid_release"
    defaults["release_termination"] = {
        "basis": "inventory_depletion",
        "time_s": 0.05,
        "provenance": "provider packet termination_basis=inventory_depletion",
    }
    resolver = provider_release_resolver_from_packet(
        args.provider_packet,
        defaults,
        component_id="storage-tank-01",
    )
    template_raw = _load(args.template)
    template_raw["component_id"] = "storage-tank-01"
    template = ConsequenceRequest.model_validate_json(
        json.dumps(template_raw, ensure_ascii=False)
    )
    backend = IsolatedBackend(_load_backend(args.backend_config))
    monitor = RealtimeConsequenceMonitor(
        ConsequenceService(ResearchPipeline(facility, backend)),
        period_s=1.0,
        deadline_s=30.0,
    )
    binding = SimpleNamespace(
        template=template,
        monitor=monitor,
        frequency_binding=frequency_binding,
    )
    scenario_id = "TK01-receiving-liquid-hole:receiving:liquid_two_phase"
    annual_conditions = [{
        "id": "synthetic-current-weather-D-3ms",
        "annual_probability": 1.0,
        "weather": copy.deepcopy(defaults["weather"]),
        "population": [{
            "receptor_id": "worker-01",
            "persons": 1.0,
            "presence_probability": 1.0,
            "provenance": "synthetic diagnostic receptor population; replace with reviewed facility occupancy",
        }],
        "provenance": "synthetic diagnostic current-weather condition; not a site weather distribution",
    }]
    source_frame = build_observed_state_runtime_frames([_runtime_source()])["frames"][0]
    forecast_frames = json.loads(args.forecast_frames.read_text(encoding="utf-8"))
    if not isinstance(forecast_frames, list):
        raise ValueError("forecast frames must be an array")
    # Forecast frames may come from a generic simulator export.  The runtime
    # contract requires the selected HAZOP table's facility identity, so copy
    # that identity at this integration boundary rather than allowing a
    # cross-facility selection.
    forecast_frames = [
        {**frame, "facility_id": table["facility_id"]}
        for frame in forecast_frames
    ]
    result = run_hazop_integrated_risk(
        table,
        {"storage-tank-01": source_frame},
        now_s=12.0,
        component_bindings={"storage-tank-01": binding},
        release_resolvers={("storage-tank-01", scenario_id): resolver},
        forecast_frames=forecast_frames,
        forecast_tables_by_component=forecast_table,
        forecast_component_ids=("storage-tank-01",),
        forecast_quantitative_evaluator=build_hazop_forecast_runtime_evaluator(
            tables_by_component=forecast_table,
            component_bindings={"storage-tank-01": binding},
            release_resolvers={("storage-tank-01", scenario_id): resolver},
        ),
        facility_campaign_evaluator=_facility_campaign_evaluator(
            event=event,
            scenario_id=scenario_id,
            annual_conditions=annual_conditions,
        ),
    )
    result["diagnostic_context"] = {
        "scope": "synthetic_provider_bound_hazop_lh2_diagnostic",
        "pool_boundary": {
            "footprint_origin": "declared_sensitivity",
            "radius_m": defaults["pool"]["radius_m"],
            "provenance": "explicit script assumption required because the provider packet has positive ground liquid and no resolved pool footprint",
        },
        "forecast_facility_id_normalized_to": table["facility_id"],
        "frequency_binding": "explicit generated literature event; no sensor or simulation frequency inference",
        "facility_qra_claim": False,
        "facility_campaign": {
            "status": result["facility_campaign"].get("status"),
            "conditional_diagnostic_facility_ir_available": result["facility_campaign"].get("facility_ledger", {}).get("conditional_diagnostic_facility_risk_available") is True,
            "conditional_diagnostic_facility_fn_available": result["facility_campaign"].get("facility_ledger", {}).get("conditional_diagnostic_facility_expected_death_fn_low_high") is not None,
            "facility_total_risk_available": result["facility_campaign"].get("facility_ledger", {}).get("facility_total_risk_available") is True,
            "qualified_facility_ir_fn_available": result["facility_campaign"].get("facility_ledger", {}).get("qualified_facility_qra_available") is True,
        },
    }
    _save(args.output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=ROOT / "examples/generic_hazop_tables_by_component_provider_bound.json")
    parser.add_argument("--forecast-frames", type=Path, default=ROOT / "examples/generic_hazop_forecast_frames.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "examples/generic_lh2_near_receptor_manifest.json")
    parser.add_argument("--frequency-plan", type=Path, default=ROOT / "examples/generic_lh2_full_scope_frequency_plan.json")
    parser.add_argument("--provider-packet", type=Path, required=True)
    parser.add_argument("--provider-defaults", type=Path, default=ROOT / "examples/provider_request_defaults_liquid.json")
    parser.add_argument("--template", type=Path, default=ROOT / "examples/equipment_consequence_template.json")
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, StopIteration) as error:
        raise SystemExit(f"HAZOP LH2 provider diagnostic failed: {error}") from error
    current = result["current"]
    forecast = result["forecast"]
    print(
        json.dumps(
            {
                "status": result["status"],
                "current_status": current.get("status"),
                "current_risk_atom_count": len(current.get("risk_atoms", [])),
                "forecast_status": forecast.get("status"),
                "forecast_trigger_count": forecast.get("trigger_count"),
                "forecast_evaluated_count": forecast.get("evaluated_count"),
                "forecast_withheld_count": forecast.get("withheld_count"),
                "facility_qra_promotion": result["policy"]["facility_qra_promotion"],
                "frequency_inference_performed": result["policy"]["frequency_inference_performed"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
