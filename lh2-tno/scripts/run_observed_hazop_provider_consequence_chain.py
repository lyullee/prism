"""Run the strict observed-HAZOP to provider/SLABx-LH2 diagnostic chain.

The command consumes the explicit observed-mode HAZOP audit and its provider
event map.  It executes only provider packets whose actual termination and
mass contracts satisfy the selected accident family.  Withheld rows are
reported; they are never repaired by assuming a duration, isolation success,
or inventory boundary.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.consequences import ConsequenceRequest  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.hazop import run_hazop_runtime_consequence  # noqa: E402
from lh2_tno.observed_hazop_consequence_chain import (  # noqa: E402
    SCHEMA,
    audit_observed_hazop_consequence_preflight,
)
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    load_provider_emergency_relief,
    provider_release_resolver_from_packet,
)
from lh2_tno.service import (  # noqa: E402
    ConsequenceService,
    RealtimeConsequenceMonitor,
    RealtimeFrequencyBinding,
    _realtime_current_weather_risk,
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _object(path: Path) -> dict[str, Any]:
    value = _load(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} rows must be objects")
    return list(value)


def _save(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _load_backend(path: Path) -> BackendConfig:
    raw = _object(path)
    packages = raw.get("packages")
    if not isinstance(packages, list):
        raise ValueError("backend_config.packages must be an array")
    for package in packages:
        if isinstance(package, dict) and package.get("root"):
            package["sha256"] = tree_digest(Path(package["root"]))
    return BackendConfig.model_validate_json(json.dumps(raw, ensure_ascii=False))


def _rebase_manifest_to_packets(
    manifest_path: Path,
    preflight_rows: list[Mapping[str, Any]],
) -> tuple[EquipmentManifest, dict[str, Any]]:
    """Align the diagnostic generic manifest to explicit provider exits."""
    raw = _object(manifest_path)
    packet_positions: dict[str, list[float]] = {}
    for row in preflight_rows:
        path = row.get("provider_packet_path")
        component_id = str(row.get("provider_component_id") or "")
        if not path or not component_id:
            continue
        packet = _object(Path(path))
        position = packet.get("position_enu_m")
        if isinstance(position, list) and len(position) == 3:
            packet_positions[component_id] = [float(value) for value in position]
    changed_components: list[str] = []
    for component in raw.get("components", []):
        component_id = str(component.get("id"))
        position = packet_positions.get(component_id)
        if position is not None:
            component["position_enu_m"] = position
            changed_components.append(component_id)
    changed_ports: list[str] = []
    for port in raw.get("ports", []):
        port_id = str(port.get("id"))
        component_id = str(port.get("component_id"))
        if "accident" in port_id and component_id in packet_positions:
            port["position_enu_m"] = packet_positions[component_id]
            changed_ports.append(port_id)
    manifest = EquipmentManifest.model_validate_json(json.dumps(raw, ensure_ascii=False))
    return manifest, {
        "schema_version": "prism.observed_hazop_provider_geometry_rebase.v1",
        "status": "DIAGNOSTIC_PROVIDER_EXIT_GEOMETRY_REBASED",
        "changed_component_ids": sorted(set(changed_components)),
        "changed_port_ids": sorted(set(changed_ports)),
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }


def _translate_frame(frame: Mapping[str, Any], provider_component_id: str) -> dict[str, Any]:
    """Create an explicit component-identity translation for the diagnostic seam."""
    translated = copy.deepcopy(dict(frame))
    translated["component_id"] = provider_component_id
    values = translated.get("values")
    if not isinstance(values, dict):
        raise ValueError("runtime frame values must be an object")
    for value in values.values():
        if isinstance(value, dict):
            value["component_id"] = provider_component_id
    snapshot = translated.get("state_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("runtime frame state_snapshot must be an object")
    snapshot["component_id"] = provider_component_id
    translated["state_snapshot_digest"] = canonical_digest(snapshot)
    translated["frame_digest"] = canonical_digest({
        key: value for key, value in translated.items() if key != "frame_digest"
    })
    return translated


def _request_defaults(
    row: Mapping[str, Any],
    *,
    liquid_defaults: Mapping[str, Any],
    relief_defaults: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    release_mode = str(row.get("release_mode") or "")
    defaults = copy.deepcopy(
        dict(relief_defaults if release_mode == "maximum_relief_discharge" else liquid_defaults)
    )
    if release_mode == "maximum_relief_discharge":
        source_operator = "equipment_emergency_relief"
    elif packet.get("boundary_kind") == "resolved_atmospheric_liquid_exit":
        source_operator = "equipment_liquid_release"
    else:
        # Gas-unit and vaporizer-hole packets are explicit transient gas
        # histories.  They must not be routed through the liquid/two-phase
        # consequence contract merely because the observed HAZOP row also
        # carries a generic LH2 service label.
        source_operator = "integrated_transient"
    defaults["source_operator"] = source_operator
    defaults["release_termination"] = {
        "basis": "emergency_relief_discharge"
        if release_mode == "maximum_relief_discharge"
        else "provider_declared",
        "time_s": "provider_duration",
        "provenance": "provider packet termination_basis and duration",
    }
    if (
        packet.get("boundary_kind") == "resolved_atmospheric_liquid_exit"
        and not packet.get("no_rainout_evidence")
    ):
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


def _hazop_table(row: Mapping[str, Any], facility_id: str) -> dict[str, Any]:
    scenario = row["scenario"]
    provider_component_id = str(row["provider_component_id"])
    kind = str(row["provider_component_kind"])
    selected_mode = str(scenario["operating_mode"])
    hazop_row: dict[str, Any] = {
        "id": str(scenario["hazop_row_id"]),
        "component_id": provider_component_id,
        "component_kind": kind,
        "operating_modes": [selected_mode],
        "variable_tag": "pressure",
        "quantity": "pressure",
        "trigger": str(scenario["trigger"]),
        "scenario_family": str(scenario["scenario_family"]),
        "release_mode": str(scenario["release_mode"]),
        "priority": str(scenario.get("priority") or "high"),
        "deviation_label": "observed HAZOP deviation after explicit component mapping",
        "cause_summary": "observed state exceeded the mode-specific diagnostic criterion",
        "consequence_summary": "provider packet and SLABx-LH2 consequence chain",
        "provenance": "observed HAZOP diagnostic; provider geometry remains synthetic",
    }
    if scenario.get("threshold_high_si") is not None:
        hazop_row["threshold_high_si"] = float(scenario["threshold_high_si"])
    if scenario.get("threshold_low_si") is not None:
        hazop_row["threshold_low_si"] = float(scenario["threshold_low_si"])
    return {
        "schema_version": "prism.hazop_operating_mode_selection.v1",
        "id": f"observed-provider-chain-{provider_component_id}",
        "facility_id": facility_id,
        "operating_modes": [selected_mode],
        "rows": [hazop_row],
        "source_provenance": "explicit observed HAZOP scenario plus provider identity map",
        "configuration_origin": "synthetic",
        "notes": ["Component identity translation is diagnostic and does not claim site geometry validation."],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    runtime_audit = _object(args.observed_hazop_runtime_audit)
    binding_audit = _object(args.observed_hazop_provider_binding)
    worklist = _object(args.provider_worklist)
    packet_evidence = _object(args.packet_evidence)
    preflight = audit_observed_hazop_consequence_preflight(
        runtime_audit,
        binding_audit,
        worklist,
        packet_evidence,
        packet_root=args.packet_root,
    )
    selected_runtime_frames = {
        str(frame.get("source_id")): frame
        for frame in _rows(_object(args.runtime_frames).get("frames"), "runtime_frames.frames")
    }
    runtime_rows = {
        str(row.get("source_id")): row
        for row in _rows(runtime_audit.get("rows"), "runtime_audit.rows")
        if row.get("source_id")
    }
    ready_rows = [row for row in preflight["rows"] if row["status"] == "READY_FOR_PROVIDER_CHAIN"]
    manifest, geometry_rebase = _rebase_manifest_to_packets(args.manifest, preflight["rows"])
    facility = manifest.to_facility()
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    events = {event.id: event for event in generate_events(facility, plan)}
    liquid_defaults = _object(args.provider_defaults_liquid)
    relief_defaults = _object(args.provider_defaults_relief)
    template_payload = _object(args.template)
    backend = IsolatedBackend(_load_backend(args.backend_config))
    service = ConsequenceService(ResearchPipeline(facility, backend))
    packet_evidence_by_event = {
        str(row.get("provider_event_id")): row for row in preflight["rows"]
    }
    execution_rows: list[dict[str, Any]] = []
    for row in ready_rows:
        event_id = str(row["provider_event_id"])
        source_id = str(row.get("source_id") or "")
        frame = selected_runtime_frames.get(source_id)
        runtime_row = runtime_rows.get(source_id)
        if frame is None or runtime_row is None:
            row_copy = dict(row)
            row_copy.update(status="WITHHELD_RUNTIME_FRAME", blocking_reason="runtime frame source_id not found")
            execution_rows.append(row_copy)
            continue
        packet_path = Path(str(row["provider_packet_path"]))
        packet = _object(packet_path)
        provider_component_id = str(row["provider_component_id"])
        template_data = copy.deepcopy(template_payload)
        template_data["component_id"] = provider_component_id
        template = ConsequenceRequest.model_validate_json(json.dumps(template_data, ensure_ascii=False))
        defaults = _request_defaults(
            row,
            liquid_defaults=liquid_defaults,
            relief_defaults=relief_defaults,
            packet=packet,
        )
        if str(row["release_mode"]) == "maximum_relief_discharge":
            release = load_provider_emergency_relief(packet_path)
            resolver = provider_release_resolver_from_packet(
                release,
                defaults,
                component_id=provider_component_id,
                port_id=str(row["provider_port_id"]),
            )
        else:
            resolver = provider_release_resolver_from_packet(
                packet_path,
                defaults,
                component_id=provider_component_id,
                port_id=str(row["provider_port_id"]),
            )
        scenario = next(
            scenario
            for runtime_item in _rows(runtime_audit.get("rows"), "runtime_audit.rows")
            for scenario in _rows(runtime_item.get("selected_scenarios"), "selected_scenarios")
            if str(scenario.get("scenario_id")) == str(row["scenario_id"])
        )
        row_with_scenario = dict(row)
        row_with_scenario["scenario"] = scenario
        translated_frame = _translate_frame(frame, provider_component_id)
        table = _hazop_table(row_with_scenario, facility.id)
        monitor = RealtimeConsequenceMonitor(service, period_s=1.0, deadline_s=float(args.deadline_s))
        started_event = time.perf_counter()
        try:
            gate_result = run_hazop_runtime_consequence(
                table,
                translated_frame,
                now_s=float(args.now_s),
                template=template,
                monitor=monitor,
                release_resolver=resolver,
                mapping_digest=canonical_digest(binding_audit),
            )
            risk = None
            event = events.get(event_id)
            consequence = gate_result.get("consequence")
            if gate_result.get("status") == "CONSEQUENCE_EVALUATED" and isinstance(consequence, Mapping) and event is not None:
                frequency = RealtimeFrequencyBinding.from_frequency_event(
                    event,
                    annual_condition_probability=1.0,
                    release_branch_probability=1.0,
                    occupancy_probability=1.0,
                )
                risk = _realtime_current_weather_risk(consequence, frequency)
            execution_rows.append({
                **row,
                "scenario": scenario,
                "status": "EXECUTED" if gate_result.get("status") == "CONSEQUENCE_EVALUATED" else "CONSEQUENCE_WITHHELD",
                "gate_status": gate_result.get("status"),
                "gate_reason": gate_result.get("reason"),
                "risk": risk,
                "elapsed_ms": (time.perf_counter() - started_event) * 1000.0,
                "provider_input_origin": packet.get("input_origin"),
                "provider_result_digest": packet.get("provider_result_digest"),
                "provider_qualification": "UNQUALIFIED_DIAGNOSTIC",
            })
        except Exception as error:
            execution_rows.append({
                **row,
                "scenario": scenario,
                "status": "CONSEQUENCE_REJECTED",
                "error_type": type(error).__name__,
                "blocking_reason": str(error),
                "elapsed_ms": (time.perf_counter() - started_event) * 1000.0,
                "provider_qualification": "UNQUALIFIED_DIAGNOSTIC",
            })

    executed_rows = [row for row in execution_rows if row.get("status") == "EXECUTED"]
    withheld_rows = [row for row in preflight["rows"] if row["status"] != "READY_FOR_PROVIDER_CHAIN"]
    all_rows = execution_rows + withheld_rows
    risk_atoms = [
        {
            "scenario_id": row["scenario_id"],
            "operating_mode": row.get("operating_mode"),
            "provider_event_id": row.get("provider_event_id"),
            "risk": row.get("risk"),
        }
        for row in executed_rows
        if isinstance(row.get("risk"), Mapping)
    ]
    result = {
        "schema_version": SCHEMA,
        "status": (
            "OBSERVED_HAZOP_PROVIDER_CHAIN_EXECUTED_PARTIAL"
            if executed_rows and len(all_rows) > len(executed_rows)
            else "OBSERVED_HAZOP_PROVIDER_CHAIN_EXECUTED"
            if executed_rows
            else "OBSERVED_HAZOP_PROVIDER_CHAIN_WITHHELD"
        ),
        "selected_scenario_count": len(all_rows),
        "executed_scenario_count": len(executed_rows),
        "withheld_scenario_count": len(all_rows) - len(executed_rows),
        "risk_atom_count": len(risk_atoms),
        "preflight": preflight,
        "rows": all_rows,
        "risk_atoms": risk_atoms,
        "geometry_rebase": geometry_rebase,
        "processing_time": {
            "total_elapsed_ms": (time.perf_counter() - started) * 1000.0,
            "executed_case_elapsed_ms": [row.get("elapsed_ms") for row in executed_rows],
            "measurement_policy": "diagnostic wall-clock timing; no 1 Hz or site real-time guarantee",
        },
        "policy": {
            "operating_mode_taken_from_explicit_runtime_input": True,
            "frequency_assignment_performed": True if risk_atoms else False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created_by_prism": False,
            "provider_packets_are_qualified": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "facility_scope_complete": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "This run demonstrates the explicit observed-mode HAZOP to provider packet "
            "and SLABx-LH2 boundary for contract-compatible rows. Literature frequency "
            "is applied only to executed diagnostic risk atoms; it is not learned from "
            "the sensor frame. Withheld rows and unqualified packets prevent a facility "
            "annual IR/F-N claim."
        ),
    }
    _save(args.output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observed-hazop-runtime-audit", type=Path, required=True)
    parser.add_argument("--observed-hazop-provider-binding", type=Path, required=True)
    parser.add_argument("--runtime-frames", type=Path, required=True)
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--packet-evidence", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--provider-defaults-liquid", type=Path, required=True)
    parser.add_argument("--provider-defaults-relief", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--now-s", type=float, default=10081.0)
    parser.add_argument("--deadline-s", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
        raise SystemExit(f"observed HAZOP provider consequence chain failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "selected_scenario_count": result["selected_scenario_count"],
        "executed_scenario_count": result["executed_scenario_count"],
        "withheld_scenario_count": result["withheld_scenario_count"],
        "risk_atom_count": result["risk_atom_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
