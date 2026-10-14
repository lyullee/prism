"""Run a multi-equipment HAZOP-to-provider consequence diagnostic.

The command exercises the existing facility runtime coordinator with one
explicit HAZOP deviation for each generic outdoor-LH2 equipment kind.  It
keeps the provider packet, literature event, operating mode, and facility port
identity separate, then records which branches reach the consequence service.

This is a diagnostic integration campaign.  The default packet set contains
synthetic or screening outputs, so a successful branch is not a qualified
facility-QRA result.  A packet with a synthetic termination horizon is kept as
an explicit withheld branch instead of being relabelled as isolation closure.
The facility handoff is built only for branches that actually pass the strict
provider/termination/SLABx-LH2 contracts, and its scope is marked incomplete
when any configured component is withheld.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.consequences import ConsequenceRequest  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.hazop import run_hazop_facility_runtime  # noqa: E402
from lh2_tno.hazop_campaign import build_hazop_facility_campaign_result  # noqa: E402
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    load_provider_emergency_relief,
    provider_release_resolver_from_packet,
    provider_release_set_resolver_from_packet,
)
from lh2_tno.service import (  # noqa: E402
    ConsequenceService,
    RealtimeConsequenceMonitor,
    RealtimeFrequencyBinding,
)


COMPONENT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "component_id": "storage-tank-01",
        "component_kind": "storage_tank",
        "event_id": "generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%",
        "packet_relpath": "results/20261031/native_generic_scope_packets_pipefix/events/000_storage-tank-01_AREA_0.01pct/resolved_release.json",
        "scenario_family": "liquid_two_phase",
        "release_mode": "hole",
        "operating_mode": "receiving",
        "variable_tag": "tank_pressure",
        "state_value_si": 650000.0,
        "source_operator": "equipment_liquid_release",
        "equipment_group": "liquid_provider",
    },
    {
        "component_id": "liquid-transfer-line-01",
        "component_kind": "pipe",
        "event_id": "generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%",
        "packet_relpath": "results/20261018/native_dynamic_pipe_full_bore_facility_frequency/resolved_release.json",
        "scenario_family": "pipe_hole",
        "release_mode": "hole",
        "operating_mode": "supply",
        "variable_tag": "line_pressure",
        "state_value_si": 650000.0,
        "source_operator": "equipment_liquid_release",
        "equipment_group": "liquid_provider_natural_termination",
    },
    {
        "component_id": "transfer-valve-01",
        "component_kind": "valve",
        "event_id": "generic-lh2-full-scope-frequency-example/transfer-valve/AREA_0.01%",
        "packet_relpath": "results/20261031/native_generic_scope_packets_pipefix/events/010_transfer-valve-01_AREA_0.01pct/resolved_release.json",
        "scenario_family": "liquid_two_phase",
        "release_mode": "hole",
        "operating_mode": "supply",
        "variable_tag": "valve_pressure",
        "state_value_si": 650000.0,
        "source_operator": "equipment_liquid_release",
        "equipment_group": "liquid_provider",
    },
    {
        "component_id": "pressure-relief-vent-01",
        "component_kind": "vent_stack",
        "event_id": "generic-lh2-full-scope-frequency-example/pressure-relief-vent/G1",
        "packet_relpath": "results/20261031/native_generic_scope_packets_pipefix/events/015_pressure-relief-vent-01_G1/resolved_release.json",
        "scenario_family": "vent_hole",
        "release_mode": "maximum_relief_discharge",
        "operating_mode": "standby",
        "variable_tag": "vent_pressure",
        "state_value_si": 650000.0,
        "source_operator": "equipment_emergency_relief",
        "equipment_group": "emergency_relief",
    },
    {
        "component_id": "liquid-transfer-pump-01",
        "component_kind": "pump",
        "event_id": "generic-lh2-full-scope-frequency-example/transfer-pump/G1",
        "packet_relpath": "results/20261031/native_generic_scope_packets_pipefix/events/016_liquid-transfer-pump-01_G1/resolved_release.json",
        "scenario_family": "liquid_two_phase",
        "release_mode": "hole",
        "operating_mode": "supply",
        "variable_tag": "pump_pressure",
        "state_value_si": 650000.0,
        "source_operator": "equipment_liquid_release",
        "equipment_group": "liquid_provider",
    },
    {
        "component_id": "ambient-vaporizer-01",
        "component_kind": "vaporizer",
        "event_id": "generic-lh2-full-scope-frequency-example/ambient-vaporizer/G1",
        "packet_relpath": "results/20261031/native_generic_scope_packets_pipefix/events/018_ambient-vaporizer-01_G1/resolved_release.json",
        "scenario_family": "inventory_depletion",
        "release_mode": "instantaneous_inventory",
        "operating_mode": "supply",
        "variable_tag": "vaporizer_pressure",
        "state_value_si": 650000.0,
        "source_operator": "equipment_inventory_depletion",
        "equipment_group": "gas_inventory_depletion",
    },
    {
        "component_id": "reliquefier-01",
        "component_kind": "reliquefier",
        "event_id": "generic-lh2-full-scope-frequency-example/reliquefier/G4",
        "packet_relpath": "results/20261031/native_generic_scope_packets_pipefix/events/021_reliquefier-01_G4/resolved_release_set.json",
        "scenario_family": "two_sided_rupture",
        "release_mode": "two_sided_rupture",
        "operating_mode": "standby",
        "variable_tag": "reliquefier_pressure",
        "state_value_si": 650000.0,
        "source_operator": "equipment_two_sided_rupture",
        "equipment_group": "two_sided_provider",
    },
)


def _load(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _load_backend(path: Path) -> BackendConfig:
    raw = _load(path)
    if not isinstance(raw, dict):
        raise ValueError("backend config must be an object")
    for package in raw.get("packages", []):
        root = Path(package["root"])
        package["sha256"] = tree_digest(root)
    return BackendConfig.model_validate_json(json.dumps(raw, ensure_ascii=False))


def _packet_json(path: Path) -> dict[str, Any]:
    value = _load(path)
    if not isinstance(value, dict):
        raise ValueError(f"provider packet must be an object: {path}")
    return value


def _packet_positions(path: Path) -> list[list[float]]:
    value = _packet_json(path)
    if isinstance(value.get("releases"), list):
        return [list(row["position_enu_m"]) for row in value["releases"]]
    if value.get("position_enu_m") is not None:
        return [list(value["position_enu_m"])]
    raise ValueError(f"provider packet has no explicit position: {path}")


def _rebase_manifest_to_packets(
    manifest_path: Path,
    packet_paths: Mapping[str, Path],
) -> tuple[EquipmentManifest, dict[str, Any]]:
    """Create an explicit diagnostic geometry matching provider exit positions.

    External exporters use their own local coordinate origin.  The rebasing is
    recorded as diagnostic metadata so a packet is never silently attached to
    the unrelated generic-manifest coordinates.  This is not a reviewed plant
    geometry and never promotes a facility-QRA claim.
    """
    raw = _load(manifest_path)
    if not isinstance(raw, dict):
        raise ValueError("equipment manifest must be an object")
    original = {
        str(row["id"]): list(row["position_enu_m"])
        for row in raw.get("components", [])
        if isinstance(row, dict) and row.get("position_enu_m") is not None
    }
    positions: dict[str, list[list[float]]] = {}
    for component_id, path in packet_paths.items():
        if path.exists():
            positions[component_id] = _packet_positions(path)
    for component in raw.get("components", []):
        component_id = str(component.get("id"))
        if component_id in positions:
            component["position_enu_m"] = positions[component_id][0]
    for port in raw.get("ports", []):
        if not isinstance(port, dict) or "accident" not in str(port.get("id", "")):
            continue
        component_id = str(port.get("component_id"))
        component_positions = positions.get(component_id)
        if not component_positions:
            continue
        port["position_enu_m"] = (
            component_positions[1]
            if str(port.get("id", "")).endswith("-2") and len(component_positions) > 1
            else component_positions[0]
        )
    manifest = EquipmentManifest.model_validate_json(json.dumps(raw, ensure_ascii=False))
    return manifest, {
        "schema_version": "prism.hazop_provider_packet_geometry_rebase.v1",
        "status": "DIAGNOSTIC_PROVIDER_EXIT_GEOMETRY_REBASED",
        "source_manifest": str(manifest_path),
        "original_component_positions": original,
        "provider_packet_positions": positions,
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "Provider packets and the generic manifest use different local coordinate origins. "
            "The diagnostic facility is rebased to the explicit provider exits so the strict "
            "port-position contract can be exercised; this is not a reviewed plant geometry."
        ),
    }


def _request_defaults(
    spec: Mapping[str, Any],
    *,
    liquid_defaults: Mapping[str, Any],
    relief_defaults: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    defaults = copy.deepcopy(dict(relief_defaults if spec["equipment_group"] == "emergency_relief" else liquid_defaults))
    defaults["source_operator"] = spec["source_operator"]
    defaults["release_termination"] = {
        "basis": "provider_declared",
        "time_s": "provider_duration",
        "provenance": "provider packet termination_basis and duration; diagnostic handoff",
    }
    if spec["equipment_group"] == "emergency_relief":
        defaults["release_termination"] = {
            "basis": "emergency_relief_discharge",
            "time_s": "provider_duration",
            "provenance": "provider emergency-relief packet termination_basis and duration",
        }
    if spec["equipment_group"] == "liquid_provider_natural_termination":
        defaults["source_duration_mode"] = "model_natural"
    if spec["equipment_group"] in {"liquid_provider", "liquid_provider_natural_termination"}:
        boundary = str(packet.get("boundary_kind", ""))
        if boundary == "resolved_atmospheric_liquid_exit" and not packet.get("no_rainout_evidence"):
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
    return defaults


def _scenario_row(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{spec['component_id']}-mode-deviation",
        "component_id": spec["component_id"],
        "component_kind": spec["component_kind"],
        "operating_modes": [spec["operating_mode"]],
        "variable_tag": spec["variable_tag"],
        "quantity": "pressure",
        "trigger": "at_or_above",
        "threshold_high_si": 600000.0,
        "scenario_family": spec["scenario_family"],
        "release_mode": spec["release_mode"],
        "priority": "high",
        "deviation_label": "mode-specific pressure deviation",
        "cause_summary": "synthetic diagnostic state reaches the declared HAZOP criterion",
        "consequence_summary": "bind the matching equipment provider packet before consequence evaluation",
        "safeguards": ["ESD", "PSV"],
        "provenance": "synthetic generic facility HAZOP diagnostic; replace with reviewed P&ID/HAZOP evidence",
    }


def _runtime_sources(specs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        component_id = str(spec["component_id"])
        tag = str(spec["variable_tag"])
        sources.append({
            "source_id": f"synthetic-multi-hazop-{component_id}",
            "source_path": "synthetic://prism/multi-equipment-hazop-provider-diagnostic",
            "source_sha256": f"{index:064x}",
            "format": "json",
            "component_id": component_id,
            "origin": "synthetic",
            "samples": [{
                "captured_at_s": 12.0,
                "operating_mode": spec["operating_mode"],
                "values": {
                    tag: {
                        "quantity": "pressure",
                        "value_si": float(spec["state_value_si"]),
                        "sensor_location": f"{component_id}.pressure",
                        "quality": "valid",
                    }
                },
            }],
        })
    return sources


def _scenario_id(spec: Mapping[str, Any]) -> str:
    return f"{spec['component_id']}-mode-deviation:{spec['operating_mode']}:{spec['scenario_family']}"


def _branch_harm(consequence: Mapping[str, Any]) -> dict[str, dict[str, list[float]]]:
    data = consequence.get("data")
    receptors = data.get("receptors", []) if isinstance(data, Mapping) else []
    output: dict[str, dict[str, list[float]]] = {}
    for receptor in receptors:
        values = receptor.get("branch_harm_low_high") if isinstance(receptor, Mapping) else None
        if not isinstance(values, list) or len(values) != 2:
            raise ValueError("provider consequence receptor lacks two branch harm endpoints")
        output[str(receptor["id"])] = {
            name: [float(values[0][name]), float(values[1][name])]
            for name in ("direct_fire", "delayed_flash_fire", "delayed_explosion", "no_ignition")
        }
    return output


def _annual_conditions(defaults: Mapping[str, Any], manifest: EquipmentManifest) -> list[dict[str, Any]]:
    population = [
        {
            "receptor_id": receptor.id,
            "persons": 1.0,
            "presence_probability": 1.0,
            "provenance": "synthetic diagnostic receptor occupancy; replace with reviewed facility population",
        }
        for receptor in manifest.receptors
    ] or [{
        "receptor_id": "worker-01",
        "persons": 1.0,
        "presence_probability": 1.0,
        "provenance": "synthetic diagnostic receptor occupancy; replace with reviewed facility population",
    }]
    return [{
        "id": "synthetic-multi-hazop-current-weather-D-3ms",
        "annual_probability": 1.0,
        "weather": copy.deepcopy(defaults["weather"]),
        "population": population,
        "provenance": "synthetic diagnostic current-weather condition; not a site weather distribution",
    }]


def _filtered_runtime_result(runtime: Mapping[str, Any], accepted_ids: Sequence[str]) -> dict[str, Any]:
    accepted = set(accepted_ids)
    result = copy.deepcopy(dict(runtime))
    result["status"] = "FACILITY_HAZOP_RUNTIME_EVALUATED"
    result["components"] = {
        component_id: row
        for component_id, row in result.get("components", {}).items()
        if component_id in accepted
    }
    result["component_count"] = len(result["components"])
    result["risk_atoms"] = [
        atom for atom in result.get("risk_atoms", [])
        if atom.get("component_id") in accepted
    ]
    result["diagnostic_scope_filter"] = {
        "accepted_component_ids": sorted(accepted),
        "withheld_component_ids": sorted(
            set(str(component_id) for component_id in runtime.get("components", {})) - accepted
        ),
        "facility_scope_complete": False,
        "reason": "facility handoff contains only branches that passed the strict runtime/provider boundary",
    }
    return result


def _build_facility_handoff(
    runtime: Mapping[str, Any],
    *,
    specs: Sequence[Mapping[str, Any]],
    events: Mapping[str, Any],
    manifest: EquipmentManifest,
    defaults: Mapping[str, Any],
) -> dict[str, Any] | None:
    accepted = [
        str(component_id)
        for component_id, row in runtime.get("components", {}).items()
        if isinstance(row, Mapping) and row.get("status") == "CONSEQUENCE_BRANCHES_EVALUATED"
    ]
    if not accepted:
        return None
    filtered = _filtered_runtime_result(runtime, accepted)
    conditions = _annual_conditions(defaults, manifest)
    bindings: list[dict[str, Any]] = []
    spec_by_id = {str(spec["component_id"]): spec for spec in specs}
    for component_id in sorted(accepted):
        spec = spec_by_id[component_id]
        row = filtered["components"][component_id]
        branch = row["branches"][0]
        consequence_result = branch["result"]
        consequence = consequence_result["consequence"]
        risk = branch.get("risk")
        if not isinstance(risk, Mapping) or risk.get("status") != "AVAILABLE_CURRENT_WEATHER_IR":
            raise ValueError(f"accepted component lacks current-weather risk binding: {component_id}")
        data = consequence.get("data", {})
        event = events[str(spec["event_id"])]
        bindings.append({
            "component_id": component_id,
            "operating_mode": spec["operating_mode"],
            "hazop_scenario_id": branch["scenario_id"],
            "event_id": str(event.id),
            "asset_id": str(event.asset_id),
            "annual_condition_id": conditions[0]["id"],
            "release_branch_id": "provider-resolved-boundary",
            "release_branch_probability": 1.0,
            "ignition_branch_probabilities": data["ignition_branch_probabilities"],
            "branch_harm_low_high": _branch_harm(consequence),
            "scenario_families": [str(branch["scenario_family"])],
        })
    handoff = build_hazop_facility_campaign_result(
        filtered,
        annual_conditions=conditions,
        scenario_bindings=bindings,
        expected_component_ids=tuple(sorted(accepted)),
    )
    handoff["diagnostic_scope_filter"] = filtered["diagnostic_scope_filter"]
    return handoff


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    manifest_path = args.manifest
    packet_paths = {
        str(spec["component_id"]): ROOT / str(spec["packet_relpath"])
        for spec in COMPONENT_SPECS
    }
    manifest, geometry_rebase = _rebase_manifest_to_packets(manifest_path, packet_paths)
    facility = manifest.to_facility()
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    events = {event.id: event for event in generate_events(facility, plan)}
    liquid_defaults = _load(args.provider_defaults_liquid)
    relief_defaults = _load(args.provider_defaults_relief)
    template_raw = _load(args.template)
    backend = IsolatedBackend(_load_backend(args.backend_config))
    service = ConsequenceService(ResearchPipeline(facility, backend))

    rows = [_scenario_row(spec) for spec in COMPONENT_SPECS]
    table = {
        "schema_version": "prism.hazop_operating_mode_selection.v1",
        "id": "generic-outdoor-lh2-hazop-multi-equipment-provider-bound-v1",
        "facility_id": facility.id,
        "operating_modes": sorted({str(spec["operating_mode"]) for spec in COMPONENT_SPECS}),
        "configuration_origin": "synthetic",
        "source_provenance": "synthetic multi-equipment HAZOP diagnostic; replace with reviewed facility HAZOP/P&ID",
        "rows": rows,
        "notes": [
            "One row per generic equipment kind is used to exercise the existing multi-component runtime coordinator.",
            "The selected operating mode is supplied by the state frame and is never inferred from pressure.",
            "Synthetic packets, horizons, geometry rebasing, and receptor occupancy remain diagnostic evidence only.",
        ],
    }
    frames_output = build_observed_state_runtime_frames(_runtime_sources(COMPONENT_SPECS))
    frames = {str(frame["component_id"]): frame for frame in frames_output["frames"]}
    bindings: dict[str, Any] = {}
    resolvers: dict[tuple[str, str], Any] = {}
    component_input: dict[str, Any] = {}
    for spec in COMPONENT_SPECS:
        component_id = str(spec["component_id"])
        packet_path = packet_paths[component_id]
        row = {
            "component_id": component_id,
            "event_id": spec["event_id"],
            "packet_path": str(packet_path),
            "packet_exists": packet_path.exists(),
        }
        if not packet_path.exists():
            row["status"] = "WITHHELD_PACKET_MISSING"
            component_input[component_id] = row
            continue
        if spec["event_id"] not in events:
            row["status"] = "WITHHELD_FREQUENCY_EVENT_MISSING"
            component_input[component_id] = row
            continue
        packet = _packet_json(packet_path)
        defaults = _request_defaults(
            spec,
            liquid_defaults=liquid_defaults,
            relief_defaults=relief_defaults,
            packet=packet,
        )
        template_payload = copy.deepcopy(template_raw)
        template_payload["component_id"] = component_id
        template = ConsequenceRequest.model_validate_json(
            json.dumps(template_payload, ensure_ascii=False)
        )
        if spec["equipment_group"] == "emergency_relief":
            release = load_provider_emergency_relief(packet_path)
            resolver = provider_release_resolver_from_packet(
                release, defaults, component_id=component_id
            )
        elif spec["equipment_group"] == "two_sided_provider":
            resolver = provider_release_set_resolver_from_packet(
                packet_path, defaults, component_id=component_id
            )
        else:
            resolver = provider_release_resolver_from_packet(
                packet_path, defaults, component_id=component_id
            )
        bindings[component_id] = SimpleNamespace(
            template=template,
            monitor=RealtimeConsequenceMonitor(service, period_s=1.0, deadline_s=30.0),
            frequency_binding=RealtimeFrequencyBinding.from_frequency_event(
                events[spec["event_id"]],
                annual_condition_probability=1.0,
                release_branch_probability=1.0,
                occupancy_probability=1.0,
            ),
        )
        resolvers[(component_id, _scenario_id(spec))] = resolver
        row.update({
            "status": "INPUTS_BOUND",
            "provider_export_schema": packet.get("provider_export_schema"),
            "provider_termination_basis": packet.get("termination_basis")
            or (
                packet.get("releases", [{}])[0].get("termination_basis")
                if isinstance(packet.get("releases"), list) and packet.get("releases")
                else None
            ),
            "provider_input_origin": packet.get("input_origin")
            or packet.get("releases", [{}])[0].get("input_origin")
            if isinstance(packet.get("releases"), list) and packet.get("releases")
            else packet.get("input_origin"),
            "scenario_id": _scenario_id(spec),
        })
        component_input[component_id] = row

    runtime_started = time.perf_counter()
    runtime = run_hazop_facility_runtime(
        table,
        frames,
        now_s=float(args.now_s),
        component_bindings=bindings,
        release_resolvers=resolvers,
    )
    runtime_elapsed_ms = (time.perf_counter() - runtime_started) * 1000.0
    accepted_ids = [
        str(component_id)
        for component_id, row in runtime.get("components", {}).items()
        if isinstance(row, dict) and row.get("status") == "CONSEQUENCE_BRANCHES_EVALUATED"
    ]
    handoff = _build_facility_handoff(
        runtime,
        specs=COMPONENT_SPECS,
        events=events,
        manifest=manifest,
        defaults=liquid_defaults,
    )
    withheld_ids = sorted(set(str(spec["component_id"]) for spec in COMPONENT_SPECS) - set(accepted_ids))
    result = {
        "schema_version": "prism.hazop_lh2_multiequipment_provider_diagnostic.v1",
        "status": "MULTI_EQUIPMENT_HAZOP_RUNTIME_EVALUATED" if accepted_ids else "MULTI_EQUIPMENT_HAZOP_RUNTIME_WITHHELD",
        "facility_id": facility.id,
        "component_count": len(COMPONENT_SPECS),
        "accepted_component_count": len(accepted_ids),
        "accepted_component_ids": sorted(accepted_ids),
        "withheld_component_count": len(withheld_ids),
        "withheld_component_ids": withheld_ids,
        "table": table,
        "frames": frames_output,
        "component_input": component_input,
        "geometry_rebase": geometry_rebase,
        "current": runtime,
        "facility_handoff": handoff,
        "processing_time": {
            "runtime_elapsed_ms": runtime_elapsed_ms,
            "total_elapsed_ms": (time.perf_counter() - started) * 1000.0,
            "component_timing": {
                component_id: [
                    branch.get("result", {})
                    .get("consequence", {})
                    .get("realtime")
                    for branch in row.get("branches", [])
                    if isinstance(branch, dict)
                    and isinstance(branch.get("result"), dict)
                    and isinstance(branch["result"].get("consequence"), dict)
                    and isinstance(branch["result"]["consequence"].get("realtime"), dict)
                ]
                for component_id, row in runtime.get("components", {}).items()
                if isinstance(row, dict)
            },
            "measurement_policy": "diagnostic wall-clock timing; no facility real-time guarantee is claimed",
        },
        "policy": {
            "operating_mode_taken_from_input": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created_by_prism": False,
            "facility_qra_promotion": False,
            "physical_validation_claim": False,
            "facility_scope_complete": False,
            "synthetic_diagnostic_inputs_present": True,
        },
        "interpretation": (
            "This record proves multi-equipment HAZOP dispatch and records the branches that cross "
            "the provider/SLABx-LH2 boundary. It is not a qualified facility annual IR/F-N result; "
            "withheld components and synthetic evidence remain part of the declared gap ledger."
        ),
    }
    _save(args.output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "examples/generic_lh2_near_receptor_manifest.json")
    parser.add_argument("--frequency-plan", type=Path, default=ROOT / "examples/generic_lh2_full_scope_frequency_plan.json")
    parser.add_argument("--provider-defaults-liquid", type=Path, default=ROOT / "examples/provider_request_defaults_liquid_provider_duration.json")
    parser.add_argument("--provider-defaults-relief", type=Path, default=ROOT / "examples/provider_emergency_relief_defaults.json")
    parser.add_argument("--template", type=Path, default=ROOT / "examples/equipment_consequence_template.json")
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--now-s", type=float, default=12.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
        raise SystemExit(f"multi-equipment HAZOP diagnostic failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "component_count": result["component_count"],
        "accepted_component_count": result["accepted_component_count"],
        "withheld_component_count": result["withheld_component_count"],
        "runtime_status": result["current"].get("status"),
        "risk_atom_count": len(result["current"].get("risk_atoms", [])),
        "facility_handoff": result["facility_handoff"] is not None,
        "facility_qra_promotion": result["policy"]["facility_qra_promotion"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
