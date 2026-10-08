"""Audit the external lh2dt history against the SLABx-LH2 rate boundary.

The equipment model owns the total release rate.  SLABx-LH2 is used only for
the atmospheric partition.  This command reports the relative-rate gate
without relaxing it: a mismatch is a reproducible blocked result and never a
reason to replace the provider rate or promote a packet.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def audit_boundary(
    provider_export: Path,
    slabx_root: Path,
    *,
    rate_relative_tolerance: float,
) -> dict:
    if rate_relative_tolerance < 0.0 or not math.isfinite(rate_relative_tolerance):
        raise ValueError("rate_relative_tolerance must be finite and non-negative")

    # Keep this import local so the normal PRISM test suite does not require
    # the optional SLABx-LH2 source tree.
    sys.path.insert(0, str(slabx_root / "source" / "slabx-lh2"))
    sys.path.insert(0, str(ROOT / "scripts"))
    import validate_layered_tank_slabsx_bridge as bridge

    source = json.loads(provider_export.read_text(encoding="utf-8"))
    provider_rows, dt = bridge._provider_rows(source)
    partition_rows = bridge._slabx_partition_rows(provider_rows, source, dt)
    intervals = []
    for index, (provider, partition) in enumerate(zip(provider_rows, partition_rows)):
        provider_rate = float(provider["total_mass_flow_kg_s"])
        slabx_rate = float(partition["total_mass_flow_kg_s"])
        relative_error = (
            None
            if provider_rate <= 1.0e-12
            else abs(slabx_rate - provider_rate) / provider_rate
        )
        intervals.append(
            {
                "index": index,
                "time_s": float(provider["time_s"]),
                "provider_mass_flow_kg_s": provider_rate,
                "slabsx_mass_flow_kg_s": slabx_rate,
                "relative_rate_error": relative_error,
            }
        )
    max_error = max(
        (row["relative_rate_error"] for row in intervals if row["relative_rate_error"] is not None),
        default=0.0,
    )
    gate_pass = max_error <= rate_relative_tolerance
    bridge_error = None
    if gate_pass:
        try:
            bridge.combine_provider_liquid_partition(
                provider_rows,
                partition_rows,
                ambient_pressure_pa=float(source["ambient_pressure_pa"]),
                rate_relative_tolerance=rate_relative_tolerance,
            )
        except ValueError as error:
            bridge_error = str(error)
            gate_pass = False
    else:
        bridge_error = (
            f"provider/SLABx rate mismatch {max_error:.6g} exceeds "
            f"tolerance {rate_relative_tolerance:.6g}"
        )
    return {
        "status": "RATE_GATE_PASS" if gate_pass else "BLOCKED_PROVIDER_SLABX_RATE_MISMATCH",
        "provider_export": str(provider_export),
        "provider_schema_version": source.get("schema_version"),
        "component_id": source.get("component_id"),
        "port_id": source.get("port_id"),
        "interval_count": len(intervals),
        "time_step_s": dt,
        "rate_relative_tolerance": rate_relative_tolerance,
        "max_relative_rate_error": max_error,
        "intervals": intervals,
        "bridge_error": bridge_error,
        "provider_rate_owner": "external_lh2dt_equipment_model",
        "partition_owner": "SLABx-LH2",
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "promotion_policy": "A failed rate gate remains blocked; no coefficient, provider rate, or frequency is inferred.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("provider_export", type=Path)
    parser.add_argument("--slabx-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rate-relative-tolerance", type=float, default=0.05)
    args = parser.parse_args()
    try:
        result = audit_boundary(
            args.provider_export,
            args.slabx_root,
            rate_relative_tolerance=args.rate_relative_tolerance,
        )
    except (OSError, ImportError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"lh2dt/SLABx boundary audit failed: {error}") from error
    _save(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "RATE_GATE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
