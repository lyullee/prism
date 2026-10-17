"""Run the multi-equipment, header-bound LH2 facility runtime bridge.

This command is the reusable digital-twin seam for a facility that supplies
three independent inputs at once:

* state frames built from explicitly declared workbook/header units;
* an explicit supervisory operating mode for each frame; and
* a reviewed HAZOP table plus explicit provider-event mapping.

Every selected HAZOP scenario is dispatched independently to its own provider
release resolver.  The existing PRISM consequence service then calls the
SLABx-LH2 backend through the normal consequence contract and applies the
literature frequency attached to that provider event.  Missing packets or
ambiguous identities remain withheld.  The result is a current-weather,
diagnostic facility view; it never learns a frequency from telemetry and never
promotes synthetic/model-prediction packets to annual facility IR/F-N.
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
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.hazop import run_hazop_facility_runtime  # noqa: E402
from lh2_tno.observed_hazop_consequence_chain import (  # noqa: E402
    audit_observed_hazop_consequence_preflight,
)
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    load_provider_emergency_relief,
    provider_release_resolver_from_packet,
)
from lh2_tno.service import (  # noqa: E402
    ConsequenceService,
    FacilityRealtimeBinding,
    RealtimePopulationBinding,
    RealtimeConsequenceMonitor,
    RealtimeFrequencyBinding,
)

from run_inspection_center_facility_hazop_bridge import (  # noqa: E402
    _RuntimeNormalizer,
    _facility_hazop_table,
)
from run_observed_hazop_provider_consequence_chain import (  # noqa: E402
    _load_backend,
    _object,
    _rebase_manifest_to_packets,
    _request_defaults,
)


SCHEMA = "prism.inspection_center_header_bound_facility_hazop_bridge.v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return list(value)


def _scenario_index(runtime_audit: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for runtime_row in _rows(runtime_audit.get("rows"), "runtime_audit.rows"):
        for scenario in _rows(runtime_row.get("selected_scenarios"), "selected_scenarios"):
            scenario_id = str(scenario.get("scenario_id") or "").strip()
            if not scenario_id:
                raise ValueError("selected HAZOP scenario requires scenario_id")
            if scenario_id in result:
                raise ValueError(f"duplicate selected HAZOP scenario: {scenario_id}")
            result[scenario_id] = scenario
    return result


def _frame_index(runtime_frames: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for frame in _rows(runtime_frames.get("frames"), "runtime_frames.frames"):
        component_id = str(frame.get("component_id") or "").strip()
        if not component_id or component_id in result:
            raise ValueError("runtime frames require unique nonempty component_id values")
        result[component_id] = frame
    return result


def _aggregate_frequency_uncertainty(
    components: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate explicit current-weather IR bounds without imputing missing bounds.

    The provider consequence already carries p05/published/p95 IR maps when the
    literature catalogue supplies marginal frequency bounds.  This helper sums
    only those explicit maps and reports the scenario IDs that have no bounds.
    It never substitutes a default interval or treats a missing interval as
    zero uncertainty.
    """
    scenarios: list[tuple[str, Mapping[str, Any]]] = []
    published_totals: dict[str, list[float]] = {}
    bounded_totals: dict[str, dict[str, list[float]]] = {
        "p05": {},
        "published": {},
        "p95": {},
    }
    bounded_ids: list[str] = []
    missing_ids: list[str] = []
    for component_id, component in sorted(components.items()):
        if not isinstance(component, Mapping):
            continue
        for branch in component.get("branches", ()):
            if not isinstance(branch, Mapping):
                continue
            scenario_id = str(branch.get("scenario_id") or "")
            risk = branch.get("risk")
            if not scenario_id or not isinstance(risk, Mapping):
                continue
            if risk.get("status") != "AVAILABLE_CURRENT_WEATHER_IR":
                continue
            scenarios.append((scenario_id, risk))
            annual_ir = risk.get("annual_ir_low_high")
            if isinstance(annual_ir, Mapping):
                for receptor_id, endpoints in annual_ir.items():
                    if (
                        isinstance(endpoints, (list, tuple))
                        and len(endpoints) == 2
                    ):
                        total = published_totals.setdefault(str(receptor_id), [0.0, 0.0])
                        total[0] += float(endpoints[0])
                        total[1] += float(endpoints[1])
            sensitivity = risk.get("frequency_sensitivity_current_weather_ir_low_high")
            if not isinstance(sensitivity, Mapping) or not all(
                isinstance(sensitivity.get(key), Mapping)
                for key in ("p05", "published", "p95")
            ):
                missing_ids.append(scenario_id)
                continue
            bounded_ids.append(scenario_id)
            for scenario_name in ("p05", "published", "p95"):
                scenario_ir = sensitivity[scenario_name]
                for receptor_id, endpoints in scenario_ir.items():
                    if (
                        isinstance(endpoints, (list, tuple))
                        and len(endpoints) == 2
                    ):
                        total = bounded_totals[scenario_name].setdefault(
                            str(receptor_id), [0.0, 0.0]
                        )
                        total[0] += float(endpoints[0])
                        total[1] += float(endpoints[1])
    complete = bool(scenarios) and not missing_ids and len(bounded_ids) == len(scenarios)
    return {
        "schema_version": "prism.header_bound_frequency_uncertainty.v1",
        "status": (
            "COMPLETE_CURRENT_WEATHER_FREQUENCY_UNCERTAINTY"
            if complete
            else "PARTIAL_CURRENT_WEATHER_FREQUENCY_UNCERTAINTY"
            if bounded_ids
            else "WITHHELD_CURRENT_WEATHER_FREQUENCY_UNCERTAINTY"
        ),
        "risk_atom_count": len(scenarios),
        "frequency_bound_scenario_count": len(bounded_ids),
        "frequency_unbound_scenario_count": len(missing_ids),
        "frequency_bound_scenario_ids": bounded_ids,
        "frequency_unbound_scenario_ids": missing_ids,
        "complete": complete,
        "current_weather_annual_ir_low_high": published_totals or None,
        "bounded_current_weather_ir_low_high": (
            bounded_totals if bounded_ids else None
        ),
        "frequency_inference_performed": False,
        "missing_bounds_imputed": False,
        "interpretation": (
            "p05/published/p95 values are summed only for branches whose provider "
            "frequency binding exposes all three explicit bounds; branches without "
            "bounds remain visible and are not assigned an assumed interval"
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    runtime_frames_record = _object(args.runtime_frames)
    frames = _frame_index(runtime_frames_record)
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
    ready_rows = [
        row for row in preflight["rows"]
        if row.get("status") == "READY_FOR_PROVIDER_CHAIN"
    ]
    scenario_by_id = _scenario_index(runtime_audit)

    table_set = _object(args.hazop_table_set)
    hazop_table = _facility_hazop_table(table_set)
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
    liquid_defaults = _object(args.provider_defaults_liquid)
    relief_defaults = _object(args.provider_defaults_relief)
    population_binding = None
    if args.population_binding is not None:
        population_payload = _object(args.population_binding)
        population_binding = RealtimePopulationBinding(
            persons_by_receptor=population_payload["persons_by_receptor"],
            provenance=str(population_payload["provenance"]),
            source_digest=str(population_payload["source_digest"]),
        )

    # Build one resolver and one frequency binding per selected scenario.  The
    # key includes the observed component so two components can never share a
    # release packet merely because their scenario names happen to match.
    resolvers: dict[tuple[str, str], Any] = {}
    frequency_by_scenario: dict[str, RealtimeFrequencyBinding] = {}
    provider_by_scenario: dict[str, Mapping[str, Any]] = {}
    for row in ready_rows:
        scenario_id = str(row["scenario_id"])
        scenario = scenario_by_id.get(scenario_id)
        if scenario is None:
            continue
        component_id = str(scenario.get("component_id") or "")
        packet_path = Path(str(row["provider_packet_path"]))
        packet = _object(packet_path)
        defaults = _request_defaults(
            row,
            liquid_defaults=liquid_defaults,
            relief_defaults=relief_defaults,
            packet=packet,
        )
        if str(row.get("release_mode")) == "maximum_relief_discharge":
            release = load_provider_emergency_relief(packet_path)
            resolver = provider_release_resolver_from_packet(
                release,
                defaults,
                component_id=str(row["provider_component_id"]),
                port_id=str(row["provider_port_id"]),
            )
        else:
            resolver = provider_release_resolver_from_packet(
                packet_path,
                defaults,
                component_id=str(row["provider_component_id"]),
                port_id=str(row["provider_port_id"]),
            )
        resolvers[(component_id, scenario_id)] = resolver
        provider_by_scenario[scenario_id] = row
        event = events.get(str(row["provider_event_id"]))
        if event is None:
            raise ValueError(
                f"provider event is missing from the declared frequency plan: {row['provider_event_id']}"
            )
        frequency_by_scenario[scenario_id] = RealtimeFrequencyBinding.from_frequency_event(
            event,
            annual_condition_probability=1.0,
            release_branch_probability=1.0,
            occupancy_probability=1.0,
        )

    bindings: dict[str, FacilityRealtimeBinding] = {}
    for component_id, frame in sorted(frames.items()):
        selected = [
            scenario
            for scenario in scenario_by_id.values()
            if str(scenario.get("component_id")) == component_id
        ]
        selected_ids = [str(scenario.get("scenario_id")) for scenario in selected]
        provider_component_ids_by_scenario = {
            scenario_id: str(provider_by_scenario[scenario_id]["provider_component_id"])
            for scenario_id in selected_ids
            if scenario_id in provider_by_scenario
            and provider_by_scenario[scenario_id].get("provider_component_id") is not None
        }
        provider_component_ids = set(provider_component_ids_by_scenario.values())
        provider_component_id = (
            next(iter(provider_component_ids))
            if len(selected_ids) == 1 and provider_component_ids
            else None
        )
        template_data = copy.deepcopy(template_payload)
        template_data["component_id"] = component_id
        template = ConsequenceRequest.model_validate_json(
            json.dumps(template_data, ensure_ascii=False, allow_nan=False)
        )
        bindings[component_id] = FacilityRealtimeBinding(
            component_id=component_id,
            template=template,
            monitor=RealtimeConsequenceMonitor(
                service, period_s=1.0, deadline_s=float(args.deadline_s)
            ),
            normalizer=_RuntimeNormalizer(),
            pressure_tag="pressure",
            temperature_tag="temperature",
            frequency_binding=(
                frequency_by_scenario.get(selected_ids[0])
                if len(selected_ids) == 1 else None
            ),
            scenario_frequency_bindings=(
                {
                    scenario_id: frequency_by_scenario[scenario_id]
                    for scenario_id in selected_ids
                    if scenario_id in frequency_by_scenario
                }
                if len(selected_ids) > 1 else None
            ),
            provider_component_id=provider_component_id,
            provider_component_ids_by_scenario=(
                provider_component_ids_by_scenario
                if len(selected_ids) > 1
                else None
            ),
        )

    result = run_hazop_facility_runtime(
        hazop_table,
        frames,
        now_s=float(args.now_s),
        component_bindings=bindings,
        release_resolvers=resolvers,
        mapping_digest=canonical_digest(binding_audit),
        population_binding=population_binding,
    )
    frequency_uncertainty = _aggregate_frequency_uncertainty(
        result.get("components", {})
    )
    result["conditional_current_weather_frequency_uncertainty"] = frequency_uncertainty
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    component_rows = result.get("components", {})
    selected_count = sum(
        int(row.get("selection", {}).get("selected_scenario_count", 0))
        for row in component_rows.values()
        if isinstance(row, Mapping) and isinstance(row.get("selection"), Mapping)
    )
    executed_count = sum(
        str(row.get("status", "")).startswith("CONSEQUENCE_BRANCHES_EVALUATED")
        for row in component_rows.values()
        if isinstance(row, Mapping)
    )
    state_handoff = []
    for component_id, frame in sorted(frames.items()):
        snapshot = frame.get("state_snapshot")
        selected_scenario_ids = [
            str(s.get("scenario_id"))
            for s in scenario_by_id.values()
            if str(s.get("component_id")) == component_id
        ]
        provider_identities = {
            scenario_id: {
                "component_id": str(provider_by_scenario[scenario_id]["provider_component_id"]),
                "port_id": str(provider_by_scenario[scenario_id]["provider_port_id"]),
            }
            for scenario_id in selected_scenario_ids
            if scenario_id in provider_by_scenario
        }
        state_handoff.append({
            "observed_component_id": component_id,
            "source_id": frame.get("source_id"),
            "captured_at_s": frame.get("captured_at_s"),
            "origin": frame.get("origin"),
            "state_snapshot_digest": frame.get("state_snapshot_digest"),
            "selected_scenario_ids": selected_scenario_ids,
            "provider_identities_by_scenario": provider_identities,
            "provider_identity": (
                next(iter(provider_identities.values()))
                if len(provider_identities) == 1
                else None
            ),
        })
    result = {
        **result,
        "schema_version": SCHEMA,
        "input_evidence": {
            "runtime_frames": str(args.runtime_frames),
            "observed_hazop_runtime_audit": str(args.observed_hazop_runtime_audit),
            "observed_hazop_provider_binding": str(args.observed_hazop_provider_binding),
            "provider_worklist": str(args.provider_worklist),
            "packet_evidence": str(args.packet_evidence),
            "population_binding": (
                str(args.population_binding)
                if args.population_binding is not None
                else None
            ),
            "geometry_rebase": geometry_rebase,
        },
        "preflight": preflight,
        "facility_bridge_audit": {
            "status": "MULTI_EQUIPMENT_HEADER_BOUND_FACILITY_RUNTIME_EXECUTED_DIAGNOSTIC",
            "component_count": len(bindings),
            "selected_component_count": selected_count,
            "executed_component_count": executed_count,
            "ready_provider_scenario_count": len(ready_rows),
            "withheld_provider_scenario_count": len(preflight["rows"]) - len(ready_rows),
            "state_snapshot_handoff": state_handoff,
            "operating_mode_taken_from_explicit_input": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created_by_prism": False,
            "provider_packets_qualified": False,
            "facility_annual_ir_available": False,
            "facility_fn_available": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "population_binding_supplied": population_binding is not None,
            "conditional_current_weather_expected_death_fn": copy.deepcopy(
                result.get("conditional_current_weather_expected_death_fn")
            ),
            "conditional_current_weather_expected_death_fn_available": (
                isinstance(
                    result.get("conditional_current_weather_expected_death_fn"),
                    Mapping,
                )
                and result["conditional_current_weather_expected_death_fn"].get(
                    "status"
                ) == "AVAILABLE_CONDITIONAL_CURRENT_WEATHER_EXPECTED_DEATH_FN"
            ),
            "frequency_uncertainty_status": frequency_uncertainty["status"],
            "frequency_uncertainty_complete": frequency_uncertainty["complete"],
            "frequency_bound_scenario_count": frequency_uncertainty[
                "frequency_bound_scenario_count"
            ],
            "frequency_unbound_scenario_count": frequency_uncertainty[
                "frequency_unbound_scenario_count"
            ],
            "diagnostic_only": True,
            "wall_elapsed_ms": elapsed_ms,
            "measurement_policy": (
                "diagnostic synchronous wall-clock timing for this batch; "
                "not a fresh-physics 1 Hz guarantee"
            ),
        },
        "interpretation": (
            "Explicit header-bound state frames for all declared components entered one "
            "facility HAZOP runtime batch. Each selected mode/scenario retained its own "
            "provider component, port, release history, SLABx-LH2 consequence and "
            "literature frequency binding. The output is a current-weather diagnostic "
            "view; model-prediction packets, missing qualification and physical validation "
            "keep annual facility IR/F-N promotion withheld."
        ),
    }
    _save(args.output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-frames", type=Path, required=True)
    parser.add_argument("--hazop-table-set", type=Path, required=True)
    parser.add_argument("--observed-hazop-runtime-audit", type=Path, required=True)
    parser.add_argument("--observed-hazop-provider-binding", type=Path, required=True)
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--packet-evidence", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--provider-defaults-liquid", type=Path, required=True)
    parser.add_argument("--provider-defaults-relief", type=Path, required=True)
    parser.add_argument(
        "--population-binding",
        type=Path,
        default=None,
        help=(
            "optional explicit receptor population binding for a conditional "
            "current-weather expected-death F/N diagnostic"
        ),
    )
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--now-s", type=float, default=20000.0)
    parser.add_argument("--deadline-s", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
        raise SystemExit(f"header-bound facility HAZOP bridge failed: {error}") from error
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
