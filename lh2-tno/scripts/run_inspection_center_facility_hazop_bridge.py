"""Run the reconstructed three-component facility HAZOP/runtime bridge.

This example exercises the *facility* coordinator rather than the standalone
observed-provider runner.  It keeps the three reconstructed state frames in
their observed component identities, combines their explicit mode-specific
HAZOP rows into one facility table, and translates only the selected supply
vaporizer branch to the explicitly mapped provider component.  Receiving and
standby remain normal and therefore never call a provider resolver.

The generated record is diagnostic: the input frames and provider packet are
reconstructed/model-prediction evidence, and the table thresholds are
synthetic.  The bridge therefore exposes conditional current-weather IR only
and keeps facility annual IR/F-N promotion false.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from lh2_tno.backend import IsolatedBackend  # noqa: E402
from lh2_tno.consequences import ConsequenceRequest  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.hazop import run_hazop_facility_runtime  # noqa: E402
from lh2_tno.observed_hazop_consequence_chain import (  # noqa: E402
    audit_observed_hazop_consequence_preflight,
)
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import provider_release_resolver_from_packet  # noqa: E402
from lh2_tno.resolved_liquid_worker import dynamic_state_closure_status  # noqa: E402
from lh2_tno.state_snapshot import EquipmentStateSnapshot  # noqa: E402
from lh2_tno.service import (  # noqa: E402
    ConsequenceService,
    FacilityRealtimeBinding,
    FacilityRealtimeConsequenceMonitor,
    RealtimeConsequenceMonitor,
    RealtimeFrequencyBinding,
)

from run_observed_hazop_provider_consequence_chain import (  # noqa: E402
    _load_backend,
    _object,
    _rebase_manifest_to_packets,
    _request_defaults,
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class _RuntimeNormalizer:
    """Marker adapter: runtime HAZOP frames already contain canonical state."""

    def normalize(self, *_args, **_kwargs):  # pragma: no cover - guarded seam
        raise AssertionError("state-only HAZOP bridge must not normalize historian rows")


def _facility_hazop_table(table_set: Mapping[str, Any]) -> dict[str, Any]:
    tables = table_set.get("tables")
    if not isinstance(tables, Mapping) or not tables:
        raise ValueError("HAZOP table set must contain nonempty tables")
    rows: list[dict[str, Any]] = []
    modes: set[str] = set()
    for component_id, table in tables.items():
        if not isinstance(table, Mapping):
            raise ValueError(f"HAZOP table is not an object: {component_id}")
        table_rows = table.get("rows")
        if not isinstance(table_rows, list):
            raise ValueError(f"HAZOP table rows are not an array: {component_id}")
        for row in table_rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"HAZOP row is not an object: {component_id}")
            copied = copy.deepcopy(dict(row))
            if copied.get("component_id") != component_id:
                raise ValueError(
                    f"HAZOP row component identity mismatch: {component_id}"
                )
            rows.append(copied)
            modes.update(str(mode) for mode in copied.get("operating_modes", ()))
    return {
        "schema_version": "prism.hazop_operating_mode_selection.v1",
        "id": "inspection-center-facility-hazop-diagnostic-v1",
        "facility_id": "generic-outdoor-lh2-diagnostic",
        "operating_modes": sorted(modes),
        "configuration_origin": "synthetic",
        "source_provenance": (
            "explicit union of the reconstructed component HAZOP tables; "
            "thresholds remain diagnostic pending facility P&ID/HAZOP review"
        ),
        "rows": rows,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    operation_sequence_evidence = None
    operation_sequence_path = getattr(args, "operation_sequence_evidence", None)
    if operation_sequence_path is not None:
        operation_sequence_evidence = _object(Path(operation_sequence_path))
        if operation_sequence_evidence.get("schema_version") != (
            "prism.inspection_center_operation_sequence_evidence.v1"
        ):
            raise ValueError("operation sequence evidence has an unexpected schema")
        if operation_sequence_evidence.get("promotion_gates", {}).get(
            "release_boundary_closed", True
        ):
            raise ValueError("operation sequence evidence cannot claim a closed release boundary")
    runtime_frames_record = _object(args.runtime_frames)
    frame_rows = runtime_frames_record.get("frames")
    if not isinstance(frame_rows, list) or not frame_rows:
        raise ValueError("runtime_frames.frames must be a nonempty array")
    frames = {}
    for frame in frame_rows:
        if not isinstance(frame, Mapping):
            raise ValueError("runtime frame must be an object")
        component_id = str(frame.get("component_id") or "")
        if not component_id or component_id in frames:
            raise ValueError("runtime frame component IDs must be unique and nonempty")
        frames[component_id] = frame

    table_set = _object(args.hazop_table_set)
    hazop_table = _facility_hazop_table(table_set)
    runtime_audit = _object(args.observed_hazop_runtime_audit)
    binding_audit = _object(args.observed_hazop_provider_binding)
    provider_worklist = _object(args.provider_worklist)
    packet_evidence = _object(args.packet_evidence)
    preflight = audit_observed_hazop_consequence_preflight(
        runtime_audit,
        binding_audit,
        provider_worklist,
        packet_evidence,
        packet_root=args.packet_root,
    )
    ready = [row for row in preflight["rows"] if row["status"] == "READY_FOR_PROVIDER_CHAIN"]
    if len(ready) != 1:
        raise ValueError(f"expected exactly one ready diagnostic provider row, got {len(ready)}")
    provider_row = ready[0]
    scenario_id = str(provider_row["scenario_id"])
    scenario = next(
        scenario
        for runtime_row in runtime_audit["rows"]
        for scenario in runtime_row.get("selected_scenarios", [])
        if str(scenario.get("scenario_id")) == scenario_id
    )
    packet_path = Path(str(provider_row["provider_packet_path"]))
    packet = _object(packet_path)
    provider_dynamic_state_closure = dynamic_state_closure_status(packet)
    defaults = _request_defaults(
        provider_row,
        liquid_defaults=_object(args.provider_defaults_liquid),
        relief_defaults=_object(args.provider_defaults_relief),
        packet=packet,
    )
    provider_component_id = str(provider_row["provider_component_id"])
    provider_port_id = str(provider_row["provider_port_id"])
    resolver = provider_release_resolver_from_packet(
        packet_path,
        defaults,
        component_id=provider_component_id,
        port_id=provider_port_id,
    )

    # The reconstructed facility manifest has a generic diagnostic position.
    # Rebase only the explicitly mapped provider component/port to the packet's
    # declared exit position, exactly as the standalone chain does.  This is a
    # diagnostic geometry operation; it does not infer a site position.
    manifest, geometry_rebase = _rebase_manifest_to_packets(
        args.manifest, preflight["rows"]
    )
    facility = manifest.to_facility()
    backend = IsolatedBackend(_load_backend(args.backend_config))
    service = ConsequenceService(ResearchPipeline(facility, backend))
    template_payload = _object(args.template)
    frequency_plan = FrequencyPlan.model_validate_json(
        args.frequency_plan.read_text(encoding="utf-8")
    )
    events = {event.id: event for event in generate_events(facility, frequency_plan)}
    event = events.get(str(provider_row["provider_event_id"]))
    if event is None:
        raise ValueError("provider event is missing from the declared frequency plan")
    frequency_binding = RealtimeFrequencyBinding.from_frequency_event(
        event,
        annual_condition_probability=1.0,
        release_branch_probability=1.0,
        occupancy_probability=1.0,
    )

    bindings: dict[str, FacilityRealtimeBinding] = {}
    for component_id in sorted(frames):
        template_payload_for_component = copy.deepcopy(template_payload)
        template_payload_for_component["component_id"] = component_id
        template = ConsequenceRequest.model_validate_json(
            json.dumps(template_payload_for_component, allow_nan=False)
        )
        is_supply = component_id == str(scenario["component_id"])
        bindings[component_id] = FacilityRealtimeBinding(
            component_id=component_id,
            template=template,
            monitor=RealtimeConsequenceMonitor(
                service, period_s=1.0, deadline_s=float(args.deadline_s)
            ),
            normalizer=_RuntimeNormalizer(),
            pressure_tag="pressure",
            temperature_tag="temperature",
            frequency_binding=frequency_binding if is_supply else None,
            provider_component_id=provider_component_id if is_supply else None,
        )

    facility_monitor = FacilityRealtimeConsequenceMonitor(
        bindings,
        facility_id=str(hazop_table["facility_id"]),
    )
    result = facility_monitor.update_from_runtime_frames_with_hazop(
        hazop_table,
        frames,
        now_s=float(args.now_s),
        release_resolvers={scenario_id: resolver},
        mapping_digest=canonical_digest(binding_audit),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    components = result.get("components", {})
    selected = [
        component
        for component in components.values()
        if isinstance(component, Mapping)
        and isinstance(component.get("selection"), Mapping)
        and component["selection"].get("status") == "SCENARIOS_SELECTED"
    ]
    executed = [
        component
        for component in selected
        if str(component.get("status", "")).startswith("CONSEQUENCE_BRANCHES_EVALUATED")
    ]
    state_snapshot_handoff: list[dict[str, Any]] = []
    for component_id, frame in sorted(frames.items()):
        snapshot = frame.get("state_snapshot")
        if not isinstance(snapshot, Mapping):
            raise ValueError(f"runtime frame has no state_snapshot: {component_id}")
        snapshot_model = EquipmentStateSnapshot.from_mapping(snapshot)
        declared_digest = frame.get("state_snapshot_digest")
        if declared_digest != snapshot_model.digest():
            raise ValueError(f"runtime frame state_snapshot_digest mismatch: {component_id}")
        state_snapshot_handoff.append(
            {
                "observed_component_id": component_id,
                "state_snapshot_schema": snapshot_model.schema_version,
                "state_snapshot_digest": snapshot_model.digest(),
                "captured_at_s": snapshot_model.captured_at_s,
                "origin": snapshot_model.origin,
                "quality": snapshot_model.quality,
                "provider_component_id": (
                    provider_component_id if component_id == str(scenario["component_id"]) else None
                ),
                "provider_port_id": (
                    provider_port_id if component_id == str(scenario["component_id"]) else None
                ),
                "provider_state_snapshot_echo": False,
                "qualification_status": "WITHHELD_PROVIDER_ECHO_NOT_CONFIRMED",
            }
        )
    result = dict(result)
    for component in result.get("components", {}).values():
        if not isinstance(component, Mapping):
            continue
        for branch in component.get("branches", ()):
            if isinstance(branch, dict) and str(branch.get("scenario_id") or "") == scenario_id:
                branch["provider_dynamic_state_closure"] = copy.deepcopy(
                    provider_dynamic_state_closure
                )
    result.update(
        {
            "schema_version": "prism.inspection_center_facility_hazop_bridge.v1",
            "input_evidence": {
                "runtime_frames": str(args.runtime_frames),
                "hazop_table_set": str(args.hazop_table_set),
                "provider_binding": str(args.observed_hazop_provider_binding),
                "provider_packet": str(packet_path),
                "geometry_rebase": geometry_rebase,
                "runtime_origin_counts": {
                    str(origin): sum(
                        frame.get("origin") == origin for frame in frames.values()
                    )
                    for origin in sorted({str(frame.get("origin")) for frame in frames.values()})
                },
            },
            "facility_bridge_audit": {
                "status": "FACILITY_RUNTIME_BRIDGE_EXECUTED_DIAGNOSTIC",
                "component_count": len(bindings),
                "selected_component_count": len(selected),
                "executed_component_count": len(executed),
                "withheld_normal_component_ids": [
                    component_id
                    for component_id, component in components.items()
                    if isinstance(component, Mapping)
                    and component.get("status") in {
                        "WITHHELD_HAZOP_NO_DEVIATION",
                        "WITHHELD_HAZOP_NO_APPLICABLE_MODE_ROW",
                    }
                ],
                "explicit_provider_component_mapping": {
                    "observed_component_id": str(scenario["component_id"]),
                    "provider_component_id": provider_component_id,
                    "provider_port_id": provider_port_id,
                    "scenario_id": scenario_id,
                    "mapping_digest": canonical_digest(binding_audit),
                },
                "state_snapshot_handoff": state_snapshot_handoff,
                "operation_sequence_evidence_bound": operation_sequence_evidence is not None,
                "operating_mode_inferred": False,
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "provider_release_created_by_prism": False,
                "provider_dynamic_state_closure": copy.deepcopy(
                    provider_dynamic_state_closure
                ),
                "facility_annual_ir_available": False,
                "facility_fn_available": False,
                "facility_qra_claim": False,
                "physical_validation_claim": False,
                "diagnostic_only": True,
                "wall_elapsed_ms": elapsed_ms,
                "measurement_policy": (
                    "diagnostic synchronous wall-clock timing for this batch; "
                    "not a fresh-physics 1 Hz guarantee"
                ),
            },
            "interpretation": (
                "Three reconstructed component state frames entered one facility HAZOP "
                "bridge. Receiving and standby were withheld as normal; the explicit "
                "supply deviation selected one vaporizer-hole scenario and translated "
                "only that branch to ambient-vaporizer-01 before the SLABx-LH2/TNO chain. "
                "The provider packet is model-prediction diagnostic evidence, so annual "
                "facility IR/F-N promotion remains false."
            ),
        }
    )
    if operation_sequence_evidence is not None:
        result["input_evidence"]["operation_sequence_evidence"] = {
            "path": str(operation_sequence_path),
            "schema_version": operation_sequence_evidence["schema_version"],
            "status": operation_sequence_evidence.get("status"),
            "source_sha256": operation_sequence_evidence.get("source", {}).get("sha256"),
            "selected_row_count": operation_sequence_evidence.get("source", {}).get(
                "row_count_selected"
            ),
            "observed_relief_setpoint_candidate_pa": operation_sequence_evidence.get(
                "operating_sequence", {}
            ).get("observed_relief_setpoint_candidate_pa"),
            "observed_operational_close_threshold_candidate_pa": operation_sequence_evidence.get(
                "operating_sequence", {}
            ).get("observed_operational_close_threshold_candidate_pa"),
            "release_boundary_closed": operation_sequence_evidence.get(
                "promotion_gates", {}
            ).get("release_boundary_closed"),
            "frequency_applied": operation_sequence_evidence.get("promotion_gates", {}).get(
                "frequency_applied"
            ),
        }
    _save(args.output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-frames", type=Path, default=ROOT / "examples/inspection_center_reconstructed_runtime_frames.json")
    parser.add_argument("--hazop-table-set", type=Path, default=ROOT / "examples/inspection_center_hazop_runtime_tables.json")
    parser.add_argument("--observed-hazop-runtime-audit", type=Path, default=ROOT / "examples/inspection_center_reconstructed_hazop_runtime_audit.json")
    parser.add_argument("--observed-hazop-provider-binding", type=Path, default=ROOT / "examples/inspection_center_reconstructed_hazop_provider_event_binding.json")
    parser.add_argument("--provider-worklist", type=Path, default=ROOT / "results/20261110/native_full_scope_frequency_assessment_latest2/provider_worklist.json")
    parser.add_argument("--packet-evidence", type=Path, default=ROOT / "results/20261110/observed_hazop_storage_vaporizer_isolation_overlay/packet_evidence.json")
    parser.add_argument("--packet-root", type=Path, default=ROOT / "results/20261110/native_generic_scope_packets_latest2")
    parser.add_argument("--manifest", type=Path, default=ROOT / "examples/generic_lh2_full_scope_manifest.json")
    parser.add_argument("--frequency-plan", type=Path, default=ROOT / "results/20261110/native_full_scope_frequency_assessment_latest2/frequency_plan.json")
    parser.add_argument("--provider-defaults-liquid", type=Path, default=ROOT / "examples/provider_request_defaults_liquid.json")
    parser.add_argument("--provider-defaults-relief", type=Path, default=ROOT / "examples/provider_emergency_relief_defaults.json")
    parser.add_argument("--template", type=Path, default=ROOT / "examples/equipment_consequence_template.json")
    parser.add_argument("--backend-config", type=Path, default=ROOT / "results/20261008/full_chain/backend_config.json")
    parser.add_argument("--operation-sequence-evidence", type=Path)
    parser.add_argument("--now-s", type=float, default=43200.0)
    parser.add_argument("--deadline-s", type=float, default=180.0)
    parser.add_argument("--output", type=Path, default=ROOT / "examples/inspection_center_facility_hazop_bridge.json")
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
        raise SystemExit(f"inspection-center facility HAZOP bridge failed: {error}") from error
    print(json.dumps({
        "status": result.get("status"),
        "component_count": result.get("component_count"),
        "risk_atom_count": len(result.get("risk_atoms", [])),
        "facility_annual_ir_available": result.get("facility_annual_ir_available"),
        "facility_fn_available": result.get("facility_fn_available"),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
