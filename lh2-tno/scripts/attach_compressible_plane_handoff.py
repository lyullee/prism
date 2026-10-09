"""Attach a provider-owned compressible plane to one exact PRISM gas packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.compressible_handoff import (  # noqa: E402
    CompressibleHandoffExportError,
    attach_compressible_plane_handoff,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True, help="upstream resolved_release.json")
    parser.add_argument("--handoff", type=Path, required=True, help="provider handoff export JSON")
    parser.add_argument("--output-packet", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    args = parser.parse_args()
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
        result, audit = attach_compressible_plane_handoff(packet, handoff)
        args.output_packet.parent.mkdir(parents=True, exist_ok=True)
        args.output_audit.parent.mkdir(parents=True, exist_ok=True)
        args.output_packet.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        args.output_audit.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(audit, ensure_ascii=False))
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError,
            CompressibleHandoffExportError) as error:
        audit = {
            "status": "COMPRESSIBLE_PLANE_HANDOFF_ATTACH_BLOCKED",
            "error": f"{type(error).__name__}: {error}",
            "provider_packet_qualified": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        }
        args.output_audit.parent.mkdir(parents=True, exist_ok=True)
        args.output_audit.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(audit, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
