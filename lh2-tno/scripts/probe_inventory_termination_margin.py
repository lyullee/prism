"""Probe whether the external LH2 inventory provider reaches its declared stop.

This is a diagnostic margin test for the provider termination boundary.  It
does not extend a release, replace an open case with another termination basis,
or promote a provider packet.  The result is intentionally useful when a
finite-inventory case remains ``NUMERICALLY_OPEN`` in the facility audit.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402


SCHEMA = "prism.inventory_termination_margin_probe.v1"
DEFAULT_AREAS_M2 = (1.0e-9, 1.0e-8, 1.0e-7, 1.0e-6, 1.0e-5)


def _load_backend(path: Path) -> tuple[BackendConfig, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("backend config must be an object")
    packages = raw.get("packages", [])
    if not isinstance(packages, list):
        raise ValueError("backend config packages must be a list")
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("root"), str):
            raise ValueError("backend package roots must be declared")
        package["sha256"] = tree_digest(Path(package["root"]))
    config = BackendConfig.model_validate_json(json.dumps(raw, ensure_ascii=False))
    return config, raw


def _request(area_m2: float, *, threshold_mass_kg: float, duration_s: float, time_step_s: float) -> dict[str, Any]:
    return {
        "operation": "equipment_dynamic_inventory",
        "fluid": "ParaHydrogen",
        "tank_geometry": {
            "volume_m3": 1.0e-4,
            "wall_heat_capacity_J_K": 100.0,
            "ambient_UA_W_K": 0.1,
            "fluid_wall_UA_W_K": 0.1,
        },
        "initial": {
            "pressure_pa": 101000.0,
            "liquid_fraction": 0.0001,
            "hydrogen_internal_energy_offset_j_kg": 5000.0,
        },
        "ambient": {"pressure_pa": 100000.0, "temperature_k": 288.15},
        "valve": {
            "full_open_area_m2": area_m2,
            "discharge_coefficient": 0.8,
            "pressure_samples": 16,
        },
        "depletion": {"threshold_mass_kg": threshold_mass_kg},
        "duration_s": duration_s,
        "time_step_s": time_step_s,
    }


def run_probe(
    *,
    backend_config_path: Path,
    areas_m2: tuple[float, ...] = DEFAULT_AREAS_M2,
    threshold_mass_kg: float = 1.0e-10,
    duration_s: float = 120.0,
    time_step_s: float = 1.2,
) -> dict[str, Any]:
    config, config_raw = _load_backend(backend_config_path)
    backend = IsolatedBackend(config)
    rows: list[dict[str, Any]] = []
    for area_m2 in areas_m2:
        started = time.perf_counter()
        request = _request(
            area_m2,
            threshold_mass_kg=threshold_mass_kg,
            duration_s=duration_s,
            time_step_s=time_step_s,
        )
        row: dict[str, Any] = {
            "area_m2": area_m2,
            "requested_duration_s": duration_s,
            "time_step_s": time_step_s,
            "threshold_mass_kg": threshold_mass_kg,
        }
        try:
            payload = backend.run("equipment_dynamic_inventory", request)
            data = payload["data"]
            initial = float(data["available_mass_kg"])
            remaining = float(data["remaining_inventory_kg"])
            row.update(
                {
                    "status": "DEPLETED" if data.get("inventory_depletion_detected") else "HORIZON_OR_INTERVAL_OPEN",
                    "duration_s": data.get("duration_s"),
                    "provider_intervals": data.get("provider_intervals"),
                    "available_mass_kg": initial,
                    "remaining_inventory_kg": remaining,
                    "remaining_fraction": remaining / initial if initial > 0.0 else None,
                    "inventory_depletion_detected": bool(data.get("inventory_depletion_detected")),
                    "termination_basis": data.get("termination_basis"),
                }
            )
        except Exception as error:  # external model errors are evidence, not instructions
            row.update({"status": "PROVIDER_ERROR", "error": f"{type(error).__name__}: {error}"})
        row["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
        rows.append(row)

    depleted_count = sum(row.get("status") == "DEPLETED" for row in rows)
    return {
        "schema_version": SCHEMA,
        "status": "TERMINATION_MARGIN_DIAGNOSTIC_COMPLETED",
        "provider_backend_config": str(backend_config_path),
        "provider_backend_config_digest": config.digest(),
        "provider_package_count": len(config_raw.get("packages", [])),
        "request_policy": {
            "source_kind": "external_dynamic_inventory_provider",
            "threshold_mass_kg": threshold_mass_kg,
            "duration_s": duration_s,
            "time_step_s": time_step_s,
            "no_extrapolation": True,
            "no_termination_basis_substitution": True,
            "provider_packet_promotion": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
        },
        "area_count": len(rows),
        "depleted_case_count": depleted_count,
        "open_case_count": len(rows) - depleted_count,
        "rows": rows,
        "interpretation": (
            "The probe measures whether the declared positive-mass inventory stop is reached within the bounded provider run. "
            "An open or provider-error row remains open in the facility release-boundary ledger; the result is never extended or relabelled."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = run_probe(backend_config_path=args.backend_config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "depleted_case_count": record["depleted_case_count"], "open_case_count": record["open_case_count"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
