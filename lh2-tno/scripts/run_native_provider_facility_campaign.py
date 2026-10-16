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

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_boundary import ResolvedLiquidRelease  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    build_consequence_request_from_provider_release,
    load_provider_release,
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


def _request_defaults(context: dict[str, Any], packet: Any) -> dict[str, Any]:
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
    defaults["source_operator"] = "equipment_liquid_release" if is_liquid else "integrated_transient"
    defaults["source_duration_mode"] = "declared"
    defaults["release_termination"] = {
        "basis": "reviewed_isolation_success",
        "time_s": "provider_duration",
        "provenance": "native provider isolation clock retained for multi-packet facility diagnostic",
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
            provenance="catalogue point estimates retained as fixed where no complete published p05/p95 bounds exist",
        ),)
    return tuple(
        LiteratureFrequencyScenario(
            id=identifier,
            asset_quantiles={
                asset: quantile if complete[asset] else "fixed"
                for asset in sorted(by_asset)
            },
            provenance=(
                "published within-asset frequency sensitivity; assets without complete "
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


def run(args: argparse.Namespace) -> dict[str, Any]:
    packets = [load_provider_release(path) for path in args.packets]
    if not packets:
        raise ValueError("at least one provider packet is required")
    if len({packet.component_id for packet in packets}) != len(packets):
        raise ValueError("one packet per facility component is required")
    for packet in packets:
        if not isinstance(packet, ResolvedLiquidRelease) and packet.compressible_plane_handoff is None:
            raise ValueError(f"gas packet {packet.event_id} lacks compressible_plane_handoff")
    context = _object(args.request_context)
    manifest = EquipmentManifest.from_json(args.manifest)
    facility = manifest.to_facility()
    packet_components = {packet.component_id for packet in packets}
    if not packet_components <= {component.id for component in facility.components}:
        raise ValueError("every provider packet component must be present in the facility manifest")
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    events = generate_events(facility, plan)
    matched: dict[str, tuple[Any, Any]] = {}
    for packet in packets:
        event = _packet_event_match(packet, list(events))
        if event.id in {value[0].id for value in matched.values()}:
            raise ValueError("multiple provider packets resolve to one frequency event")
        matched[packet.component_id] = (event, packet)
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
            request = build_consequence_request_from_provider_release(
                packet, _request_defaults(context, packet)
            )
            release_kind = "liquid" if isinstance(packet, ResolvedLiquidRelease) else "gas"
            branch = {
                "id": f"native-provider-{release_kind}-packet",
                "probability_given_event": 1.0,
                "provenance": f"native external {release_kind} provider packet; exact component/opening match; diagnostic only",
                "request": request.model_dump(mode="json"),
            }
        routes.append({"event_id": event.id, "branches": [branch]})
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
    verification = {
        "schema_version": "prism.native_provider_multi_equipment_facility_campaign.v1",
        "status": "NATIVE_PROVIDER_MULTI_EQUIPMENT_FACILITY_CAMPAIGN_EXECUTED_DIAGNOSTIC",
        "facility_id": facility.id,
        "component_ids": sorted(packet_components),
        "packet_count": len(packets),
        "matched_event_ids": [event.id for event, _packet in matched.values()],
        "event_count": len(result.get("events", [])),
        "case_count": len(result_cases),
        "executed_case_count": sum(1 for case in result_cases if str(case.get("status", "")).startswith("EXECUTED")),
        "uncomputed_case_count": sum(1 for case in withheld if case.get("status") == "UNCOMPUTED"),
        "operator_limited_case_count": sum(1 for case in withheld if str(case.get("status", "")).startswith("EXECUTED_OPERATOR_LIMITED")),
        "withheld_case_count": len(withheld),
        "risk_atom_count": len(result.get("risk_atoms", [])),
        "conditional_diagnostic_facility_risk_available": assessment.get("conditional_diagnostic_facility_risk_available"),
        "facility_total_risk_available": assessment.get("facility_total_risk_available"),
        "frequency_scenario_count": len(assessment.get("frequency_uncertainty", {}).get("scenarios", [])),
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "campaign_elapsed_ms": elapsed_ms,
        "packet_digests": [
            {
                "component_id": packet.component_id,
                "event_id": packet.event_id,
                "provider_packet_digest": canonical_digest(packet.model_dump(mode="json")),
                "provider_result_digest": packet.provider_result_digest,
                "termination_basis": packet.termination_basis,
            }
            for packet in packets
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
