"""Re-export the authoritative AREA_100% pipe state with explicit stop evidence.

This is a diagnostic candidate runner.  It reproduces the current campaign's
10 m, 0.025 m transfer-line state (250 kPa, quality 0.1), asks the external
DynamicHEMPipe for an explicit post-pressure-equalization observation, and
then consumes that packet in a one-event RiskCampaign.  The reduced spatial
grid is deliberate for a processing-time diagnostic; it never promotes the
authoritative facility campaign or facility QRA.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_lh2dt_native_dynamic_pipe_full_bore_facility_frequency_case import _defaults  # noqa: E402
from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.consequences import PoolBoundary, SpatialDomain  # noqa: E402
from lh2_tno.equipment_accident_export import (  # noqa: E402
    AccidentReleaseExportRequest,
    export_equipment_liquid_accident_history,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import build_consequence_request_from_provider_release  # noqa: E402


EVENT_ID = "generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%"


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class _NativeProvider:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = dict(response)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if request.get("event_id") != self.response.get("data", {}).get("event_id"):
            raise ValueError("native provider event_id does not match candidate request")
        return self.response


def _load_native_response(
    *,
    external_root: Path,
    verification: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    sys.path.insert(0, str(external_root / "src"))
    from lh2dt.dynamic_pipe import DynamicHEMPipe
    from lh2dt.properties import HydrogenProperties

    properties = HydrogenProperties("Hydrogen")
    source_digest = _tree_digest(external_root)
    pipe = DynamicHEMPipe(
        10.0,
        0.025,
        1.0e-6,
        1.0e5,
        ambient_temperature_K=288.15,
        properties=properties,
    )
    response = pipe.export_accident_history(
        {
            "event_id": EVENT_ID,
            "component_id": "liquid-transfer-line-01",
            "port_id": "line-accident-out",
            "failure_mode": "explicit_failed_opening",
            "initial_pressure_pa_abs": 250000.0,
            "initial_temperature_k": 27.0,
            "initial_quality": 0.1,
            "ambient_pressure_pa_abs": 101325.0,
            "ambient_temperature_k": 288.15,
            "failure_opening_diameter_m": 0.025,
            "discharge_coefficient": 0.8,
            "horizon_s": 60.0,
            "time_step_s": 0.05,
            "wall_temperature_k": 27.0,
            "position_enu_m": [5.0, 0.0, 1.0],
            "direction_enu": [1.0, 0.0, 0.0],
            "provider_source_digest": source_digest,
            "state_snapshot_digest": verification["state_snapshot_digest"],
            "post_pressure_equalization_observation_s": 0.2,
        }
    )
    return dict(response), source_digest


def _build_request(
    response: Mapping[str, Any],
    verification: Mapping[str, Any],
    campaign: Mapping[str, Any],
) -> Any:
    request = AccidentReleaseExportRequest.from_mapping(
        {
            "schema_version": "prism.equipment_accident_export_request.v1",
            "event_kind": "accidental_leak",
            "component_id": "liquid-transfer-line-01",
            "port_id": "line-accident-out",
            "event_id": EVENT_ID,
            "failure_mode": "explicit_failed_opening",
            "failure_opening_diameter_m": 0.025,
            "horizon_s": 60.0,
            "position_enu_m": [5.0, 0.0, 1.0],
            "direction_enu": [1.0, 0.0, 0.0],
            "ambient_pressure_pa_abs": 101325.0,
            "ambient_temperature_k": 288.15,
            "post_pressure_equalization_observation_s": 0.2,
            "provider_source_digest": response["provider_source_digest"],
            "provider_boundary_reference": "lh2dt.DynamicHEMPipe.export_accident_history native outlet",
            "input_origin": "model_prediction",
            "model_package": "lh2dt_models",
            "model_class": "lh2dt.dynamic_pipe.DynamicHEMPipe",
            "model_revision": "native-export-3d9b982",
            "state_snapshot_digest": verification["state_snapshot_digest"],
            "state_snapshot": verification["state_snapshot"],
            "evidence_status": "synthetic_diagnostic",
            "scenario_provenance": (
                "exact authoritative AREA_100% state replay with explicit provider "
                "pressure-equalization observation; candidate only"
            ),
            "provider_termination_required": True,
        }
    )
    adapted = export_equipment_liquid_accident_history(_NativeProvider(response), request)
    release = adapted.release
    route = next(row for row in campaign["event_routes"] if row["event_id"] == EVENT_ID)
    defaults = _defaults(route["branches"][0]["request"])
    return adapted, build_consequence_request_from_provider_release(release, defaults)


def run(args: argparse.Namespace) -> dict[str, Any]:
    campaign_raw = json.loads(args.campaign.read_text(encoding="utf-8"))
    packet_verification = json.loads(args.packet_verification.read_text(encoding="utf-8"))
    response, source_digest = _load_native_response(
        external_root=args.lh2dt_root.resolve(),
        verification=packet_verification,
    )
    adapted, request = _build_request(response, packet_verification, campaign_raw)
    request = request.model_copy(
        update={
            "pool": PoolBoundary(
                footprint_origin="declared_sensitivity",
                fluid="Hydrogen",
                fluid_translation="none",
                radius_m=args.pool_radius_m,
                conductivity_w_mk=0.6,
                diffusivity_m2_s=1.5e-7,
                initial_temperature_k=288.15,
                domain_radius_m=args.pool_domain_radius_m,
                radial_step_m=args.pool_radial_step_m,
                maximum_time_step_s=0.01,
            ),
            "domain": SpatialDomain(
                downwind_bounds_m=(-1.0, 30.0),
                crosswind_bounds_m=(-5.0, 5.0),
                height_bounds_m=(0.0, 5.0),
                cell_size_m=1.0,
            ),
            "n_puff_steps": args.n_puff_steps,
        }
    )

    selected_event = next(
        event
        for event in campaign_raw["frequency_plan"]["precomputed_events"]
        if event["id"] == EVENT_ID
    )
    manifest_raw = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected_component = "liquid-transfer-line-01"
    raw = copy.deepcopy(campaign_raw)
    raw["event_routes"] = [
        {
            "event_id": EVENT_ID,
            "operating_mode": "supply",
            "hazop_scenario_id": (
                "native-full-scope|liquid-transfer-line-01|supply|"
                "generic-lh2-full-scope-frequency-example|transfer-line|AREA_100%"
            ),
            "branches": [
                {
                    "id": "native-provider-pressure-equalization-candidate",
                    "probability_given_event": 1.0,
                    "provenance": (
                        "exact current AREA_100% state replay; reduced declared sensitivity "
                        "grid; diagnostic only"
                    ),
                    "request": request.model_dump(mode="json"),
                }
            ],
        }
    ]
    plan = raw["frequency_plan"]
    plan["assets"] = [asset for asset in plan["assets"] if asset.get("id") == "transfer-line"]
    plan["excluded_model_components"] = {
        component["id"]: "excluded from exact AREA_100% candidate campaign; no packet executed"
        for component in manifest_raw["components"]
        if component["id"] != selected_component
    }
    plan["precomputed_events"] = [selected_event]
    plan["precomputed_events_provenance"] = (
        "exact current AREA_100% frequency row selected for candidate recheck"
    )
    raw["maximum_physics_cases"] = 1
    raw["scope_provenance"] = (
        "exact current AREA_100% native DynamicHEMPipe pressure-equalization candidate; "
        "single event only; no facility promotion"
    )

    manifest = EquipmentManifest.from_json(args.manifest)
    config_raw = json.loads(args.backend_config.read_text(encoding="utf-8"))
    for package in config_raw.get("packages", []):
        package["sha256"] = tree_digest(Path(package["root"]))
    config = BackendConfig.model_validate_json(json.dumps(config_raw, ensure_ascii=False))
    risk_campaign = RiskCampaign.model_validate_json(
        json.dumps(raw, ensure_ascii=False, allow_nan=False)
    )
    started = time.perf_counter()
    result = ResearchPipeline(
        manifest.to_facility(), IsolatedBackend(config)
    ).facility_risk(risk_campaign)
    chain_elapsed_ms = (time.perf_counter() - started) * 1000.0
    provider_meta = response["data"].get("provider_meta", {})
    release = adapted.release
    output = {
        "schema_version": "prism.native_dynamic_pipe_exact_area100_reduced_grid_candidate.v1",
        "provider_source_digest": source_digest,
        "provider_result_digest": release.provider_result_digest,
        "event_id": EVENT_ID,
        "provider_duration_s": release.duration_s,
        "provider_mass_residual_kg": (
            release.cumulative_mass_out_kg - release.integrated_mass_kg
        ),
        "termination_basis": release.termination_basis,
        "pressure_equalization": provider_meta,
        "state_snapshot_digest": packet_verification["state_snapshot_digest"],
        "candidate_request_digest": request.digest(),
        "chain_elapsed_ms": chain_elapsed_ms,
        "campaign_status": result.get("status"),
        "campaign_event_count": len(result.get("events", [])),
        "campaign_case_count": len(result.get("cases", [])),
        "campaign_executed_case_count": sum(
            str(case.get("status", "")).startswith("EXECUTED")
            for case in result.get("cases", [])
        ),
        "campaign_risk_atom_count": len(result.get("risk_atoms", [])),
        "facility_total_risk_available": result.get("total_facility_annual_ir_low_high") is not None,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "provider_packet_promoted": adapted.provider_packet_promoted,
        "sensitivity_grid": {
            "pool_domain_radius_m": args.pool_domain_radius_m,
            "pool_radial_step_m": args.pool_radial_step_m,
            "downwind_bounds_m": [-1.0, 30.0],
            "crosswind_bounds_m": [-5.0, 5.0],
            "height_bounds_m": [0.0, 5.0],
            "cell_size_m": 1.0,
            "n_puff_steps": args.n_puff_steps,
        },
        "limitations": [
            "reduced declared sensitivity grid for processing-time diagnostic",
            "exact state replay uses synthetic provider input and current campaign synthetic receptor/weather",
            "qualification sidecar and independent physical validation remain absent",
            "candidate is not rebound into authoritative campaign",
        ],
    }
    _save(args.output, output)
    if args.output_dir is not None:
        _save(args.output_dir / "provider_response.json", response)
        _save(args.output_dir / "resolved_release.json", release.model_dump(mode="json"))
        _save(args.output_dir / "campaign_result.json", result)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--packet-verification", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--pool-radius-m", type=float, default=1.0e-4)
    parser.add_argument("--pool-domain-radius-m", type=float, default=5.0e-4)
    parser.add_argument("--pool-radial-step-m", type=float, default=5.0e-5)
    parser.add_argument("--n-puff-steps", type=int, default=40)
    args = parser.parse_args()
    try:
        output = run(args)
    except (ImportError, KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise SystemExit(f"exact native AREA_100% candidate failed: {error}") from error
    print(json.dumps({
        "status": output["campaign_status"],
        "provider_result_digest": output["provider_result_digest"],
        "campaign_executed_case_count": output["campaign_executed_case_count"],
        "campaign_risk_atom_count": output["campaign_risk_atom_count"],
        "chain_elapsed_ms": output["chain_elapsed_ms"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
