"""Pass one strict lh2dt->PRISM packet through the full consequence chain.

This command is a chain diagnostic, not a facility QRA.  It uses a synthetic
outdoor facility/receptor context and deliberately omits initiating frequency.
The provider packet, however, is loaded through the same strict
``prism.resolved_release.v1`` loader used by a campaign.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.contracts import Facility  # noqa: E402
from lh2_tno.equipment_boundary import ResolvedLiquidRelease  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    build_consequence_request_from_provider_release,
    load_provider_release,
)


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _facility(
    component_id: str,
    port_id: str,
    position: tuple[float, float, float],
    phase: str,
    fluid: str,
) -> Facility:
    basis = {
        "fluid": fluid,
        "backend": "CoolProp-HEOS",
        "energy_reference": f"CoolProp-HEOS:{fluid}:native",
    }
    raw = {
        "id": "lh2dt-prism-packet-chain-diagnostic",
        "configuration_origin": "synthetic",
        "environment": "outdoor",
        "components": [{
            "id": component_id,
            "kind": "pipe",
            "position_enu_m": list(position),
            "property_basis": basis,
            "parameters_si": {"length_m": 0.01, "diameter_m": 0.01},
        }],
        "ports": [{
            "id": port_id,
            "component_id": component_id,
            "phase": phase,
            "direction": "out",
        }],
        "edges": [],
        "receptors": [
            {"id": "near_worker", "position_enu_m": [2.0, 0.0, 1.0]},
            {"id": "downwind_worker", "position_enu_m": [10.0, 0.0, 0.1]},
            {"id": "side_worker", "position_enu_m": [25.0, 4.0, 1.8]},
        ],
    }
    return Facility.model_validate_json(json.dumps(raw, allow_nan=False))


def run(packet_path: Path, output_dir: Path, backend_config_path: Path) -> dict:
    release = load_provider_release(packet_path)
    defaults_name = (
        "provider_request_defaults_liquid.json"
        if isinstance(release, ResolvedLiquidRelease)
        else "provider_request_defaults.json"
    )
    defaults = json.loads((ROOT / "examples" / defaults_name).read_text(encoding="utf-8"))
    defaults["component_id"] = release.component_id
    defaults["source_position_enu_m"] = list(release.position_enu_m)
    defaults["available_mass_kg"] = release.available_mass_kg
    defaults["resolved_release"] = None
    defaults["source_input"] = None
    defaults["resolved_liquid_release"] = None
    defaults["resolved_release_set"] = None
    defaults["annual_frequency_per_year"] = None
    defaults["annual_frequency_provenance"] = None
    defaults["frequency_event"] = None
    defaults["initiation_intensity_per_s"] = None
    if isinstance(release, ResolvedLiquidRelease):
        # Small provider diagnostic packets can evaporate below the native
        # pool dry-depth threshold before a finite wet cell is formed.  Use a
        # declared sensitivity footprint for that diagnostic only; the
        # footprint is never inferred for a facility assessment.
        pool_radius = (
            0.0001 if release.integrated_mass_kg < 1.0e-4
            else 0.005 if release.integrated_mass_kg < 0.1
            else 0.05
        )
        if release.property_basis.fluid == "ParaHydrogen":
            pool_fluid = "Hydrogen"
            pool_translation = "para_hydrogen_to_hydrogen"
            pool_provenance = "explicit provider ParaHydrogen to native DynamicLH2PoolX Hydrogen compatibility boundary; synthetic diagnostic"
        else:
            pool_fluid = release.property_basis.fluid
            pool_translation = "none"
            pool_provenance = None
        defaults["pool"] = {
            "footprint_origin": "declared_sensitivity",
            "fluid": pool_fluid,
            "fluid_translation": pool_translation,
            "translation_provenance": pool_provenance,
            "radius_m": pool_radius,
            "conductivity_w_mk": 0.6,
            "diffusivity_m2_s": 1.5e-7,
            "initial_temperature_k": release.ambient_temperature_k,
            "domain_radius_m": max(0.005, 5.0 * pool_radius) if pool_radius < 0.001 else max(0.25, 5.0 * pool_radius),
            "radial_step_m": pool_radius / 20.0,
            "maximum_time_step_s": 0.01,
        }
    defaults["release_termination"] = {
        "basis": "provider_declared",
        "time_s": "provider_duration",
        "provenance": "provider packet termination basis and duration; synthetic diagnostic context",
    }
    # The request model requires the end of release and delayed ignition to be
    # explicit timestamps; provider breakpoints are inserted by the adapter.
    defaults["evaluation_times_s"] = sorted(set(
        list(defaults["evaluation_times_s"])
        + [float(release.duration_s)]
    ))
    if isinstance(release, ResolvedLiquidRelease):
        defaults["source_operator"] = "equipment_liquid_release"
    else:
        defaults["source_operator"] = "integrated_transient"
    request = build_consequence_request_from_provider_release(release, defaults)

    config_raw = json.loads(backend_config_path.read_text(encoding="utf-8"))
    for pin in config_raw.get("packages", []):
        root = Path(pin["root"])
        if root.exists():
            pin["sha256"] = tree_digest(root)
    config = BackendConfig.model_validate_json(json.dumps(config_raw, allow_nan=False))
    facility = _facility(
        release.component_id,
        release.port_id,
        tuple(release.position_enu_m),
        "two_phase" if isinstance(release, ResolvedLiquidRelease) else "vapour",
        release.property_basis.fluid,
    )
    pipeline = ResearchPipeline(facility, IsolatedBackend(config))
    result = pipeline.consequences(request)
    result_data = result.get("data", result) if isinstance(result, dict) else {}
    verification = {
        "status": result_data.get("status"),
        "source_operator": request.source_operator,
        "provider_packet_schema": release.provider_export_schema,
        "provider_model_provenance": release.upstream_service_provenance,
        "boundary_kind": release.boundary_kind,
        "provider_duration_s": release.duration_s,
        "provider_mass_residual_kg": release.cumulative_mass_out_kg - release.integrated_mass_kg,
        "pool_sensitivity_radius_m": defaults.get("pool", {}).get("radius_m") if isinstance(defaults.get("pool"), dict) else None,
        "consequence_chain_executed": result_data.get("status", "").startswith("END_TO_END"),
        "facility_ir_fn_claim": False,
        "frequency_inference": False,
        "physical_validation_claim": False,
        "provider_packet_promoted": False,
        "limitations": [
            "synthetic facility, receptors, weather and ignition context",
            "no initiating frequency was applied",
            "single external-provider diagnostic packet only; provider model is not site-calibrated",
        ],
    }
    _save(output_dir / "request.json", request.model_dump(mode="json"))
    _save(output_dir / "consequence_result.json", result)
    _save(output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one strict lh2dt PRISM packet through consequence damage")
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--backend-config",
        type=Path,
        default=ROOT / "results" / "20261009" / "backend_config_current.json",
    )
    args = parser.parse_args()
    try:
        verification = run(args.packet, args.output_dir, args.backend_config)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        raise SystemExit(f"lh2dt PRISM packet chain failed: {error}") from error
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
