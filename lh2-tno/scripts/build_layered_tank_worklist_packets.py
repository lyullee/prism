"""Build synthetic LayeredTank release packets for supported worklist events.

This is a development diagnostic, not a replacement for a reviewed facility
provider export.  It runs the external ``lh2dt.LayeredTankNetworkSimulator``
for each declared storage-tank hole size, sends the provider history through
the existing SLABx-LH2 boundary, and writes only packets whose component,
accident port, and opening exactly match the worklist.  Any model failure is
kept as an explicit uncomputed case.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lh2_tno.provider_catalog_coverage import audit_provider_catalog_coverage
from lh2_tno.provider_release import load_provider_release_catalog
from validate_layered_tank_inventory_slabsx import _run_provider


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def diagnostic_time_step(
    opening_diameter_m: float,
    *,
    reference_opening_diameter_m: float = 0.0127,
    reference_time_step_s: float = 0.001,
) -> float:
    """Scale the synthetic integration interval with opening area.

    The provider is advanced for a short positive-inventory diagnostic.  The
    area scaling keeps the first interval's released mass bounded as the
    worklist opening changes; it does not estimate an accident duration.
    """
    for name, value in (
        ("opening_diameter_m", opening_diameter_m),
        ("reference_opening_diameter_m", reference_opening_diameter_m),
        ("reference_time_step_s", reference_time_step_s),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive")
    return reference_time_step_s * (reference_opening_diameter_m / opening_diameter_m) ** 2


def _case_name(index: int) -> str:
    return f"storage_case_{index:02d}"


def build_packets(
    worklist: dict,
    *,
    lh2dt_root: Path,
    slabx_root: Path,
    output_dir: Path,
    component_id: str,
    target_release_kg: float,
    max_intervals: int,
    reference_time_step_s: float,
) -> dict:
    if not isinstance(worklist.get("work_items"), list) or not worklist["work_items"]:
        raise ValueError("provider worklist must contain a non-empty work_items list")
    if target_release_kg <= 0.0 or not math.isfinite(target_release_kg):
        raise ValueError("target_release_kg must be finite and positive")
    if max_intervals < 1:
        raise ValueError("max_intervals must be positive")
    items = [
        item
        for item in worklist.get("work_items", [])
        if item.get("component_id") == component_id
        and item.get("release_mode") == "hole"
        and item.get("provider_event_kind") == "accidental_leak"
        and item.get("required_opening_diameter_m") is not None
        and len(item.get("accident_port_ids", [])) == 1
    ]
    packets: list[dict] = []
    case_rows: list[dict] = []
    for index, item in enumerate(items, start=1):
        event_id = item["event_id"]
        port_id = item["accident_port_ids"][0]
        diameter = float(item["required_opening_diameter_m"])
        case_dir = output_dir / _case_name(index)
        time_step_s = diagnostic_time_step(
            diameter, reference_time_step_s=reference_time_step_s
        )
        row = {
            "event_id": event_id,
            "component_id": component_id,
            "port_id": port_id,
            "opening_diameter_m": diameter,
            "time_step_s": time_step_s,
            "status": "UNCOMPUTED",
            "synthetic_diagnostic": True,
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "frequency_inference": False,
        }
        try:
            provider_export, provider_meta = _run_provider(
                lh2dt_root,
                time_step_s=time_step_s,
                target_release_kg=target_release_kg,
                max_intervals=max_intervals,
                full_open_area_m2=math.pi * diameter**2 / 4.0,
            )
            _save(case_dir / "layered_tank_provider_export.json", provider_export)
            _save(case_dir / "layered_tank_provider_verification.json", provider_meta)
            bridge = ROOT / "scripts" / "validate_layered_tank_slabsx_bridge.py"
            command = [
                sys.executable,
                str(bridge),
                str(case_dir / "layered_tank_provider_export.json"),
                "--slabx-root",
                str(slabx_root),
                "--facility-component-id",
                component_id,
                "--facility-port-id",
                port_id,
                "--event-id",
                event_id,
                "--output-dir",
                str(case_dir / "slabx_bridge"),
            ]
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(detail or f"bridge exited {completed.returncode}")
            packet_path = case_dir / "slabx_bridge" / "resolved_liquid_release.json"
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            # Do not let a successful bridge for the wrong context enter the
            # catalog.  The later coverage audit is still authoritative, but
            # this local check makes each case failure explicit at the source.
            if packet.get("event_id") != event_id:
                raise ValueError("bridge packet event_id does not match worklist item")
            if packet.get("component_id") != component_id:
                raise ValueError("bridge packet component_id does not match worklist item")
            if packet.get("port_id") != port_id:
                raise ValueError("bridge packet port_id does not match worklist item")
            if not math.isclose(
                float(packet.get("failure_opening_diameter_m")),
                diameter,
                rel_tol=1e-10,
                abs_tol=1e-12,
            ):
                raise ValueError("bridge packet opening does not match worklist item")
            packets.append(packet)
            bridge_verification = json.loads(completed.stdout)
            row.update(
                {
                    "status": "PACKET_BUILT_SYNTHETIC",
                    "duration_s": packet["duration_s"],
                    "provider_mass_residual_kg": provider_meta["max_abs_mass_residual_kg"],
                    "bridge_rate_intervals": bridge_verification["rate_intervals"],
                    "bridge_max_relative_rate_error": max(
                        interval["relative_rate_error"]
                        for interval in bridge_verification["rate_intervals"]
                    ),
                    "provider_termination_basis": provider_export["termination_basis"],
                }
            )
        except Exception as error:  # preserve each unsupported case, never abort the set
            row["status"] = "UNCOMPUTED"
            row["blocking_reason"] = f"{type(error).__name__}: {error}"
        case_rows.append(row)
        _save(case_dir / "case_verification.json", row)

    catalog_path = output_dir / "provider_release_catalog.json"
    _save(catalog_path, {"releases": packets})
    # ``load_provider_release_catalog`` deliberately rejects an empty catalog.
    # A diagnostic campaign must still emit a useful zero-packet coverage
    # ledger when every provider case is unavailable, so pass an empty tuple in
    # that case while retaining strict validation for every non-empty catalog.
    provider_packets = (
        load_provider_release_catalog(catalog_path) if packets else ()
    )
    coverage = audit_provider_catalog_coverage(worklist, provider_packets)
    _save(output_dir / "provider_catalog_coverage.json", coverage)
    report = {
        "status": "SYNTHETIC_PROVIDER_PACKET_DIAGNOSTIC",
        "provider_model": "lh2dt.LayeredTankNetworkSimulator",
        "component_id": component_id,
        "case_count": len(case_rows),
        "packet_count": len(packets),
        "uncomputed_case_count": sum(row["status"] == "UNCOMPUTED" for row in case_rows),
        "coverage_status": coverage["status"],
        "coverage_exact_match_count": coverage["exact_match_count"],
        "coverage_unmatched_event_count": coverage["unmatched_event_count"],
        "synthetic_diagnostic": True,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "cases": case_rows,
    }
    _save(output_dir / "campaign_verification.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--slabx-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--component-id", default="storage-tank-01")
    parser.add_argument("--target-release-kg", type=float, default=1.0e-4)
    parser.add_argument("--max-intervals", type=int, default=32)
    parser.add_argument("--reference-time-step-s", type=float, default=0.001)
    args = parser.parse_args()
    try:
        worklist = json.loads(args.provider_worklist.read_text(encoding="utf-8"))
        report = build_packets(
            worklist,
            lh2dt_root=args.lh2dt_root,
            slabx_root=args.slabx_root,
            output_dir=args.output_dir,
            component_id=args.component_id,
            target_release_kg=args.target_release_kg,
            max_intervals=args.max_intervals,
            reference_time_step_s=args.reference_time_step_s,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"LayeredTank worklist packet build failed: {error}") from error
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
