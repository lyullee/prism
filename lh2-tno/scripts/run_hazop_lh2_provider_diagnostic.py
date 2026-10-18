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
from lh2_tno.uncertainty import LiteratureFrequencyScenario, literature_frequency_uncertainty  # noqa: E402
from lh2_tno.service import (  # noqa: E402
    ConsequenceService,
    RealtimeConsequenceMonitor,
    RealtimeFrequencyBinding,
    _realtime_current_weather_risk,
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


def _forecast_facility_campaign_evaluator(
    *,
    event: object,
    scenario_id: str,
    frequency_binding: RealtimeFrequencyBinding,
    annual_conditions: list[dict],
) -> object:
    """Build one conditional facility handoff for every evaluated forecast trigger.

    The forecast scan stores a consequence-gate result inside each evaluated
    ``scenario_entries[].evaluation`` row rather than pretending that a future
    state is a current runtime snapshot.  This adapter reconstructs only the
    explicit one-branch handoff required by the existing facility campaign
    contract.  It reuses the provider harm and the reviewed literature event;
    it does not infer a future frequency, merge repeated forecast times, or
    promote a facility total.
    """

    def evaluate(forecast: dict) -> dict:
        campaigns: list[dict] = []
        for entry in forecast.get("scenario_entries", []):
            if not isinstance(entry, dict):
                continue
            evaluation = entry.get("evaluation")
            result = evaluation.get("result") if isinstance(evaluation, dict) else None
            if not isinstance(result, dict) or result.get("status") != "CONSEQUENCE_EVALUATED":
                continue
            component_id = str(entry.get("component_id") or "")
            entry_scenario_id = str(entry.get("scenario_id") or "")
            if component_id != "storage-tank-01" or entry_scenario_id != scenario_id:
                raise ValueError("forecast facility handoff received an unexpected component/scenario")
            selection = result.get("selection")
            selected = selection.get("selected_scenarios") if isinstance(selection, dict) else None
            if not isinstance(selected, list) or len(selected) != 1 or not isinstance(selected[0], dict):
                raise ValueError("forecast consequence lacks one selected HAZOP scenario")
            scenario_family = str(selected[0].get("scenario_family") or "")
            operating_mode = str(entry.get("operating_mode") or "")
            consequence = result.get("consequence")
            if not isinstance(consequence, dict):
                raise ValueError("forecast consequence result lacks consequence data")
            risk = _realtime_current_weather_risk(consequence, frequency_binding)
            if risk.get("status") != "AVAILABLE_CURRENT_WEATHER_IR":
                raise ValueError("forecast consequence cannot produce an explicit frequency-bound IR atom")
            data = consequence.get("data")
            receptor_rows = data.get("receptors", []) if isinstance(data, dict) else []
            branch_harm: dict[str, dict[str, list[float]]] = {}
            for receptor in receptor_rows:
                if not isinstance(receptor, dict):
                    raise ValueError("forecast provider receptor row is not an object")
                values = receptor.get("branch_harm_low_high")
                if not isinstance(values, list) or len(values) != 2:
                    raise ValueError("forecast provider receptor lacks two branch harm endpoints")
                branch_harm[str(receptor["id"])] = {
                    name: [float(values[0][name]), float(values[1][name])]
                    for name in ("direct_fire", "delayed_flash_fire", "delayed_explosion", "no_ignition")
                }
            forecast_time = float(entry.get("forecast_time_s", 0.0))
            condition = copy.deepcopy(annual_conditions[0])
            condition["id"] = f"synthetic-forecast-weather-D-3ms-t{forecast_time:g}"
            condition["provenance"] = (
                "synthetic diagnostic forecast condition; not a site weather distribution"
            )
            binding = {
                "component_id": component_id,
                "operating_mode": operating_mode,
                "hazop_scenario_id": entry_scenario_id,
                "event_id": str(event.id),
                "asset_id": str(event.asset_id),
                "annual_condition_id": condition["id"],
                "release_branch_id": "provider-inventory-depletion",
                "release_branch_probability": 1.0,
                "ignition_branch_probabilities": data["ignition_branch_probabilities"],
                "branch_harm_low_high": branch_harm,
                "scenario_families": [scenario_family],
            }
            runtime_result = {
                "schema_version": "prism.hazop_facility_runtime.v1",
                "facility_id": str(result["selection"]["facility_id"]),
                "status": "FACILITY_HAZOP_RUNTIME_EVALUATED",
                "component_count": 1,
                "components": {
                    component_id: {
                        "status": "CONSEQUENCE_BRANCHES_EVALUATED",
                        "component_id": component_id,
                        "selection": copy.deepcopy(selection),
                        "branches": [{
                            "scenario_id": entry_scenario_id,
                            "scenario_family": scenario_family,
                            "operating_mode": operating_mode,
                            "result": copy.deepcopy(result),
                            "risk": risk,
                        }],
                        "policy": copy.deepcopy(result.get("policy", {})),
                    }
                },
                "risk_atoms": [{
                    "component_id": component_id,
                    "scenario_id": entry_scenario_id,
                    "scenario_family": scenario_family,
                    "operating_mode": operating_mode,
                    "risk": risk,
                }],
                "conditional_current_weather_risk": {
                    "status": "AVAILABLE_CONDITIONAL_CURRENT_WEATHER_IR",
                    "annual_ir_low_high_by_receptor": copy.deepcopy(risk["annual_ir_low_high"]),
                    "risk_atom_count": 1,
                    "frequency_learning": False,
                },
                "facility_annual_ir_available": False,
                "facility_fn_available": False,
            }
            handoff = build_hazop_facility_campaign_result(
                runtime_result,
                annual_conditions=[condition],
                scenario_bindings=[binding],
                expected_component_ids=(component_id,),
            )
            campaigns.append({
                "forecast_time_s": forecast_time,
                "component_id": component_id,
                "scenario_id": entry_scenario_id,
                "campaign": handoff["campaign"],
                "facility_ledger": handoff["facility_ledger"],
                "hazop_scenario_trace_audit": handoff["hazop_scenario_trace_audit"],
                "equipment_state_release_audit": handoff["equipment_state_release_audit"],
                "risk_atom_chain_audit": handoff["risk_atom_chain_audit"],
            })
        return {
            "status": "FORECAST_FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
            "facility_id": forecast.get("facility_id"),
            "forecast_trigger_count": forecast.get("trigger_count"),
            "forecast_evaluated_count": forecast.get("evaluated_count"),
            "campaign_count": len(campaigns),
            "campaigns": campaigns,
            "conditional_diagnostic_facility_risk_available": bool(campaigns),
            "policy": {
                "forecast_time_is_not_annual_probability": True,
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "physical_validation_claim": False,
                "facility_qra_promotion": False,
            },
        }

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
        forecast_facility_campaign_evaluator=_forecast_facility_campaign_evaluator(
            event=event,
            scenario_id=scenario_id,
            frequency_binding=frequency_binding,
            annual_conditions=annual_conditions,
        ),
    )
    # Reweight the saved HAZOP risk atoms with the published literature bounds.
    # This changes no provider or consequence physics and does not create a
    # facility credible interval; it only closes the conditional known-atom
    # uncertainty record required by the completion audit.
    facility_campaign_result = result.get("facility_campaign")
    campaign = (
        facility_campaign_result.get("campaign")
        if isinstance(facility_campaign_result, dict)
        else None
    )
    facility_ledger = (
        facility_campaign_result.get("facility_ledger")
        if isinstance(facility_campaign_result, dict)
        else None
    )
    if isinstance(campaign, dict) and isinstance(facility_ledger, dict):
        uncertainty_input = copy.deepcopy(campaign)
        uncertainty_input["known_contribution_annual_ir_low_high"] = copy.deepcopy(
            facility_ledger.get("known_contribution_annual_ir_low_high")
        )
        uncertainty_input["known_contribution_expected_death_fn_low_high"] = copy.deepcopy(
            facility_ledger.get("known_contribution_expected_death_fn_low_high")
        )
        # The realtime campaign event is intentionally a compact
        # provider-boundary record, whereas the uncertainty calculator
        # validates the full catalogue FrequencyEvent contract. Reattach the
        # original generated event fields and retain the HAZOP annotations.
        uncertainty_event = event.model_dump(mode="json")
        campaign_event = campaign["events"][0]
        for key in ("scenario_families", "operating_mode", "hazop_scenario_id"):
            if key in campaign_event:
                uncertainty_event[key] = copy.deepcopy(campaign_event[key])
        uncertainty_input["events"] = [uncertainty_event]
        asset_id = str(event.asset_id)
        uncertainty_scenarios = tuple(
            LiteratureFrequencyScenario(
                id=identifier,
                asset_quantiles={asset_id: quantile},
                provenance="published frequency bounds from the explicit catalogue event; conditional diagnostic only",
            )
            for identifier, quantile in (
                ("hazop-provider-frequency-p05", "p05"),
                ("hazop-provider-frequency-published", "published"),
                ("hazop-provider-frequency-p95", "p95"),
            )
        )
        result["frequency_uncertainty"] = literature_frequency_uncertainty(
            uncertainty_input,
            uncertainty_scenarios,
        )
    else:
        # A partial current runtime must remain a valid diagnostic output. Do
        # not fabricate a campaign or reweight a missing risk atom; preserve a
        # machine-readable withheld state instead of raising KeyError.
        result["frequency_uncertainty"] = {
            "status": "WITHHELD_NO_CURRENT_FACILITY_CAMPAIGN",
            "scenarios": [],
            "fresh_physics_executed": False,
            "facility_credible_interval": False,
            "frequency_inference_performed": False,
            "blocking_reasons": [
                "current HAZOP runtime did not produce a facility campaign",
                "no current campaign risk atoms were available for literature reweighting",
            ],
        }
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
        "frequency_uncertainty": {
            "scenario_count": len(result["frequency_uncertainty"]["scenarios"]),
            "conditional_diagnostic_facility_risk": bool(
                result["frequency_uncertainty"]["scenarios"]
            ),
            "facility_credible_interval": False,
            "fresh_physics_executed": False,
            "status": result["frequency_uncertainty"].get("status"),
        },
        "facility_campaign": {
            "status": result["facility_campaign"].get("status"),
            "conditional_diagnostic_facility_ir_available": result["facility_campaign"].get("facility_ledger", {}).get("conditional_diagnostic_facility_risk_available") is True,
            "conditional_diagnostic_facility_fn_available": result["facility_campaign"].get("facility_ledger", {}).get("conditional_diagnostic_facility_expected_death_fn_low_high") is not None,
            "facility_total_risk_available": result["facility_campaign"].get("facility_ledger", {}).get("facility_total_risk_available") is True,
            "qualified_facility_ir_fn_available": result["facility_campaign"].get("facility_ledger", {}).get("qualified_facility_qra_available") is True,
        },
        "forecast_facility_campaign": {
            "status": result["forecast_facility_campaign"].get("status"),
            "campaign_count": result["forecast_facility_campaign"].get("campaign_count", 0),
            "conditional_diagnostic_facility_risk_available": result["forecast_facility_campaign"].get("conditional_diagnostic_facility_risk_available") is True,
            "facility_qra_promotion": result["forecast_facility_campaign"].get("policy", {}).get("facility_qra_promotion") is True,
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
    current_facility_ledger = result.get("facility_campaign", {}).get(
        "facility_ledger", {}
    )
    forecast_campaigns = result.get("forecast_facility_campaign", {}).get(
        "campaigns", []
    )
    forecast_ledgers = [
        row.get("facility_ledger", {})
        for row in forecast_campaigns
        if isinstance(row, dict) and isinstance(row.get("facility_ledger"), dict)
    ]
    forecast_boundary_ready = (
        None
        if not forecast_ledgers
        else all(row.get("provider_release_boundary_ready") is True for row in forecast_ledgers)
    )
    forecast_facility_total_available = (
        None
        if not forecast_ledgers
        else all(row.get("facility_total_risk_available") is True for row in forecast_ledgers)
    )
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
                "current_provider_release_boundary_ready": current_facility_ledger.get(
                    "provider_release_boundary_ready"
                ),
                "current_facility_total_risk_available": current_facility_ledger.get(
                    "facility_total_risk_available"
                ),
                "forecast_provider_release_boundary_ready": forecast_boundary_ready,
                "forecast_facility_total_risk_available": forecast_facility_total_available,
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
