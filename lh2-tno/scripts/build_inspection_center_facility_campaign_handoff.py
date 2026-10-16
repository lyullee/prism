"""Join the reconstructed facility HAZOP bridge to explicit annual conditions.

The bridge result contains one selected supply branch and two normal
components.  This adapter carries that selected branch to the existing annual
weather/population/IR-FN ledger while preserving the normal components as
withheld coverage.  The annual condition file is an explicit input; this
script never invents occupancy or weather and never opens facility-QRA
promotion for diagnostic provider packets.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _object(path: Path) -> dict[str, Any]:
    value = _load(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _save(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _annual_conditions(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    conditions = record.get("annual_conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("annual-condition record must contain a nonempty annual_conditions array")
    result = []
    for condition in conditions:
        if not isinstance(condition, Mapping):
            raise ValueError("annual condition must be an object")
        copied = copy.deepcopy(dict(condition))
        if not copied.get("id") or not copied.get("weather") or not copied.get("population"):
            raise ValueError("annual condition must declare id, weather, and population")
        result.append(copied)
    return result


def _branch_binding(bridge: Mapping[str, Any], annual_condition_id: str) -> dict[str, Any]:
    components = bridge.get("components")
    if not isinstance(components, Mapping):
        raise ValueError("bridge result has no components")
    selected = []
    for component_id, component in components.items():
        if not isinstance(component, Mapping):
            continue
        if component.get("status") != "CONSEQUENCE_BRANCHES_EVALUATED":
            continue
        branches = component.get("branches")
        if not isinstance(branches, list) or len(branches) != 1:
            raise ValueError(f"selected component must have one branch: {component_id}")
        selected.append((str(component_id), component, branches[0]))
    if len(selected) != 1:
        raise ValueError(f"expected one selected bridge component, got {len(selected)}")
    component_id, component, branch = selected[0]
    result = branch.get("result")
    risk = branch.get("risk")
    if not isinstance(result, Mapping) or result.get("status") != "CONSEQUENCE_EVALUATED":
        raise ValueError("selected bridge branch has no evaluated consequence")
    if not isinstance(risk, Mapping) or risk.get("status") != "AVAILABLE_CURRENT_WEATHER_IR":
        raise ValueError("selected bridge branch has no current-weather IR atom")
    consequence = result.get("consequence")
    atom = risk.get("risk_atom")
    if not isinstance(consequence, Mapping) or not isinstance(atom, Mapping):
        raise ValueError("selected bridge branch lacks consequence/risk atom")
    data = consequence.get("data")
    probabilities = data.get("ignition_branch_probabilities") if isinstance(data, Mapping) else None
    observed = atom.get("receptor_harm_low_high")
    if not isinstance(probabilities, Mapping) or not isinstance(observed, Mapping):
        raise ValueError("selected branch lacks ignition probabilities or receptor harm")
    active_probability = sum(
        float(value) for name, value in probabilities.items() if name != "no_ignition"
    )
    if active_probability <= 0.0:
        raise ValueError("selected branch has no active ignition probability")
    branch_harm: dict[str, dict[str, list[float]]] = {}
    for receptor_id, endpoints in observed.items():
        if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2:
            raise ValueError(f"invalid observed harm endpoints: {receptor_id}")
        branch_harm[str(receptor_id)] = {
            str(name): (
                [0.0, 0.0]
                if name == "no_ignition"
                else [float(value) / active_probability for value in endpoints]
            )
            for name in probabilities
        }
    selection = component.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("selected branch has no HAZOP selection")
    scenario_id = str(branch.get("scenario_id") or "")
    scenario_family = str(branch.get("scenario_family") or "")
    operating_mode = str(branch.get("operating_mode") or selection.get("operating_mode") or "")
    release_path = consequence.get("equipment_release_path")
    boundaries = release_path.get("boundaries") if isinstance(release_path, Mapping) else None
    release_branch_id = "provider-release"
    if isinstance(boundaries, list) and boundaries and isinstance(boundaries[0], Mapping):
        release_branch_id = str(boundaries[0].get("termination_basis") or release_branch_id)
    return {
        "component_id": component_id,
        "operating_mode": operating_mode,
        "hazop_scenario_id": scenario_id,
        "event_id": str(atom.get("event_id") or ""),
        "asset_id": str(atom.get("asset_id") or ""),
        "annual_condition_id": annual_condition_id,
        "release_branch_id": release_branch_id,
        "release_branch_probability": 1.0,
        "occupancy_probability": 1.0,
        "ignition_branch_probabilities": dict(probabilities),
        "branch_harm_low_high": branch_harm,
        "scenario_families": [scenario_family],
    }


def _frequency_uncertainty(
    bridge: Mapping[str, Any],
    frequency_scenarios_record: Mapping[str, Any],
    known_ir: Mapping[str, Any],
) -> dict[str, Any]:
    """Reweight the selected atom only across declared literature scenarios.

    The generic catalogue marks the selected ambient-vaporizer asset as
    ``fixed`` in its low/high scenarios.  That is a valid sensitivity ledger,
    but it is not a marginal p05/p95 confidence interval.  Missing bounds stay
    explicitly unavailable.
    """
    selected_atom = None
    for component in bridge.get("components", {}).values():
        if not isinstance(component, Mapping):
            continue
        for branch in component.get("branches", ()):  # selected component only
            if isinstance(branch, Mapping):
                risk = branch.get("risk")
                if isinstance(risk, Mapping) and isinstance(risk.get("risk_atom"), Mapping):
                    selected_atom = risk["risk_atom"]
                    break
        if selected_atom is not None:
            break
    if not isinstance(selected_atom, Mapping):
        raise ValueError("bridge has no selected risk atom for frequency sensitivity")
    central = float(selected_atom.get("initiating_frequency_per_year"))
    asset_id = str(selected_atom.get("asset_id") or "")
    p05 = selected_atom.get("frequency_p05_per_year")
    p95 = selected_atom.get("frequency_p95_per_year")
    scenarios = frequency_scenarios_record.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("frequency scenario record must contain scenarios")
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            continue
        scenario_id = str(scenario.get("id") or "")
        asset_quantiles = scenario.get("asset_quantiles")
        basis = asset_quantiles.get(asset_id) if isinstance(asset_quantiles, Mapping) else None
        scenario_frequency = None
        status = "WITHHELD_MISSING_MARGINAL_FREQUENCY_BOUND"
        if basis in {"published", "fixed"}:
            scenario_frequency = central
            status = "FIXED_CATALOGUE_RATE_SCENARIO"
        elif basis == "p05" and isinstance(p05, (int, float)):
            scenario_frequency = float(p05)
            status = "PUBLISHED_MARGINAL_P05_SCENARIO"
        elif basis == "p95" and isinstance(p95, (int, float)):
            scenario_frequency = float(p95)
            status = "PUBLISHED_MARGINAL_P95_SCENARIO"
        row: dict[str, Any] = {
            "id": scenario_id,
            "asset_id": asset_id,
            "asset_quantile_basis": basis,
            "status": status,
            "annual_frequency_per_year": scenario_frequency,
            "frequency_is_not_inferred": True,
        }
        if scenario_frequency is not None:
            scale = scenario_frequency / central if central > 0.0 else 0.0
            row["annual_ir_low_high"] = {
                str(receptor_id): [float(value) * scale for value in endpoints]
                for receptor_id, endpoints in known_ir.items()
                if isinstance(endpoints, (list, tuple)) and len(endpoints) == 2
            }
        else:
            row["annual_ir_low_high"] = None
        rows.append(row)
    return {
        "schema_version": "prism.facility_frequency_sensitivity.v1",
        "event_id": selected_atom.get("event_id"),
        "asset_id": asset_id,
        "central_frequency_per_year": central,
        "marginal_p05_per_year": p05,
        "marginal_p95_per_year": p95,
        "status": (
            "LITERATURE_SCENARIO_SENSITIVITY_AVAILABLE"
            if all(row["annual_frequency_per_year"] is not None for row in rows)
            else "LITERATURE_SCENARIO_SENSITIVITY_PARTIAL"
        ),
        "facility_credible_interval": False,
        "frequency_inference_performed": False,
        "sensor_frequency_learning_used": False,
        "rows": rows,
        "interpretation": (
            "Declared catalogue scenario reweighting only. Fixed low/high rates "
            "do not constitute marginal p05/p95 uncertainty bounds or a statistical "
            "confidence interval."
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    from lh2_tno.hazop_campaign import build_hazop_facility_campaign_result

    bridge = _object(args.bridge)
    conditions = _annual_conditions(_object(args.annual_conditions))
    frequency_scenarios_record = _object(args.frequency_scenarios)
    condition_id = str(conditions[0]["id"])
    binding = _branch_binding(bridge, condition_id)
    component_ids = sorted(str(component_id) for component_id in bridge["components"])
    handoff = build_hazop_facility_campaign_result(
        bridge,
        annual_conditions=conditions,
        scenario_bindings=[binding],
        expected_component_ids=component_ids,
        allow_withheld_normal_components=True,
    )
    result = dict(handoff)
    result["schema_version"] = "prism.inspection_center_facility_campaign_handoff.v1"
    result["input_evidence"] = {
        "bridge": str(args.bridge),
        "annual_conditions": str(args.annual_conditions),
        "frequency_scenarios": str(args.frequency_scenarios),
        "annual_condition_id": condition_id,
        "annual_condition_provenance": conditions[0].get("provenance"),
        "population_provenance": [
            row.get("provenance")
            for row in conditions[0].get("population", [])
            if isinstance(row, Mapping)
        ],
    }
    ledger = result.get("facility_ledger")
    known_ir = (
        ledger.get("known_contribution_annual_ir_low_high")
        if isinstance(ledger, Mapping)
        else {}
    )
    result["frequency_uncertainty"] = _frequency_uncertainty(
        bridge,
        frequency_scenarios_record,
        known_ir if isinstance(known_ir, Mapping) else {},
    )
    result["facility_campaign_handoff_audit"] = {
        "status": "FACILITY_CAMPAIGN_HANDOFF_EXECUTED_DIAGNOSTIC",
        "declared_component_count": len(component_ids),
        "selected_component_count": 1,
        "withheld_normal_component_ids": [
            component_id
            for component_id, component in bridge["components"].items()
            if isinstance(component, Mapping)
            and component.get("status") == "WITHHELD_HAZOP_NO_DEVIATION"
        ],
        "annual_weather_population_input_explicit": True,
        "frequency_inference_performed": False,
        "sensor_frequency_learning_used": False,
        "facility_annual_ir_available": False,
        "facility_fn_available": False,
        "facility_qra_claim": False,
        "provider_packet_qualification": "UNQUALIFIED_DIAGNOSTIC",
        "physical_validation_claim": False,
        "diagnostic_only": True,
    }
    result["interpretation"] = (
        "The selected HAZOP branch crossed the explicit annual weather/population "
        "handoff. Normal components remain withheld coverage entries; the ledger "
        "therefore exposes a conditional/operator-limited facility contribution "
        "without promoting it to qualified annual facility IR/F-N."
    )
    _save(args.output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", type=Path, default=ROOT / "examples/inspection_center_facility_hazop_bridge.json")
    parser.add_argument("--annual-conditions", type=Path, default=ROOT / "results/20261009/generic_full_scope_worklist/campaign_result.json")
    parser.add_argument("--frequency-scenarios", type=Path, default=ROOT / "results/20261110/native_full_scope_frequency_assessment_latest2/frequency_scenarios.json")
    parser.add_argument("--output", type=Path, default=ROOT / "examples/inspection_center_facility_campaign_handoff.json")
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
        raise SystemExit(f"inspection-center campaign handoff failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "campaign_status": result["campaign"]["status"],
        "facility_ledger_status": result["facility_ledger"]["status"],
        "risk_atom_count": len(result["campaign"].get("risk_atoms", [])),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
