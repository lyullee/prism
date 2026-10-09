"""Validate a provider gas packet's low-Mach or compressible-plane boundary."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.provider_release import (  # noqa: E402
    ProviderReleaseContractError,
    load_provider_release,
)
from lh2_tno.resolved_gas_worker import resolve_gas_rows  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--ambient-pressure-pa", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        release = load_provider_release(args.packet)
        import CoolProp.CoolProp as cp

        ambient = (
            release.ambient_pressure_pa_abs
            if args.ambient_pressure_pa is None
            else args.ambient_pressure_pa
        )
        _, history = resolve_gas_rows(release.model_dump(mode="json"), ambient, cp)
        handoff = release.compressible_plane_handoff
        checks = history.get("thermodynamic_checks", [])
        output = {
            "status": (
                "COMPRESSIBLE_PLANE_HANDOFF_VALIDATED"
                if handoff is not None
                else "DIRECT_LOW_MACH_GAS_EXIT_VALIDATED"
            ),
            "event_id": release.event_id,
            "component_id": release.component_id,
            "provider_result_digest": release.provider_result_digest,
            "max_mach_number": max((row["mach_number"] for row in checks), default=None),
            "handoff_state_count": len(handoff.states) if handoff is not None and handoff.states else 1 if handoff is not None else 0,
            "handoff_consumed": bool(history.get("compressible_plane_handoff_consumed")),
            "provider_packet_qualified": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "interpretation": (
                "The provider-owned gas boundary is conservation-checked. This command does not "
                "assign frequency, qualify the provider, or promote facility IR/F-N."
            ),
        }
        exit_code = 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, ProviderReleaseContractError) as error:
        output = {
            "status": "COMPRESSIBLE_PLANE_HANDOFF_BLOCKED",
            "error": f"{type(error).__name__}: {error}",
            "provider_packet_qualified": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        }
        exit_code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
