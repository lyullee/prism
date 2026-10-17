"""Run multiple native gas/liquid provider packets in one facility campaign.

Each packet must already contain its provider-owned release history and explicit
termination boundary. The runner only matches packet identity and opening to
the facility frequency catalogue; it never invents a missing packet or
frequency bound. Unmatched frequency events remain ``UNCOMPUTED``.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def _display_path(path: Path) -> str:
    """Serialize workspace paths portably instead of embedding host paths."""

    try:
        value = path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        value = path
    return str(value).replace("\\", "/")

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_boundary import (  # noqa: E402
    ResolvedGasReleaseSet,
    ResolvedLiquidRelease,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    build_consequence_request_from_provider_release,
    build_consequence_request_from_provider_release_set,
    load_provider_emergency_relief,
    load_provider_release,
    load_provider_release_set,
)
from lh2_tno.uncertainty import LiteratureFrequencyScenario  # noqa: E402


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{path} must contain an array of objects")
    return value


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _request_defaults(
    context: dict[str, Any], packet: Any, *, event: Any | None = None
) -> dict[str, Any]:
    """Copy shared consequence inputs without overriding provider release data."""
    defaults = copy.deepcopy(context)
    for key in (
        "component_id", "available_mass_kg", "source_position_enu_m",
        "source_positions_enu_m", "source_input", "resolved_release",
        "resolved_release_set", "resolved_liquid_release",
        "annual_frequency_per_year", "annual_frequency_provenance",
        "frequency_event", "initiation_intensity_per_s",
    ):
        defaults.pop(key, None)
    is_liquid = isinstance(packet, ResolvedLiquidRelease)
    is_two_sided = isinstance(packet, ResolvedGasReleaseSet)
    packet_termination_basis = getattr(packet, "termination_basis", None)
    if getattr(packet, "event_kind", "accidental_leak") == "emergency_relief":
        defaults["source_operator"] = "equipment_emergency_relief"
    elif is_two_sided:
        defaults["source_operator"] = "equipment_two_sided_rupture"
    elif getattr(packet, "termination_basis", None) == "inventory_depletion":
        defaults["source_operator"] = (
            "equipment_liquid_release" if is_liquid else "equipment_inventory_depletion"
        )
    elif getattr(packet, "termination_basis", None) == "inventory_over_600s":
        defaults["source_operator"] = (
            "equipment_liquid_over_600s" if is_liquid else "equipment_inventory_over_600s"
        )
    else:
        defaults["source_operator"] = "equipment_liquid_release" if is_liquid else "integrated_transient"
    defaults["source_duration_mode"] = (
        "model_natural"
        if packet_termination_basis == "model_pressure_equalization"
        else "declared"
    )
    # HAZOP identity is copied only from an exact reviewed event binding.  The
    # campaign never derives a mode from equipment type, pressure, or release
    # physics.
    if event is not None:
        if event.operating_mode is not None:
            defaults["operating_mode"] = event.operating_mode
            defaults["hazop_scenario_id"] = event.hazop_scenario_id
    defaults["release_termination"] = {
        "basis": (
            "emergency_relief_discharge"
            if getattr(packet, "event_kind", "accidental_leak") == "emergency_relief"
            else "two_sided_rupture"
            if is_two_sided
            else packet_termination_basis
            if packet_termination_basis in {
                "inventory_depletion",
                "inventory_over_600s",
                "model_pressure_equalization",
            }
            else "reviewed_isolation_success"
        ),
        "time_s": "provider_duration",
        "provenance": (
            "native provider emergency-relief duration retained for multi-packet facility diagnostic"
            if getattr(packet, "event_kind", "accidental_leak") == "emergency_relief"
            else "native provider two-sided endpoint histories retained for multi-packet facility diagnostic"
            if is_two_sided
            else "native provider inventory termination retained for multi-packet facility diagnostic"
            if packet_termination_basis in {"inventory_depletion", "inventory_over_600s"}
            else "native provider pressure-equalization termination retained for multi-packet facility diagnostic"
            if packet_termination_basis == "model_pressure_equalization"
            else "native provider isolation clock retained for multi-packet facility diagnostic"
        ),
    }
    if is_liquid:
        integrated_mass = float(packet.integrated_mass_kg)
        radius = 0.0001 if integrated_mass < 1.0e-4 else 0.005 if integrated_mass < 0.1 else 0.05
        defaults["pool"] = {
            "footprint_origin": "declared_sensitivity",
            "fluid": packet.property_basis.fluid,
            "radius_m": radius,
            "conductivity_w_mk": 0.6,
            "diffusivity_m2_s": 1.5e-7,
            "initial_temperature_k": packet.ambient_temperature_k,
            "domain_radius_m": max(0.005, 5.0 * radius) if radius < 0.001 else max(0.25, 5.0 * radius),
            "radial_step_m": radius / 20.0,
            "maximum_time_step_s": 0.01,
        }
    return defaults


def _facility_frequency_scenarios(events: list[dict[str, Any]]) -> tuple[LiteratureFrequencyScenario, ...]:
    """Use bounds only where every event in an asset has published bounds."""
    by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_asset[str(event.get("asset_id", ""))].append(event)
    complete = {
        asset: bool(rows) and all(
            row.get("marginal_p05_per_year") is not None
            and row.get("marginal_p95_per_year") is not None
            for row in rows
        )
        for asset, rows in by_asset.items()
    }
    if not any(complete.values()):
        return (LiteratureFrequencyScenario(
            id="native-provider-facility-fixed",
            asset_quantiles={asset: "fixed" for asset in sorted(by_asset)},
            provenance="no frequency inference; catalogue point estimates retained as fixed where no complete published p05/p95 bounds exist",
        ),)
    return tuple(
        LiteratureFrequencyScenario(
            id=identifier,
            asset_quantiles={
                asset: quantile if complete[asset] else "fixed"
                for asset in sorted(by_asset)
            },
            provenance=(
                "no frequency inference; published within-asset frequency sensitivity; assets without complete "
                "p05/p95 bounds retain their catalogue point estimate as fixed"
            ),
        )
        for identifier, quantile in (
            ("native-provider-facility-published", "published"),
            ("native-provider-facility-p05", "p05"),
            ("native-provider-facility-p95", "p95"),
        )
    )


def _packet_event_match(packet: Any, events: list[Any]) -> Any:
    if isinstance(packet, ResolvedGasReleaseSet):
        matches = [
            event for event in events
            if event.id == packet.event_id
            and event.model_component_id == packet.component_id
            and event.release.mode == "two_sided_rupture"
            and event.port_ids is not None
            and tuple(event.port_ids) == tuple(release.port_id for release in packet.releases)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"two-sided packet {packet.event_id} must match exactly one facility event; found {len(matches)}"
            )
        return matches[0]
    if getattr(packet, "event_kind", "accidental_leak") == "emergency_relief":
        matches = [
            event for event in events
            if event.model_component_id == packet.component_id
            and event.release.mode == "maximum_relief_discharge"
        ]
        if len(matches) != 1:
            raise ValueError(
                f"emergency-relief packet {packet.event_id} must match exactly one facility event; found {len(matches)}"
            )
        return matches[0]
    if getattr(packet, "failure_opening_diameter_m", None) is None:
        # Inventory events have no random-hole diameter.  They bind by the
        # exact event identity and provider-owned termination basis instead of
        # reconstructing an opening from the outlet history.
        basis_to_mode = {
            "inventory_depletion": "instantaneous_inventory",
            "inventory_over_600s": "inventory_over_600s",
        }
        release_mode = basis_to_mode.get(getattr(packet, "termination_basis", None))
        matches = [
            event for event in events
            if event.id == packet.event_id
            and event.model_component_id == packet.component_id
            and event.release.mode == release_mode
        ]
        if len(matches) != 1:
            raise ValueError(
                f"inventory packet {packet.event_id} must match exactly one facility event; found {len(matches)}"
            )
        return matches[0]
    matches = [
        event for event in events
        if event.model_component_id == packet.component_id
        and event.release.mode == "hole"
        and event.release.hole_diameter_m is not None
        and math.isclose(
            event.release.hole_diameter_m,
            packet.failure_opening_diameter_m,
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            f"packet {packet.event_id} must match exactly one facility event; found {len(matches)}"
        )
    return matches[0]


def _has_explicit_provider_source_states(packet: Any) -> bool:
    """Return whether a gas packet has provider-owned source states per step.

    A compressible-plane handoff remains mandatory for high-speed gas paths.
    Low-speed atmospheric gas exits may use the ordinary SLABx-LH2 route only
    when every interval retains the upstream provider state, so PRISM never
    reconstructs a near-field state from outlet flow alone.
    """
    if getattr(packet, "boundary_kind", None) != "resolved_atmospheric_gas_exit":
        return False
    steps = getattr(packet, "steps", ())
    return bool(steps) and all(
        getattr(step, "provider_source_state", None) is not None for step in steps
    )


def _dynamic_state_closure_dump(packet: Any) -> dict[str, Any] | None:
    """Return provider closure evidence without treating it as qualification."""
    mass_balance = getattr(packet, "provider_mass_balance", None)
    closure = getattr(mass_balance, "dynamic_state_closure", None)
    return closure.model_dump(mode="json") if closure is not None else None


def _bind_hazop_event_modes(
    events: tuple[Any, ...], path: Path | None,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Attach exact reviewed HAZOP mode/scenario labels to catalogue events.

    A missing binding stays missing.  This deliberately rejects component-only
    or release-only matches because those would silently turn a qualitative
    HAZOP decision into an inferred operating mode.
    """
    if path is None:
        return events, {
            "status": "NOT_SUPPLIED",
            "path": None,
            "bound_event_count": 0,
            "unbound_event_count": len(events),
            "orphan_binding_count": 0,
            "binding_digest": None,
        }
    raw = _object(path)
    rows = raw.get("event_rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("HAZOP binding file must contain an event_rows array")
    event_by_id = {event.id: event for event in events}
    binding_by_id: dict[str, dict[str, Any]] = {}
    orphan_count = 0
    for row in rows:
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("HAZOP binding rows require a nonempty event_id")
        if event_id in binding_by_id:
            raise ValueError(f"duplicate HAZOP binding for event {event_id}")
        event = event_by_id.get(event_id)
        if event is None:
            orphan_count += 1
            continue
        if row.get("component_id") != event.model_component_id:
            raise ValueError(f"HAZOP binding component mismatch for event {event_id}")
        if row.get("release_mode") != event.release.mode:
            raise ValueError(f"HAZOP binding release-mode mismatch for event {event_id}")
        mode = row.get("operating_mode")
        scenario = row.get("hazop_scenario_id")
        if not isinstance(mode, str) or not mode.strip():
            raise ValueError(f"HAZOP binding operating_mode missing for event {event_id}")
        if not isinstance(scenario, str) or not scenario.strip():
            raise ValueError(f"HAZOP binding hazop_scenario_id missing for event {event_id}")
        binding_by_id[event_id] = {
            "operating_mode": mode,
            "hazop_scenario_id": scenario,
        }
    bound_rows = []
    for event in events:
        update = binding_by_id.get(event.id)
        if update is None:
            bound_rows.append(event)
        elif hasattr(event, "model_copy"):
            bound_rows.append(event.model_copy(update=update))
        else:  # small test doubles can use attribute copies too
            clone = copy.copy(event)
            for key, value in update.items():
                setattr(clone, key, value)
            bound_rows.append(clone)
    bound_events = tuple(bound_rows)
    return bound_events, {
        "status": "EXACT_REVIEWED_BINDING",
        "path": str(path).replace("\\", "/"),
        "bound_event_count": len(binding_by_id),
        "unbound_event_count": len(events) - len(binding_by_id),
        "orphan_binding_count": orphan_count,
        "binding_digest": canonical_digest(raw),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    packets = []
    for path in args.packets:
        raw = _object(path)
        if raw.get("provider_export_schema") == "prism.resolved_release_set.v1":
            packets.append(load_provider_release_set(path))
        elif raw.get("event_kind") == "emergency_relief":
            packets.append(load_provider_emergency_relief(path))
        else:
            packets.append(load_provider_release(path))
    if not packets:
        raise ValueError("at least one provider packet is required")
    for packet in packets:
        if (
            not isinstance(packet, (ResolvedLiquidRelease, ResolvedGasReleaseSet))
            and packet.event_kind != "emergency_relief"
        ):
            if packet.compressible_plane_handoff is None and not _has_explicit_provider_source_states(packet):
                raise ValueError(
                    f"gas packet {packet.event_id} lacks compressible_plane_handoff "
                    "and complete provider_source_state rows"
                )
    context = _object(args.request_context)
    manifest = EquipmentManifest.from_json(args.manifest)
    facility = manifest.to_facility()
    packet_components = {packet.component_id for packet in packets}
    if not packet_components <= {component.id for component in facility.components}:
        raise ValueError("every provider packet component must be present in the facility manifest")
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    events = generate_events(facility, plan)
    events, hazop_binding = _bind_hazop_event_modes(events, args.hazop_event_mode_binding)
    matched: dict[str, tuple[Any, Any]] = {}
    for packet in packets:
        event = _packet_event_match(packet, list(events))
        if event.id in {value[0].id for value in matched.values()}:
            raise ValueError("multiple provider packets resolve to one frequency event")
        matched[packet.event_id] = (event, packet)
    routes = []
    for event in events:
        entry = next((pair for pair in matched.values() if pair[0].id == event.id), None)
        if entry is None:
            branch = {
                "id": "uncomputed-opening-bin",
                "probability_given_event": 1.0,
                "provenance": "no native provider packet for this opening bin",
                "uncomputed_reason": "provider release evidence is not supplied for this event",
            }
        else:
            packet = entry[1]
            if isinstance(packet, ResolvedGasReleaseSet):
                request = build_consequence_request_from_provider_release_set(
                    packet, _request_defaults(context, packet, event=event)
                )
            else:
                request = build_consequence_request_from_provider_release(
                    packet, _request_defaults(context, packet, event=event)
                )
            release_kind = "liquid" if isinstance(packet, ResolvedLiquidRelease) else "gas"
            branch = {
                "id": f"native-provider-{release_kind}-packet",
                "probability_given_event": 1.0,
                "provenance": f"native external {release_kind} provider packet; exact component/opening match; diagnostic only",
                "request": request.model_dump(mode="json"),
            }
        route = {"event_id": event.id, "branches": [branch]}
        if event.operating_mode is not None:
            route["operating_mode"] = event.operating_mode
            route["hazop_scenario_id"] = event.hazop_scenario_id
        routes.append(route)
    campaign_raw = {
        "id": "native-provider-multi-equipment-facility-campaign",
        "frequency_plan": plan.model_dump(mode="json"),
        "annual_conditions": _array(args.annual_conditions),
        "event_routes": routes,
        "scope_provenance": "multiple native provider packets bound to exact facility events; unmatched bins remain withheld",
        "maximum_physics_cases": args.maximum_physics_cases,
    }
    campaign = RiskCampaign.model_validate_json(json.dumps(campaign_raw, ensure_ascii=False, allow_nan=False))
    config_raw = _object(args.backend_config)
    for pin in config_raw.get("packages", []):
        if isinstance(pin, dict) and isinstance(pin.get("root"), str):
            pin["sha256"] = tree_digest(Path(pin["root"]))
    config = BackendConfig.model_validate_json(json.dumps(config_raw, ensure_ascii=False, allow_nan=False))
    started = time.perf_counter()
    result = ResearchPipeline(facility, IsolatedBackend(config)).facility_risk(campaign)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    result_events = result.get("events", [])
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=tuple(component.id for component in facility.components),
        frequency_scenarios=_facility_frequency_scenarios(result_events),
    )
    result_cases = result.get("cases", [])
    withheld = result.get("uncomputed_cases", [])
    matched_event_ids = {event.id for event, _packet in matched.values()}
    case_rows = [*result_cases, *withheld]
    case_event_ids = {
        str(case.get("event_id"))
        for case in case_rows
        if case.get("event_id") is not None
    }
    executed_event_ids = {
        str(case.get("event_id"))
        for case in result_cases
        if str(case.get("status", "")).startswith("EXECUTED")
    }
    atom_expected_event_ids = {
        str(case.get("event_id"))
        for case in case_rows
        if str(case.get("status", "")).startswith("EXECUTED")
    }
    risk_atom_event_ids = {
        str(atom.get("event_id"))
        for atom in result.get("risk_atoms", [])
    }
    missing_case_events = sorted(matched_event_ids - case_event_ids)
    missing_atom_events = sorted(atom_expected_event_ids - risk_atom_event_ids)
    if missing_case_events or missing_atom_events:
        raise ValueError(
            "matched provider event did not close the case-to-risk-atom chain: "
            f"missing_cases={missing_case_events}, missing_atoms={missing_atom_events}"
        )
    verification = {
        "schema_version": "prism.native_provider_multi_equipment_facility_campaign.v1",
        "status": "NATIVE_PROVIDER_MULTI_EQUIPMENT_FACILITY_CAMPAIGN_EXECUTED_DIAGNOSTIC",
        "facility_id": facility.id,
        "component_ids": sorted(packet_components),
        "packet_count": len(packets),
        "matched_event_ids": [event.id for event, _packet in matched.values()],
        "matched_event_case_chain_closed": not missing_case_events,
        "matched_event_risk_atom_chain_closed": not missing_atom_events,
        "matched_event_chain_closed": not (missing_case_events or missing_atom_events),
        "matched_event_executed_case_count": len(matched_event_ids & executed_event_ids),
        "matched_event_case_record_count": len(matched_event_ids & case_event_ids),
        "matched_event_uncomputed_case_count": sum(
            1 for case in case_rows
            if str(case.get("event_id")) in matched_event_ids
            and str(case.get("status", "")) == "UNCOMPUTED"
        ),
        "matched_event_failed_case_count": sum(
            1 for case in case_rows
            if str(case.get("event_id")) in matched_event_ids
            and str(case.get("status", "")) == "FAILED"
        ),
        "matched_event_withheld_case_count": sum(
            1 for case in withheld
            if str(case.get("event_id")) in matched_event_ids
        ),
        "matched_event_risk_atom_event_count": len(matched_event_ids & risk_atom_event_ids),
        "event_count": len(result.get("events", [])),
        "case_count": len(result_cases),
        "executed_case_count": sum(1 for case in result_cases if str(case.get("status", "")).startswith("EXECUTED")),
        "uncomputed_case_count": sum(1 for case in withheld if case.get("status") == "UNCOMPUTED"),
        "failed_case_count": sum(1 for case in case_rows if str(case.get("status", "")) == "FAILED"),
        "operator_limited_case_count": sum(1 for case in withheld if str(case.get("status", "")).startswith("EXECUTED_OPERATOR_LIMITED")),
        "withheld_case_count": len(withheld),
        "risk_atom_count": len(result.get("risk_atoms", [])),
        "conditional_diagnostic_facility_risk_available": assessment.get("conditional_diagnostic_facility_risk_available"),
        "facility_total_risk_available": assessment.get("facility_total_risk_available"),
        "facility_qra_blocking_reasons": assessment.get(
            "qualified_facility_qra_blocking_reasons", []
        ),
        "frequency_scenario_count": len(assessment.get("frequency_uncertainty", {}).get("scenarios", [])),
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "hazop_event_mode_binding": hazop_binding,
        "campaign_elapsed_ms": elapsed_ms,
        "packet_digests": [
            {
                "component_id": packet.component_id,
                "port_id": (
                    packet.port_id if not isinstance(packet, ResolvedGasReleaseSet) else None
                ),
                "port_ids": (
                    [release.port_id for release in packet.releases]
                    if isinstance(packet, ResolvedGasReleaseSet) else [packet.port_id]
                ),
                "event_id": packet.event_id,
                "release_kind": "liquid" if isinstance(packet, ResolvedLiquidRelease) else "gas",
                "event_kind": (
                    "two_sided_rupture"
                    if isinstance(packet, ResolvedGasReleaseSet)
                    else packet.event_kind
                ),
                "position_enu_m": list(
                    packet.positions_enu_m[0]
                    if isinstance(packet, ResolvedGasReleaseSet) else packet.position_enu_m
                ),
                "positions_enu_m": (
                    [list(position) for position in packet.positions_enu_m]
                    if isinstance(packet, ResolvedGasReleaseSet) else [list(packet.position_enu_m)]
                ),
                "failure_opening_diameter_m": (
                    packet.failure_opening_diameter_m
                    if not isinstance(packet, ResolvedGasReleaseSet)
                    else None
                ),
                "failure_opening_diameters_m": (
                    [release.failure_opening_diameter_m for release in packet.releases]
                    if isinstance(packet, ResolvedGasReleaseSet) else None
                ),
                "duration_s": packet.duration_s,
                "available_mass_kg": packet.available_mass_kg,
                "cumulative_mass_out_kg": packet.cumulative_mass_out_kg,
                "integrated_mass_kg": packet.integrated_mass_kg,
                "mass_residual_kg": packet.cumulative_mass_out_kg - packet.integrated_mass_kg,
                "provider_packet_digest": canonical_digest(packet.model_dump(mode="json")),
                "provider_result_digest": packet.provider_result_digest,
                "packet_path": _display_path(args.packets[index]),
                "termination_basis": (
                    "two_sided_rupture"
                    if isinstance(packet, ResolvedGasReleaseSet)
                    else packet.termination_basis
                ),
                "termination_provenance": (
                    packet.inventory_provenance
                    if isinstance(packet, ResolvedGasReleaseSet)
                    else packet.termination_provenance
                ),
                "dynamic_state_closure": _dynamic_state_closure_dump(packet),
            }
            for index, packet in enumerate(packets)
        ],
        "limitations": [
            "provider packets, facility geometry, weather and population remain synthetic or diagnostic",
            "unmatched frequency opening bins remain UNCOMPUTED and are not assigned zero risk",
            "pump catalogue rates without p05/p95 bounds remain fixed rather than receiving invented uncertainty",
            "provider qualification and independent physical validation are not claimed",
            "facility IR/F-N promotion remains closed",
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _save(args.output_dir / "facility.json", facility.model_dump(mode="json"))
    _save(args.output_dir / "frequency_plan.json", plan.model_dump(mode="json"))
    _save(args.output_dir / "campaign.json", campaign.model_dump(mode="json"))
    _save(args.output_dir / "campaign_result.json", result)
    _save(args.output_dir / "facility_assessment.json", assessment)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packets", type=Path, nargs="+", required=True)
    parser.add_argument("--request-context", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--annual-conditions", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--maximum-physics-cases", type=int, default=30)
    parser.add_argument(
        "--hazop-event-mode-binding", type=Path, default=None,
        help="Reviewed event_rows JSON; modes are copied only on exact event/component/release matches",
    )
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ImportError, TypeError, ValueError) as error:
        raise SystemExit(f"native provider multi-equipment campaign failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "packet_count": result["packet_count"],
        "executed_case_count": result["executed_case_count"],
        "uncomputed_case_count": result["uncomputed_case_count"],
        "risk_atom_count": result["risk_atom_count"],
        "output": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
