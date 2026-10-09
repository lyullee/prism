"""Export a facility-neutral native LH2 packet catalog for every scope event.

The generic full-scope manifest is deliberately synthetic.  This command uses
the external ``lh2dt`` accident-export adapters for each of its 24 frequency
events, checks exact event/component/port identity, and writes separate PRISM
catalogs for accidental releases, emergency relief, and two-sided rupture.

The output is a structural diagnostic catalog.  It never copies frequency into
the packets, promotes synthetic evidence, or claims facility qualification.
Failed exports stay in the verification ledger as uncomputed events.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan, FrequencyEvent, generate_events


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _port_by_component(manifest: EquipmentManifest, component_id: str) -> str:
    candidates = [
        port.id
        for port in manifest.ports
        if port.component_id == component_id and "accident" in port.id
    ]
    if len(candidates) != 1:
        raise ValueError(f"expected one accident port for {component_id}, got {candidates}")
    return candidates[0]


def _event_port(manifest: EquipmentManifest, event: FrequencyEvent) -> str:
    if event.model_component_id == "reliquefier-01":
        return "reliquefier-accident-out-1"
    return _port_by_component(manifest, event.model_component_id)


def _spec(
    event: FrequencyEvent,
    manifest: EquipmentManifest,
    output_dir: Path,
    root: Path,
    *,
    event_index: int,
) -> dict[str, Any]:
    """Return one reproducible exporter command specification."""
    event_dir = output_dir / "events" / f"{event_index:03d}_{event.model_component_id}_{event.loc.replace('%', 'pct')}"
    script: str
    args: list[str] = []
    port = _event_port(manifest, event)
    common = [
        "--lh2dt-root", str(root),
        "--output-dir", str(event_dir),
        "--component-id", event.model_component_id,
        "--event-id", event.id,
    ]
    if event.model_component_id == "storage-tank-01":
        script = "export_lh2dt_layered_tank_prism_packet.py"
        area = math.pi * float(event.release.hole_diameter_m) ** 2 / 4.0
        args = [
            "--time-step-s", "0.05", "--target-release-kg", "0.0001",
            "--max-intervals", "64", "--full-open-area-m2", repr(area),
            "--port-id", port, "--nozzle-height-m", "1.0",
        ]
    elif event.model_component_id == "liquid-transfer-line-01":
        script = "export_lh2dt_dynamic_pipe_prism_packet.py"
        args = [
            "--duration-s", "0.001", "--time-step-s", "0.0001",
            "--length-m", "1.0", "--inner-diameter-m", repr(float(event.release.hole_diameter_m)),
            "--port-id", port, "--nozzle-height-m", "1.0",
        ]
    elif event.model_component_id == "transfer-valve-01":
        script = "export_lh2dt_valve_prism_packet.py"
        args = [
            "--duration-s", "0.2", "--time-step-s", "0.02",
            "--opening-diameter-m", repr(float(event.release.hole_diameter_m)),
            "--port-id", port, "--nozzle-height-m", "0.5",
        ]
    elif event.model_component_id == "pressure-relief-vent-01":
        script = "export_lh2dt_vent_stack_prism_packet.py"
        args = ["--port-id", port, "--nozzle-height-m", "2.0"]
    elif event.model_component_id == "liquid-transfer-pump-01":
        script = "export_lh2dt_mapped_pump_prism_packet.py"
        args = [
            "--duration-s", "0.2", "--time-step-s", "0.02",
            "--opening-diameter-m", repr(float(event.release.hole_diameter_m)),
            "--port-id", port, "--nozzle-height-m", "0.5",
        ]
    elif event.model_component_id == "ambient-vaporizer-01":
        if event.release.mode == "instantaneous_inventory":
            script = "export_lh2dt_dynamic_vaporizer_inventory_prism_packet.py"
            args = [
                "--mode", "vaporizer", "--release-mode", "instantaneous_inventory",
                "--duration-s", "600.0", "--time-step-s", "0.1", "--port-id", port,
            ]
        elif event.release.mode == "inventory_over_600s":
            script = "export_lh2dt_dynamic_vaporizer_inventory_prism_packet.py"
            args = [
                "--mode", "vaporizer", "--release-mode", "inventory_over_600s",
                "--duration-s", "600.0", "--time-step-s", "0.1", "--port-id", port,
            ]
        else:
            script = "export_lh2dt_dynamic_vaporizer_prism_packet.py"
            args = [
                "--mode", "vaporizer", "--opening-diameter-m", repr(float(event.release.hole_diameter_m)),
                "--port-id", port,
            ]
    elif event.model_component_id == "reliquefier-01":
        if event.release.mode == "two_sided_rupture":
            script = "export_lh2dt_reliquefier_two_sided_prism_packet.py"
            args = [
                "--opening-diameter-m", repr(float(event.release.hole_diameter_m)),
                "--component-id", event.model_component_id,
            ]
        else:
            script = "export_lh2dt_dynamic_vaporizer_prism_packet.py"
            args = [
                "--mode", "reliquefier", "--opening-diameter-m", repr(float(event.release.hole_diameter_m)),
                "--port-id", port,
            ]
    else:
        raise ValueError(f"no native exporter mapping for {event.model_component_id}")
    # Two-sided exporter needs the exact event id but creates its own two endpoint ports.
    if event.model_component_id == "reliquefier-01" and event.release.mode == "two_sided_rupture":
        command = [sys.executable, str(ROOT / "scripts" / script), *common, *args]
    else:
        command = [sys.executable, str(ROOT / "scripts" / script), *common, *args]
    return {
        "event_id": event.id,
        "component_id": event.model_component_id,
        "profile": event.profile,
        "mode": event.release.mode,
        "opening_diameter_m": event.release.hole_diameter_m,
        "port_id": port,
        "script": script,
        "event_dir": event_dir,
        "command": command,
    }


def _load_packet(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    event_dir = Path(spec["event_dir"])
    set_path = event_dir / "resolved_release_set.json"
    release_path = event_dir / "resolved_release.json"
    if set_path.exists():
        return "two_sided", json.loads(set_path.read_text(encoding="utf-8"))
    if release_path.exists():
        return "release", json.loads(release_path.read_text(encoding="utf-8"))
    raise ValueError("exporter produced neither resolved_release.json nor resolved_release_set.json")


def _replace_flag(command: list[str], flag: str, value: str) -> list[str]:
    """Return a command with one explicit CLI flag replaced."""

    result = list(command)
    try:
        index = result.index(flag)
    except ValueError as error:
        raise ValueError(f"exporter command has no {flag} flag") from error
    if index + 1 >= len(result):
        raise ValueError(f"exporter command has no value after {flag}")
    result[index + 1] = value
    return result


def _retry_commands(spec: dict[str, Any]) -> list[list[str]]:
    """Return safe numerical retries without changing the physical opening.

    The external LayeredTank and DynamicHEMPipe providers can become unstable
    at the largest declared openings with the default diagnostic clock.  The
    retries shorten the provider horizon and refine its integration step while
    preserving the event's exact opening diameter/area.  No retry is supplied
    for MappedPump: its failure is a hydraulic map-to-valve mismatch and must
    be resolved with a reviewed pump map or feed boundary.
    """

    command = list(spec["command"])
    if spec["component_id"] == "storage-tank-01":
        # The 1.27 m generic tank is intentionally much larger than the
        # external diagnostic vessel.  Large openings need a micro-step to
        # keep the provider's positive-mass/EOS solve finite.
        retry = _replace_flag(command, "--time-step-s", "0.000001")
        retry = _replace_flag(retry, "--target-release-kg", "0.00001")
        retry = _replace_flag(retry, "--max-intervals", "256")
        return [retry]
    if spec["component_id"] == "liquid-transfer-line-01" and float(spec["opening_diameter_m"]) >= 0.02:
        retry = _replace_flag(command, "--duration-s", "0.0001")
        retry = _replace_flag(retry, "--time-step-s", "0.00001")
        return [retry]
    return []


def _validate_packet(spec: dict[str, Any], kind: str, packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if kind == "two_sided":
        if packet.get("provider_export_schema") != "prism.resolved_release_set.v1":
            errors.append("two-sided schema mismatch")
        if packet.get("event_id") != spec["event_id"]:
            errors.append("two-sided event_id mismatch")
        rows = packet.get("releases", [])
        if len(rows) != 2:
            errors.append("two-sided endpoint count is not two")
        expected_ports = {"reliquefier-accident-out-1", "reliquefier-accident-out-2"}
        if {row.get("port_id") for row in rows} != expected_ports:
            errors.append("two-sided endpoint ports mismatch")
        for row in rows:
            if row.get("event_id") != spec["event_id"] or row.get("component_id") != spec["component_id"]:
                errors.append("two-sided endpoint identity mismatch")
        return errors
    if packet.get("event_id") != spec["event_id"]:
        errors.append("event_id mismatch")
    if packet.get("component_id") != spec["component_id"]:
        errors.append("component_id mismatch")
    if packet.get("port_id") != spec["port_id"]:
        errors.append("port_id mismatch")
    if packet.get("provider_export_schema") != "prism.resolved_release.v1":
        errors.append("provider schema mismatch")
    return errors


def build_catalog(args: argparse.Namespace) -> dict[str, Any]:
    manifest = EquipmentManifest.from_json(args.manifest)
    facility = manifest.to_facility()
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    events = generate_events(facility, plan)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_digest = _tree_digest(args.lh2dt_root.resolve())
    rows: list[dict[str, Any]] = []
    successful: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    failures: list[dict[str, Any]] = []
    for event_index, event in enumerate(events):
        spec = _spec(event, manifest, output_dir, args.lh2dt_root.resolve(), event_index=event_index)
        attempts: list[dict[str, Any]] = []
        commands = [spec["command"], *_retry_commands(spec)]
        completed = None
        for attempt_index, command in enumerate(commands):
            if attempt_index > 0:
                # The previous provider may have written partial diagnostics
                # before failing.  A retry must be read as one atomic packet.
                shutil.rmtree(spec["event_dir"], ignore_errors=True)
                Path(spec["event_dir"]).mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            attempts.append({
                "attempt_index": attempt_index,
                "command": command,
                "returncode": completed.returncode,
                "stderr_tail": completed.stderr[-2000:],
            })
            if completed.returncode == 0:
                break
        assert completed is not None
        row = {
            "event_id": event.id,
            "component_id": event.model_component_id,
            "profile": event.profile,
            "mode": event.release.mode,
            "script": spec["script"],
            "event_dir": str(Path(spec["event_dir"]).relative_to(output_dir)).replace("\\", "/"),
            "returncode": completed.returncode,
            "attempts": attempts,
        }
        if completed.returncode != 0:
            row["status"] = "UNCOMPUTED_EXPORT_FAILED"
            row["stderr_tail"] = completed.stderr[-2000:]
            failures.append(row)
            rows.append(row)
            continue
        try:
            kind, packet = _load_packet(spec)
            errors = _validate_packet(spec, kind, packet)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            kind, packet, errors = "unknown", {}, [str(error)]
        if errors:
            row["status"] = "UNCOMPUTED_PACKET_IDENTITY"
            row["errors"] = errors
            failures.append(row)
            rows.append(row)
            continue
        row.update({
            "status": "EXACT_NATIVE_PACKET",
            "packet_kind": kind,
            "retry_used": len(attempts) > 1,
        })
        successful.append((spec, kind, packet))
        rows.append(row)

    accidental = [packet for spec, kind, packet in successful if kind == "release" and packet.get("event_kind") == "accidental_leak"]
    relief = [packet for spec, kind, packet in successful if kind == "release" and packet.get("event_kind") == "emergency_relief"]
    rupture = [packet for spec, kind, packet in successful if kind == "two_sided"]
    _save(output_dir / "accidental_catalog.json", {"releases": accidental})
    _save(output_dir / "emergency_relief_catalog.json", {"releases": relief})
    _save(output_dir / "two_sided_catalog.json", {"release_sets": rupture})
    verification = {
        "schema_version": "prism.native_generic_scope_packet_catalog.v1",
        "status": "NATIVE_GENERIC_SCOPE_PACKET_CATALOG_EXECUTED" if not failures else "NATIVE_GENERIC_SCOPE_PACKET_CATALOG_PARTIAL",
        "manifest": str(args.manifest),
        "frequency_plan": str(args.frequency_plan),
        "external_model_root": str(args.lh2dt_root.resolve()),
        "external_model_source_digest": source_digest,
        "frequency_event_count": len(events),
        "exact_native_packet_count": len(successful),
        "uncomputed_event_count": len(failures),
        "retry_succeeded_event_count": sum(1 for row in rows if row.get("retry_used")),
        "event_rows": rows,
        "catalog_counts": {
            "accidental_release": len(accidental),
            "emergency_relief": len(relief),
            "two_sided_rupture": len(rupture),
        },
        "catalogs": {
            "accidental_release": "accidental_catalog.json",
            "emergency_relief": "emergency_relief_catalog.json",
            "two_sided_rupture": "two_sided_catalog.json",
        },
        "provider_packet_promoted": False,
        "frequency_inference_performed": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "limitations": [
            "generic manifest and all exporter states are synthetic diagnostic inputs",
            "frequency remains in the separate literature frequency plan",
            "packet identity coverage does not establish qualified provider evidence or facility IR/F-N",
            "failed exports remain explicit uncomputed worklist events",
        ],
    }
    _save(output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_catalog(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"native generic scope packet catalog failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "frequency_event_count": result["frequency_event_count"],
        "exact_native_packet_count": result["exact_native_packet_count"],
        "uncomputed_event_count": result["uncomputed_event_count"],
        "output": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
