"""Run the native external LayeredTank accident export through PRISM.

This is an operator-limited integration smoke.  The external model owns the
finite-volume tank state, atmospheric flash partition and mass ledger; PRISM
only validates the returned packet and optionally runs the consequence chain.
The scenario is synthetic and never receives an initiating frequency.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_accident_export import (  # noqa: E402
    AccidentReleaseExportRequest,
    export_equipment_liquid_accident_history,
)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


class NativeLayeredTankProvider:
    """Adapt one native external model to the PRISM provider protocol."""

    def __init__(self, model: Any, native_parameters: dict[str, Any]) -> None:
        self.model = model
        self.native_parameters = dict(native_parameters)

    def export_accident_history(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = dict(request)
        payload.update(self.native_parameters)
        return dict(self.model.export_accident_history(payload))


def _request(source_digest: str, state_digest: str) -> AccidentReleaseExportRequest:
    payload = {
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": "native-layered-tank-smoke",
        "port_id": "liquid-outlet",
        "event_id": "native-layered-tank-smoke/liquid-outlet/0.001m",
        "failure_mode": "explicit_failed_opening",
        "failure_opening_diameter_m": 1.0e-3,
        "horizon_s": 0.05,
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "native lh2dt LayeredTank atmospheric liquid outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "lh2dt.layered_tank.LayeredTank",
        "model_revision": "native-export-067631a",
        "state_snapshot_digest": state_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit native external LayeredTank diagnostic; not site-calibrated",
        "provider_termination_required": True,
    }
    return AccidentReleaseExportRequest.from_mapping(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-consequence-chain", action="store_true")
    parser.add_argument(
        "--backend-config",
        type=Path,
        default=ROOT / "results" / "20261009" / "backend_config_current.json",
    )
    args = parser.parse_args()
    external_root = args.lh2dt_root.resolve()
    sys.path.insert(0, str(external_root / "src"))
    try:
        from lh2dt.geometry import HorizontalVesselGeometry
        from lh2dt.layered_tank import LayeredTank, LayeredTankParameters
    except ImportError as error:
        raise SystemExit(f"cannot import native lh2dt LayeredTank: {error}") from error

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
        "source": "native-layered-tank-smoke",
        "pressure_pa_abs": 500000.0,
        "liquid_volume_fraction": 0.43,
    })
    request = _request(source_digest, state_digest)
    provider = NativeLayeredTankProvider(
        model,
        {
            "initial_pressure_pa_abs": 500000.0,
            "liquid_volume_fraction": 0.43,
            "time_step_s": 0.05,
            "minimum_step_s": 0.005,
            "discharge_coefficient": 0.7,
            "impact_position_m": [0.0, 0.0, 0.5],
            "direction_enu": [1.0, 0.0, 0.0],
            "droplet_diameter_m": 1.0e-3,
        },
    )
    started = time.perf_counter()
    result = export_equipment_liquid_accident_history(provider, request)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    release = result.release
    response = result.provider_response
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "provider_response.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "resolved_release.json").write_text(
        json.dumps(release.model_dump(mode="json"), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    consequence_verification: dict[str, Any] | None = None
    consequence_elapsed_ms: float | None = None
    if args.run_consequence_chain:
        import subprocess

        chain_dir = args.output_dir / "consequence_chain"
        packet_path = chain_dir / "resolved_release.json"
        chain_dir.mkdir(parents=True, exist_ok=True)
        packet_path.write_text(
            json.dumps(release.model_dump(mode="json"), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(ROOT / "scripts" / "validate_lh2dt_prism_packet_chain.py"),
            "--packet",
            str(packet_path),
            "--output-dir",
            str(chain_dir),
            "--backend-config",
            str(args.backend_config),
        ]
        chain_started = time.perf_counter()
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        consequence_elapsed_ms = (time.perf_counter() - chain_started) * 1000.0
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise SystemExit(f"native packet consequence chain failed: {detail}")
        consequence_verification = json.loads(
            (chain_dir / "verification.json").read_text(encoding="utf-8")
        )

    verification = {
        "schema_version": "prism.native_lh2dt_layered_tank_smoke.v1",
        "status": "EXECUTED_OPERATOR_LIMITED_NATIVE_DIAGNOSTIC",
        "provider_model": "lh2dt.layered_tank.LayeredTank",
        "provider_source_digest": source_digest,
        "provider_result_digest": result.provider_result_digest,
        "strict_packet_duration_s": release.duration_s,
        "strict_packet_mass_residual_kg": release.cumulative_mass_out_kg - release.integrated_mass_kg,
        "strict_packet_energy_residual_j": release.cumulative_specific_enthalpy_out_j - release.integrated_specific_enthalpy_out_j,
        "native_export_elapsed_ms": elapsed_ms,
        "consequence_chain_executed": consequence_verification is not None,
        "consequence_chain_status": None if consequence_verification is None else consequence_verification.get("status"),
        "consequence_chain_elapsed_ms": consequence_elapsed_ms,
        "qualified_provider_packet_count": 0,
        "provider_packet_promoted": result.provider_packet_promoted,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "limitations": [
            "synthetic LayeredTank geometry, initial state, opening and atmospheric boundary",
            "native method currently preserves ground liquid and does not promote airborne liquid",
            "no initiating frequency or qualified provider evidence was attached",
        ],
    }
    (args.output_dir / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
