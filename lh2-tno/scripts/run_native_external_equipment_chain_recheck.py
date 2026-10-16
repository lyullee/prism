"""Replay seven saved native LH2 packets through the PRISM consequence chain.

This is the second half of the native-equipment recheck.  The first runner
executes external ``lh2dt`` exporters; this runner consumes those exact
``resolved_release.v1`` packets.  The high-speed valve uses the explicit
compressible-plane handoff, while the other six packets use the ordinary
SLABx-LH2 consequence path.  Every result remains diagnostic-only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def chain_commands(
    packet_root: Path,
    output_root: Path,
    *,
    backend_config: Path,
    facility: Path,
    context: Path,
) -> dict[str, list[str]]:
    """Return the exact six ordinary and one compressible replay commands."""

    ordinary = {
        "tank": "tank",
        "pipe": "pipe",
        "pump": "pump",
        "vaporizer": "vaporizer",
        "reliquefier": "reliquefier",
        "vent": "vent",
    }
    commands: dict[str, list[str]] = {}
    for name, folder in ordinary.items():
        commands[name] = [
            sys.executable,
            str(ROOT / "scripts/validate_lh2dt_prism_packet_chain.py"),
            "--packet", str(packet_root / folder / "resolved_release.json"),
            "--output-dir", str(output_root / folder),
            "--backend-config", str(backend_config),
        ]
    commands["valve_compressible"] = [
        sys.executable,
        str(ROOT / "scripts/run_compressible_plane_chain.py"),
        "--packet", str(packet_root / "valve" / "resolved_release.json"),
        "--handoff", str(packet_root / "valve" / "compressible_handoff.json"),
        "--facility", str(facility),
        "--context", str(context),
        "--backend-config", str(backend_config),
        "--output-dir", str(output_root / "valve_compressible"),
    ]
    return commands


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def run(
    *,
    packet_root: Path,
    output_root: Path,
    backend_config: Path,
    facility: Path,
    context: Path,
) -> dict[str, Any]:
    if not packet_root.is_dir():
        raise FileNotFoundError(f"packet root does not exist: {packet_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    commands = chain_commands(
        packet_root,
        output_root,
        backend_config=backend_config,
        facility=facility,
        context=context,
    )
    chains: list[dict[str, Any]] = []
    for name, command in commands.items():
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        result_dir = output_root / ("valve_compressible" if name == "valve_compressible" else name)
        record: dict[str, Any] = {
            "equipment": name,
            "command": command,
            "exit_code": completed.returncode,
            "stdout": (completed.stdout + completed.stderr).strip(),
        }
        verification_path = result_dir / "verification.json"
        if verification_path.exists():
            verification = _load(verification_path)
            record.update({
                key: verification[key]
                for key in (
                    "status", "chain_status", "full_chain_executed", "consequence_chain_executed",
                    "provider_handoff_consumed", "provider_duration_s", "provider_mass_residual_kg",
                    "provider_packet_promoted", "physical_validation_claim", "frequency_inference",
                    "facility_qra_claim", "operator_limited", "max_mach_number",
                )
                if key in verification
            })
        chains.append(record)
        if completed.returncode != 0 or not verification_path.exists():
            raise RuntimeError(f"{name} chain failed: {completed.stdout}{completed.stderr}")

    manifest = {
        "schema_version": "prism.native_external_multi_equipment_chain_recheck.v1",
        "status": "NATIVE_EXTERNAL_MULTI_EQUIPMENT_CHAIN_EXECUTED_DIAGNOSTIC",
        "chain_count": len(chains),
        "chains": chains,
        "provider_packet_promoted_count": sum(bool(row.get("provider_packet_promoted")) for row in chains),
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic facility, weather, receptors and ignition context",
            "no initiating frequency was applied or inferred",
            "provider qualification and independent physical validation remain open",
            "facility IR/F-N is not promoted from single-packet diagnostics",
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--facility", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = run(
            packet_root=args.packet_root,
            output_root=args.output_dir,
            backend_config=args.backend_config,
            facility=args.facility,
            context=args.context,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"native external equipment chain recheck failed: {error}") from error
    print(json.dumps({
        "status": manifest["status"],
        "chain_count": manifest["chain_count"],
        "provider_packet_promoted_count": manifest["provider_packet_promoted_count"],
        "output": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
