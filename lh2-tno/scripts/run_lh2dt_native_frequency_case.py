"""Run one native lh2dt LayeredTank packet with a reviewed literature frequency.

This is a deliberately narrow integration diagnostic.  The native external
LayeredTank owns the liquid outlet history and mass/enthalpy ledger.  PRISM
uses the published LH2 vessel frequency already present in a compiled
campaign, then runs the packet through the normal outdoor consequence chain.
The packet remains synthetic/operator-limited and is never promoted to a
qualified provider or a facility-wide QRA contribution.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_accident_export import (  # noqa: E402
    AccidentReleaseExportRequest,
    export_equipment_liquid_accident_history,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    build_consequence_request_from_provider_release,
)


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


class NativeLayeredTankProvider:
    def __init__(self, model: Any, native_parameters: dict[str, Any]) -> None:
        self.model = model
        self.native_parameters = dict(native_parameters)

    def export_accident_history(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = dict(request)
        payload.update(self.native_parameters)
        return dict(self.model.export_accident_history(payload))


def _native_request(source_digest: str, state_digest: str) -> AccidentReleaseExportRequest:
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": "storage-tank-01",
        "port_id": "tank-accident-out",
        "event_id": "generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%",
        "failure_mode": "explicit_failed_opening",
        # Exact match to the reviewed LH2_VESSEL AREA_0.01% catalogue bin.
        "failure_opening_diameter_m": 0.0127,
        "horizon_s": 0.0001,
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "native lh2dt LayeredTank atmospheric liquid outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "lh2dt.layered_tank.LayeredTank",
        "model_revision": "native-export-4b1ea87",
        "state_snapshot_digest": state_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit native external LayeredTank diagnostic; not site-calibrated",
        "provider_termination_required": True,
    })


def _campaign_request_defaults(request: dict[str, Any]) -> dict[str, Any]:
    defaults = copy.deepcopy(request)
    for key in (
        "component_id", "available_mass_kg", "source_position_enu_m",
        "source_positions_enu_m", "source_input", "resolved_release",
        "resolved_release_set", "resolved_liquid_release",
        "annual_frequency_per_year", "annual_frequency_provenance",
        "frequency_event", "initiation_intensity_per_s",
    ):
        defaults.pop(key, None)
    defaults["release_termination"] = {
        "basis": "provider_declared",
        "time_s": "provider_duration",
        "provenance": "native LayeredTank packet; provider clock retained",
    }
    old = request.get("release_termination")
    if isinstance(old, dict) and isinstance(old.get("time_s"), (int, float)):
        times = defaults.get("evaluation_times_s")
        if isinstance(times, list):
            defaults["evaluation_times_s"] = [x for x in times if x != old["time_s"]]
    return defaults


def run(args: argparse.Namespace) -> dict[str, Any]:
    external_root = args.lh2dt_root.resolve()
    sys.path.insert(0, str(external_root / "src"))
    from lh2dt.geometry import HorizontalVesselGeometry
    from lh2dt.layered_tank import LayeredTank, LayeredTankParameters

    compiled = json.loads(args.compiled_campaign.read_text(encoding="utf-8"))
    event_id = "generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%"
    routes = compiled.get("event_routes")
    if not isinstance(routes, list):
        raise ValueError("compiled campaign has no event_routes")
    route = next((row for row in routes if row.get("event_id") == event_id), None)
    if not isinstance(route, dict) or not isinstance(route.get("branches"), list):
        raise ValueError(f"compiled campaign lacks exact event route: {event_id}")
    branches = [row for row in route["branches"] if row.get("request") is not None]
    if len(branches) != 1 or not isinstance(branches[0].get("request"), dict):
        raise ValueError("exact native frequency case requires one compiled request branch")
    current_request = branches[0]["request"]

    shape = HorizontalVesselGeometry(2.0, 4.0, 0.5, quadrature_order=48)
    model = LayeredTank(
        shape,
        LayeredTankParameters(
            liquid_cell_count=3,
            vapor_cell_count=3,
            wall_node_count=6,
            wall_heat_capacity_J_K=3.0e6,
        ),
    )
    source_digest = _tree_digest(external_root)
    state_digest = canonical_digest({
        "source": "native-layered-tank-frequency-case",
        "pressure_pa_abs": 110000.0,
        "liquid_volume_fraction": 0.05,
    })
    provider = NativeLayeredTankProvider(
        model,
        {
            "initial_pressure_pa_abs": 110000.0,
            "liquid_volume_fraction": 0.05,
            "time_step_s": 0.0001,
            "minimum_step_s": 0.00001,
            "discharge_coefficient": 0.7,
            "impact_position_m": [0.0, 0.0, 0.5],
            "direction_enu": [1.0, 0.0, 0.0],
            "droplet_diameter_m": 1.0e-3,
        },
    )
    started = time.perf_counter()
    adapted = export_equipment_liquid_accident_history(
        provider, _native_request(source_digest, state_digest)
    )
    export_elapsed_ms = (time.perf_counter() - started) * 1000.0
    release = adapted.release
    # Keep the reviewed facility placement from the compiled campaign.  The
    # provider still owns all thermodynamics and time-history fields.
    payload = release.model_dump(mode="json")
    payload["position_enu_m"] = list(current_request["source_position_enu_m"])
    payload["provider_boundary_reference"] += "; explicit placement from compiled facility port"
    release = type(release).model_validate_json(json.dumps(payload, allow_nan=False))
    defaults = _campaign_request_defaults(current_request)
    if release.phase_basis == "two_phase" and any(
        float(step.ground_liquid_mass_flow_kg_s) > 0.0
        for step in release.steps
    ):
        # The native packet has a positive ground-liquid partition.  A small
        # declared sensitivity footprint lets the diagnostic chain run while
        # keeping the footprint explicitly outside facility-QRA promotion.
        defaults["pool"] = {
            "footprint_origin": "declared_sensitivity",
            "fluid": "Hydrogen",
            "fluid_translation": "none",
            "radius_m": 0.0001,
            "conductivity_w_mk": 0.6,
            "diffusivity_m2_s": 1.5e-7,
            "initial_temperature_k": release.ambient_temperature_k,
            "domain_radius_m": 0.005,
            "radial_step_m": 0.000005,
            "maximum_time_step_s": 0.01,
        }
    request = build_consequence_request_from_provider_release(release, defaults)
    branch = copy.deepcopy(branches[0])
    branch["request"] = request.model_dump(mode="json")
    branch["provenance"] = (
        "native lh2dt LayeredTank export; exact LH2_VESSEL AREA_0.01% opening; "
        "published literature frequency retained; synthetic diagnostic only"
    )
    route["branches"] = [branch]
    campaign = RiskCampaign.model_validate_json(json.dumps(compiled, ensure_ascii=False, allow_nan=False))

    manifest = EquipmentManifest.from_json(args.manifest)
    config_raw = json.loads(args.backend_config.read_text(encoding="utf-8"))
    for pin in config_raw.get("packages", []):
        pin["sha256"] = tree_digest(Path(pin["root"]))
    config = BackendConfig.model_validate_json(json.dumps(config_raw, ensure_ascii=False, allow_nan=False))
    chain_started = time.perf_counter()
    result = ResearchPipeline(manifest.to_facility(), IsolatedBackend(config)).facility_risk(campaign)
    chain_elapsed_ms = (time.perf_counter() - chain_started) * 1000.0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _save(args.output_dir / "provider_response.json", adapted.provider_response)
    _save(args.output_dir / "resolved_release.json", release.model_dump(mode="json"))
    _save(args.output_dir / "campaign.json", campaign.model_dump(mode="json"))
    _save(args.output_dir / "campaign_result.json", result)
    verification = {
        "schema_version": "prism.native_lh2dt_frequency_case.v1",
        "status": result.get("status"),
        "event_id": event_id,
        "component_id": release.component_id,
        "catalogue_opening_diameter_m": 0.0127,
        "provider_opening_diameter_m": release.failure_opening_diameter_m,
        "exact_opening_match": release.failure_opening_diameter_m == 0.0127,
        "provider_source_digest": release.provider_source_digest,
        "provider_result_digest": adapted.provider_result_digest,
        "provider_duration_s": release.duration_s,
        "provider_mass_residual_kg": release.cumulative_mass_out_kg - release.integrated_mass_kg,
        "literature_frequency_bound": True,
        "frequency_source": "compiled campaign LH2_VESSEL AREA_0.01% literature row",
        "frequency_from_provider_packet": False,
        "provider_packet_promoted": adapted.provider_packet_promoted,
        "qualified_provider_packet_count": 0,
        "native_export_elapsed_ms": export_elapsed_ms,
        "consequence_chain_elapsed_ms": chain_elapsed_ms,
        "consequence_chain_executed": any(
            str(case.get("status", "")).startswith("EXECUTED")
            for case in result.get("cases", [])
        ),
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "facility_total_risk_available": result.get("total_facility_annual_ir_low_high") is not None,
        "limitations": [
            "synthetic LayeredTank geometry, initial state, opening and atmospheric boundary",
            "native packet uses a bounded horizon and retains residual inventory",
            "literature frequency is diagnostic input and is not site-calibrated",
            "facility scope remains incomplete; this one-case result is not total facility IR/F-N",
        ],
    }
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--compiled-campaign", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        verification = run(args)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        raise SystemExit(f"native LH2 frequency case failed: {error}") from error
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
