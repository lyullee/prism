"""Rebind provider-owned inventory depletion to the vertical-handoff chain.

The source inventory campaign already contains a finite provider ledger and a
positive depletion threshold.  This command reuses that exact history for the
five vertical area bins, attaches the declared horizontal handoff section, and
runs the ordinary PRISM consequence chain.  It does not infer a frequency or
claim that the synthetic handoff is physically validated.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.contracts import Facility  # noqa: E402
from lh2_tno.equipment_boundary import ResolvedGasRelease  # noqa: E402
from lh2_tno.equipment_release_adapter import (  # noqa: E402
    build_resolved_gas_release_from_provider_response,
)
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _load_backend_with_current_source_pins(path: Path) -> BackendConfig:
    """Refresh package tree digests before running a provider-backed campaign.

    The campaign input is intentionally historical, while the provider source
    trees are shared working trees.  Recomputing each existing package pin at
    execution time prevents a stale artifact digest from being mistaken for a
    different provider revision.  The refreshed pins are kept in memory only;
    the historical backend JSON is not rewritten.
    """

    raw = _load(path)
    packages = raw.get("packages", [])
    if not isinstance(packages, list):
        raise ValueError(f"{path}: packages must be a list")
    refreshed: list[str] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        root_value = package.get("root")
        if not isinstance(root_value, str):
            continue
        root = Path(root_value)
        if not root.exists():
            raise FileNotFoundError(
                f"{path}: configured provider package root does not exist: {root}"
            )
        package["sha256"] = tree_digest(root)
        refreshed.append(str(package.get("name", root)))
    if not refreshed:
        raise ValueError(f"{path}: no provider package roots were found")
    # JSON validation accepts the tuple-shaped package collection from the
    # persisted artifact while preserving the strict BackendConfig schema.
    return BackendConfig.model_validate_json(json.dumps(raw))


def _suffix(event_id: str) -> str:
    marker = "/terminal-valve/"
    if marker not in event_id:
        raise ValueError(f"vertical event has no terminal-valve area suffix: {event_id}")
    return event_id.split(marker, 1)[1]


def _handoff(release: ResolvedGasRelease) -> dict[str, Any]:
    """Build an explicit, mass-closing handoff section for each release step."""

    h2_fraction = 0.9
    half_width = 0.02
    velocity = 5.0
    states: list[dict[str, Any]] = []
    for step in release.steps:
        # The carrier section is a declared adapter input.  Its depth is solved
        # only to close the provider mass-flow identity; it is not a vertical
        # free-jet validation or a field measurement.
        depth = step.mass_flow_kg_s / (
            h2_fraction * step.density_kg_m3 * velocity * 2.0 * half_width
        )
        states.append(
            {
                "time_s": step.time_s,
                "direction_enu": [1.0, 0.0, 0.0],
                "velocity_m_s": velocity,
                "density_kg_m3": step.density_kg_m3,
                "temperature_k": step.temperature_k,
                "h2_mass_fraction": h2_fraction,
                "half_width_m": half_width,
                "depth_m": max(depth, 1.0e-12),
                "provenance": (
                    "synthetic provider vertical-to-horizontal handoff; "
                    "not independently validated"
                ),
            }
        )
    first = states[0]
    return {
        "position_enu_m": [0.0, 0.0, 2.0],
        "direction_enu": first["direction_enu"],
        "velocity_m_s": first["velocity_m_s"],
        "density_kg_m3": first["density_kg_m3"],
        "temperature_k": first["temperature_k"],
        "h2_mass_fraction": first["h2_mass_fraction"],
        "half_width_m": first["half_width_m"],
        "depth_m": first["depth_m"],
        "provenance": (
            "synthetic provider vertical-to-horizontal handoff; "
            "not independently validated"
        ),
        "states": states,
    }


def _build_release(
    event_id: str,
    source_response: dict[str, Any],
    source_release: dict[str, Any],
    failure_opening_diameter_m: float,
) -> ResolvedGasRelease:
    response = copy.deepcopy(source_response)
    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"{event_id}: inventory provider response has no data object")
    data.update(
        {
            "event_id": event_id,
            "component_id": "terminal_pipe",
            "port_id": "terminal_pipe.out",
            "provider_meta": {
                "initial_mass_kg": data["available_mass_kg"],
                "cumulative_mass_in_kg": 0.0,
                "final_mass_kg": data["remaining_inventory_kg"],
                "residual_mass_kg": data["max_total_mass_residual_kg"],
                "available_mass_definition": (
                    "provider-owned positive-threshold finite reserve; "
                    "synthetic diagnostic inventory, not site inventory"
                ),
            },
            "termination_provenance": (
                "provider-owned homogeneous finite-storage inventory threshold; "
                "vertical handoff adapter remains synthetic"
            ),
        }
    )
    release = build_resolved_gas_release_from_provider_response(
        response,
        component_id="terminal_pipe",
        port_id="terminal_pipe.out",
        event_id=event_id,
        provider_source_digest=source_release["provider_source_digest"],
        provider_result=response,
        provider_result_digest=source_release["provider_result_digest"],
        upstream_service_provenance=(
            "provider-owned homogeneous finite-storage inventory valve; "
            "native atmospheric gas boundary"
        ),
        provider_boundary_reference=(
            "DynamicNetworkSimulator homogeneous tank to atmospheric inventory valve"
        ),
        input_origin="synthetic",
        position_enu_m=[0.0, 0.0, 1.0],
        # Build the flat packet first; the strict contract requires the
        # handoff adapter to be present before a vertical outlet direction is
        # accepted.  The packet is revalidated with the vertical direction
        # immediately after the handoff is attached below.
        direction_enu=[1.0, 0.0, 0.0],
        ambient_pressure_pa_abs=100000.0,
        ambient_temperature_k=288.15,
        failure_opening_diameter_m=failure_opening_diameter_m,
    )
    raw = release.model_dump(mode="json")
    raw["direction_enu"] = [0.0, 0.0, 1.0]
    raw["vertical_handoff"] = _handoff(release)
    return ResolvedGasRelease.model_validate_json(json.dumps(raw, allow_nan=False))


def build_campaign(
    *,
    vertical_dir: Path,
    inventory_dir: Path,
    backend_config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    facility = Facility.model_validate_json(
        (vertical_dir / "facility.json").read_text(encoding="utf-8-sig")
    )
    vertical_campaign = _load(vertical_dir / "campaign.json")
    vertical_catalog = _load(vertical_dir / "resolved_release_catalog.json")
    inventory_responses = _load(inventory_dir / "provider_responses.json")
    inventory_releases = _load(inventory_dir / "resolved_releases.json")
    inventory_snapshots = _load(inventory_dir / "state_snapshots.json")

    releases: dict[str, ResolvedGasRelease] = {}
    provider_responses: dict[str, dict[str, Any]] = {}
    requests: dict[str, dict[str, Any]] = {}
    snapshots: dict[str, dict[str, Any]] = {}
    for event_id in sorted(vertical_catalog):
        suffix = _suffix(event_id)
        source_id = f"equipment-inventory-campaign/terminal_pipe_asset/{suffix}"
        source_response = inventory_responses.get(source_id)
        source_release = inventory_releases.get(source_id)
        source_snapshot = inventory_snapshots.get(source_id)
        if not isinstance(source_response, dict) or not isinstance(source_release, dict):
            raise ValueError(f"{event_id}: matching inventory provider packet is missing")
        if not isinstance(source_snapshot, dict):
            raise ValueError(f"{event_id}: matching inventory state snapshot is missing")
        release = _build_release(
            event_id,
            source_response,
            source_release,
            float(vertical_catalog[event_id]["failure_opening_diameter_m"]),
        )
        releases[event_id] = release
        response = copy.deepcopy(source_response)
        response["data"]["event_id"] = event_id
        response["data"]["component_id"] = "terminal_pipe"
        response["data"]["port_id"] = "terminal_pipe.out"
        response["data"]["provider_meta"] = {
            "initial_mass_kg": response["data"]["available_mass_kg"],
            "cumulative_mass_in_kg": 0.0,
            "final_mass_kg": response["data"]["remaining_inventory_kg"],
            "residual_mass_kg": response["data"]["max_total_mass_residual_kg"],
            "available_mass_definition": (
                "provider-owned positive-threshold finite reserve; "
                "synthetic diagnostic inventory, not site inventory"
            ),
        }
        provider_responses[event_id] = response
        snapshots[event_id] = source_snapshot

    campaign = copy.deepcopy(vertical_campaign)
    for route in campaign.get("event_routes", []):
        event_id = route.get("event_id") if isinstance(route, dict) else None
        if event_id not in releases:
            continue
        release = releases[event_id]
        snapshot = snapshots[event_id]
        for branch in route.get("branches", []):
            request = branch.get("request")
            if not isinstance(request, dict):
                continue
            evaluation_times = {
                float(value)
                for value in request.get("evaluation_times_s", [])
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            evaluation_times.update(
                [0.0, release.duration_s, *[step.time_s for step in release.steps]]
            )
            request.update(
                {
                    "component_id": "terminal_pipe",
                    "state_snapshot": snapshot,
                    "state_snapshot_digest": snapshot_digest(snapshot),
                    "provider_state_snapshot_digest": snapshot_digest(snapshot),
                    "provider_state_snapshot_digests": [snapshot_digest(snapshot)],
                    "resolved_release": release.model_dump(mode="json"),
                    "resolved_release_set": None,
                    "available_mass_kg": release.available_mass_kg,
                    "source_operator": "equipment_inventory_depletion",
                    "release_termination": {
                        "basis": release.termination_basis,
                        "time_s": release.duration_s,
                        "provenance": release.termination_provenance,
                    },
                    "evaluation_times_s": sorted(evaluation_times),
                }
            )

    backend_config = _load_backend_with_current_source_pins(backend_config_path)
    backend = IsolatedBackend(backend_config)
    typed_campaign = RiskCampaign.model_validate_json(json.dumps(campaign))
    result = ResearchPipeline(facility, backend).facility_risk(typed_campaign)
    _save(output_dir / "facility.json", facility.model_dump(mode="json"))
    _save(output_dir / "campaign.json", campaign)
    _save(output_dir / "provider_responses.json", provider_responses)
    _save(output_dir / "resolved_releases.json", {
        event_id: release.model_dump(mode="json") for event_id, release in releases.items()
    })
    _save(output_dir / "state_snapshots.json", snapshots)
    _save(output_dir / "campaign_result.json", result)
    _save(output_dir / "verification.json", {
        "schema_version": "prism.vertical_inventory_handoff_campaign_verification.v1",
        "status": result.get("status"),
        "event_count": len(releases),
        "case_count": len(result.get("cases", [])),
        "executed_case_count": sum(
            str(row.get("status", "")).startswith("EXECUTED")
            for row in result.get("cases", [])
        ),
        "termination_basis_counts": {
            basis: sum(
                release.termination_basis == basis for release in releases.values()
            )
            for basis in sorted({release.termination_basis for release in releases.values()})
        },
        "provider_qualification_claim": False,
        "frequency_inference": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "limitations": [
            "provider finite inventory and positive threshold are synthetic diagnostic inputs",
            "vertical free-jet and horizontal handoff are not independently validated",
            "no field frequency or sensor inverse inference is performed",
        ],
    })
    return result


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    from lh2_tno.state_snapshot import EquipmentStateSnapshot

    return EquipmentStateSnapshot.from_mapping(snapshot).digest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vertical-dir", type=Path, required=True)
    parser.add_argument("--inventory-dir", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_campaign(
        vertical_dir=args.vertical_dir,
        inventory_dir=args.inventory_dir,
        backend_config_path=args.backend_config,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "status": result.get("status"),
        "output_dir": str(args.output_dir),
        "event_count": len(result.get("events", [])),
        "case_count": len(result.get("cases", [])),
        "uncomputed_case_count": len(result.get("uncomputed_cases", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
