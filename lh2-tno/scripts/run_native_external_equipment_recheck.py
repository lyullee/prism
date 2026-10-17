"""Run the native external LH2 equipment exporters as one diagnostic recheck.

The external ``lh2dt`` tree remains the owner of the transient accident
history.  This runner only orchestrates the existing equipment adapters and
records their exact packet identities in one manifest.  It deliberately keeps
the result diagnostic: a native packet is not promoted to a qualified field
release, a literature frequency, or a facility IR/F-N value by this command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def tree_digest(root: Path) -> str:
    """Return a stable digest for the Python sources in an external model tree."""

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def exporter_commands(root: Path, output_dir: Path) -> dict[str, list[str]]:
    """Build the fixed, reviewable seven-equipment diagnostic command set."""

    common = ["--lh2dt-root", str(root)]
    return {
        "layered_tank": [
            sys.executable,
            str(ROOT / "scripts/export_lh2dt_native_layered_tank_prism_packet.py"),
            *common,
            "--output-dir", str(output_dir / "tank"),
            "--horizon-s", "0.5", "--time-step-s", "0.1",
            "--isolation-time-s", "0.2", "--post-isolation-observation-s", "0.1",
        ],
        "dynamic_pipe": [
            sys.executable,
            str(ROOT / "scripts/export_lh2dt_native_dynamic_pipe_prism_packet.py"),
            *common,
            "--output-dir", str(output_dir / "pipe"),
            "--horizon-s", "0.1", "--time-step-s", "0.05",
            "--isolation-time-s", "0.05", "--post-isolation-observation-s", "0.01",
        ],
        "stroke_limited_valve": [
            sys.executable,
            str(ROOT / "scripts/export_lh2dt_native_valve_prism_packet.py"),
            *common,
            "--output-dir", str(output_dir / "valve"),
            "--horizon-s", "0.1", "--time-step-s", "0.05",
            "--compressible-handoff",
        ],
        "mapped_pump": [
            sys.executable,
            str(ROOT / "scripts/export_lh2dt_native_mapped_pump_prism_packet.py"),
            *common,
            "--output-dir", str(output_dir / "pump"),
            "--horizon-s", "0.1", "--time-step-s", "0.05",
            "--isolation-time-s", "0.05", "--post-isolation-observation-s", "0.05",
        ],
        "dynamic_vaporizer": [
            sys.executable,
            str(ROOT / "scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py"),
            *common,
            "--output-dir", str(output_dir / "vaporizer"),
            "--mode", "vaporizer", "--horizon-s", "0.1", "--time-step-s", "0.05",
            "--isolation-time-s", "0.05", "--post-isolation-observation-s", "0.05",
        ],
        "dynamic_reliquefier": [
            sys.executable,
            str(ROOT / "scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py"),
            *common,
            "--output-dir", str(output_dir / "reliquefier"),
            "--mode", "reliquefier", "--horizon-s", "0.1", "--time-step-s", "0.05",
            "--isolation-time-s", "0.05", "--post-isolation-observation-s", "0.05",
        ],
        "vent_stack": [
            sys.executable,
            str(ROOT / "scripts/export_lh2dt_native_vent_stack_prism_packet.py"),
            *common,
            "--output-dir", str(output_dir / "vent"),
            "--horizon-s", "0.1", "--time-step-s", "0.05",
        ],
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def summarise_packet(name: str, packet_dir: Path, command: list[str], *, exit_code: int, stdout: str) -> dict[str, Any]:
    """Collect the provider and PRISM identity fields without reinterpreting them."""

    verification_path = packet_dir / "verification.json"
    summary: dict[str, Any] = {
        "equipment": name,
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout.strip(),
        "verification_present": verification_path.exists(),
    }
    if verification_path.exists():
        verification = _load_json(verification_path)
        for key in (
            "status", "provider_model", "provider_export_schema", "provider_method",
            "provider_source_digest", "provider_result_digest", "termination_basis",
            "duration_s", "isolation_time_s", "post_isolation_observation_s",
            "isolation_success", "provider_packet_promoted", "physical_validation_claim",
            "frequency_inference_performed", "facility_qra_claim", "state_snapshot_digest_match",
            "isolation_success", "phase_basis", "source_phase",
            "dynamic_state_closure",
        ):
            if key in verification:
                summary[key] = verification[key]
    return summary


def run(*, lh2dt_root: Path, output_dir: Path) -> dict[str, Any]:
    root = lh2dt_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"external lh2dt root does not exist: {root}")
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = exporter_commands(root, output_dir)
    packets: list[dict[str, Any]] = []
    for name, command in commands.items():
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        packet = summarise_packet(
            name,
            output_dir / {
                "layered_tank": "tank", "dynamic_pipe": "pipe",
                "stroke_limited_valve": "valve", "mapped_pump": "pump",
                "dynamic_vaporizer": "vaporizer", "dynamic_reliquefier": "reliquefier",
                "vent_stack": "vent",
            }[name],
            command,
            exit_code=completed.returncode,
            stdout=completed.stdout + completed.stderr,
        )
        packets.append(packet)
        if completed.returncode != 0:
            raise RuntimeError(f"{name} exporter failed with exit code {completed.returncode}: {completed.stdout}{completed.stderr}")
        if not packet["verification_present"]:
            raise RuntimeError(f"{name} exporter completed without verification.json")

    promoted_count = sum(bool(packet.get("provider_packet_promoted")) for packet in packets)
    manifest = {
        "schema_version": "prism.native_external_multi_equipment_recheck.v1",
        "status": "NATIVE_EXTERNAL_MULTI_EQUIPMENT_RECHECK_EXECUTED_DIAGNOSTIC",
        "external_root": str(root),
        "external_source_digest": tree_digest(root),
        "equipment_count": len(packets),
        "equipment": packets,
        "provider_packet_promoted_count": promoted_count,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "limitations": [
            "all geometry, boundary conditions and initial states are diagnostic inputs unless independently qualified",
            "native exporter termination is preserved but does not establish field isolation reliability",
            "no sensor-based frequency learning or frequency assignment is performed",
            "SLABx-LH2 consequence execution and facility IR/F-N promotion remain separate gates",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = run(lh2dt_root=args.lh2dt_root, output_dir=args.output_dir)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"native external multi-equipment recheck failed: {error}") from error
    print(json.dumps({
        "status": manifest["status"],
        "equipment_count": manifest["equipment_count"],
        "provider_packet_promoted_count": manifest["provider_packet_promoted_count"],
        "output": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
