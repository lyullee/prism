"""Compile mixed LH2 provider families into one explicit RiskCampaign.

The generic campaign compiler historically accepted one provider family and
one request context at a time.  A real outdoor LH2 facility has accidental
holes, emergency relief, inventory-defined gas releases, and two-sided
ruptures in the same frequency plan.  This adapter chooses the operator and
termination context from each already validated provider boundary, then uses
the normal exact event binder.  It never creates a missing packet or assigns a
frequency to a packet outside the worklist.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.campaign import AnnualCondition  # noqa: E402
from lh2_tno.campaign_template import build_equipment_campaign_from_event_catalog  # noqa: E402
from lh2_tno.equipment_boundary import (  # noqa: E402
    ResolvedGasRelease,
    ResolvedGasReleaseSet,
    ResolvedLiquidRelease,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    ProviderReleaseContractError,
    build_consequence_request_from_provider_release,
    build_consequence_request_from_provider_release_set,
    load_provider_emergency_relief_catalog,
    load_provider_release_catalog,
    load_provider_release_set_catalog,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_port_position(manifest: EquipmentManifest, port_id: str) -> list[float]:
    matches = [port for port in manifest.ports if port.id == port_id]
    if len(matches) != 1 or matches[0].position_enu_m is None:
        raise ProviderReleaseContractError(
            f"manifest must declare one positioned port for provider port {port_id}"
        )
    return list(matches[0].position_enu_m)


def _rebase_release_position(
    release: ResolvedGasRelease | ResolvedLiquidRelease,
    manifest: EquipmentManifest,
) -> ResolvedGasRelease | ResolvedLiquidRelease:
    """Apply an explicit facility-port placement to a generic provider packet.

    The provider packet owns thermodynamics and its outlet history; the
    manifest owns where that outlet sits in the facility.  This opt-in rebase
    is required for synthetic generic packets whose placeholder coordinates do
    not match the target facility geometry.
    """
    position = _manifest_port_position(manifest, release.port_id)
    payload = release.model_dump(mode="json")
    payload["position_enu_m"] = position
    payload["provider_boundary_reference"] = (
        f"{release.provider_boundary_reference}; explicit placement from manifest port "
        f"{release.port_id}"
    )
    return type(release).model_validate_json(json.dumps(payload, allow_nan=False))


def _rebase_release_set_position(
    release_set: ResolvedGasReleaseSet,
    manifest: EquipmentManifest,
) -> ResolvedGasReleaseSet:
    payload = release_set.model_dump(mode="json")
    payload["releases"] = [
        _rebase_release_position(release, manifest).model_dump(mode="json")
        for release in release_set.releases
    ]
    payload["inventory_provenance"] = (
        f"{release_set.inventory_provenance}; explicit endpoint placement from facility manifest ports"
    )
    return ResolvedGasReleaseSet.model_validate_json(json.dumps(payload, allow_nan=False))


def _provider_clock_context(release: ResolvedGasRelease | ResolvedLiquidRelease | ResolvedGasReleaseSet) -> dict[str, Any]:
    if isinstance(release, ResolvedGasReleaseSet):
        basis = {endpoint.termination_basis for endpoint in release.releases}
        if len(basis) != 1:
            raise ProviderReleaseContractError("two-sided provider endpoints must share one termination basis")
        provider_basis = next(iter(basis))
        if provider_basis != "two_sided_rupture":
            raise ProviderReleaseContractError("two-sided mixed campaign requires two_sided_rupture termination basis")
        return {
            "component_id": release.component_id,
            "available_mass_kg": release.available_mass_kg,
            "source_position_enu_m": list(release.positions_enu_m[0]),
            "source_positions_enu_m": [list(position) for position in release.positions_enu_m],
            "source_operator": "equipment_two_sided_rupture",
            "release_termination": {
                "basis": "provider_declared",
                "time_s": "provider_duration",
                "provenance": "mixed provider catalog two-sided rupture termination; provider clock retained",
            },
        }

    if isinstance(release, ResolvedLiquidRelease):
        operator = (
            "equipment_liquid_over_600s"
            if release.termination_basis == "inventory_over_600s"
            else "equipment_liquid_release"
        )
    elif release.event_kind == "emergency_relief":
        operator = "equipment_emergency_relief"
    elif release.termination_basis == "inventory_depletion":
        operator = "equipment_inventory_depletion"
    elif release.termination_basis == "inventory_over_600s":
        operator = "equipment_inventory_over_600s"
    else:
        operator = "integrated_transient"

    # Older synthetic hole packets predate an explicit termination basis.  A
    # fixed diagnostic horizon is an explicit declaration; it is never
    # inferred from the source history and never promotes the packet.
    basis = release.termination_basis or "synthetic_diagnostic_horizon"
    return {
        "component_id": release.component_id,
        "available_mass_kg": release.available_mass_kg,
        "source_position_enu_m": list(release.position_enu_m),
        "source_operator": operator,
        "release_termination": {
            "basis": "provider_declared" if release.termination_basis else basis,
            "time_s": "provider_duration",
            "provenance": "mixed provider catalog termination context; provider duration retained",
        },
    }


def _request_for_release(
    release: ResolvedGasRelease | ResolvedLiquidRelease | ResolvedGasReleaseSet,
    base_defaults: dict[str, Any],
    manifest: EquipmentManifest,
    *,
    rebase_positions: bool,
) -> Any:
    if rebase_positions:
        release = (
            _rebase_release_set_position(release, manifest)
            if isinstance(release, ResolvedGasReleaseSet)
            else _rebase_release_position(release, manifest)
        )
    defaults = copy.deepcopy(base_defaults)
    defaults.update(_provider_clock_context(release))
    if isinstance(release, ResolvedGasReleaseSet):
        return build_consequence_request_from_provider_release_set(release, defaults)
    return build_consequence_request_from_provider_release(release, defaults)


def compile_campaign(args: argparse.Namespace) -> Any:
    manifest = EquipmentManifest.from_json(args.manifest)
    frequency_plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    defaults = _load_json(args.request_defaults)
    if not isinstance(defaults, dict):
        raise ValueError("request defaults must be a JSON object")
    if args.pool_radius_m is not None:
        if args.pool_radius_m <= 0.0:
            raise ValueError("pool radius must be positive")
        radius = float(args.pool_radius_m)
        defaults["pool"] = {
            "footprint_origin": "declared_sensitivity",
            "fluid": "Hydrogen",
            "fluid_translation": "none",
            "radius_m": radius,
            "conductivity_w_mk": 0.6,
            "diffusivity_m2_s": 1.5e-7,
            "initial_temperature_k": 288.15,
            "domain_radius_m": radius * 10.0,
            "radial_step_m": radius / 5.0,
            "maximum_time_step_s": 0.01,
        }
    conditions_raw = _load_json(args.annual_conditions)
    rows = conditions_raw.get("conditions") if isinstance(conditions_raw, dict) else conditions_raw
    if not isinstance(rows, list):
        raise ValueError("annual conditions must be an array or an object with conditions")
    conditions = tuple(
        AnnualCondition.model_validate_json(json.dumps(row, ensure_ascii=False, allow_nan=False))
        for row in rows
    )

    releases: list[ResolvedGasRelease | ResolvedLiquidRelease | ResolvedGasReleaseSet] = []
    releases.extend(load_provider_release_catalog(args.accidental_catalog))
    releases.extend(load_provider_emergency_relief_catalog(args.emergency_relief_catalog))
    releases.extend(load_provider_release_set_catalog(args.two_sided_catalog))
    if len({release.event_id for release in releases}) != len(releases):
        raise ValueError("mixed provider catalogs must have unique event_id values")
    request_by_event = {
        release.event_id: _request_for_release(
            release,
            defaults,
            manifest,
            rebase_positions=args.rebase_positions,
        )
        for release in releases
    }
    campaign = build_equipment_campaign_from_event_catalog(
        manifest,
        frequency_plan,
        request_by_event,
        conditions,
        scope_provenance=args.scope_provenance,
        maximum_physics_cases=args.maximum_physics_cases,
    )
    return campaign, len(releases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--accidental-catalog", type=Path, required=True)
    parser.add_argument("--emergency-relief-catalog", type=Path, required=True)
    parser.add_argument("--two-sided-catalog", type=Path, required=True)
    parser.add_argument("--request-defaults", type=Path, required=True)
    parser.add_argument("--annual-conditions", type=Path, required=True)
    parser.add_argument("--scope-provenance", required=True)
    parser.add_argument(
        "--rebase-positions",
        action="store_true",
        help="explicitly place generic provider outlets at matching manifest ports",
    )
    parser.add_argument(
        "--pool-radius-m",
        type=float,
        help="opt-in declared_sensitivity pool footprint for a diagnostic run",
    )
    parser.add_argument("--maximum-physics-cases", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        campaign, provider_packet_count = compile_campaign(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProviderReleaseContractError, ValueError, TypeError) as error:
        raise SystemExit(f"mixed LH2 provider campaign input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(campaign.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    matched = sum(branch.request is not None for route in campaign.event_routes for branch in route.branches)
    uncomputed = sum(branch.request is None for route in campaign.event_routes for branch in route.branches)
    print(json.dumps({
        "status": "COMPILED",
        "output": str(args.output),
        "event_count": len(campaign.event_routes),
        "matched_request_branch_count": matched,
        "uncomputed_branch_count": uncomputed,
        "physics_executed": False,
        "provider_packet_count": provider_packet_count,
        "promotion_policy": "synthetic and qualified provider evidence remain separate; compilation does not assign new frequency",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
