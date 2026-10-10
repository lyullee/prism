"""Audit qualification sidecars referenced by a generic LH2 evidence catalogue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.generic_provider_evidence_audit import (  # noqa: E402
    audit_generic_provider_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", required=True, type=Path)
    parser.add_argument("--packet-root", type=Path)
    parser.add_argument("--sidecar-manifest", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit_generic_provider_evidence(
        args.catalogue,
        packet_root=args.packet_root,
        sidecar_manifest=args.sidecar_manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "request_count": result["request_count"],
        "exact_match_count": result["exact_match_count"],
        "qualified_provider_packet_count": result["qualified_provider_packet_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
