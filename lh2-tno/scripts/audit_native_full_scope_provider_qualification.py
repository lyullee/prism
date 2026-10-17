"""Audit sidecars for the native full-scope provider request catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.native_provider_qualification_audit import (  # noqa: E402
    audit_native_full_scope_provider_qualification,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", required=True, type=Path)
    parser.add_argument("--packet-root", type=Path)
    parser.add_argument("--sidecar-manifest", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit_native_full_scope_provider_qualification(
        args.catalogue,
        packet_root=args.packet_root,
        sidecar_manifest=args.sidecar_manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "event_row_count": report["event_row_count"],
        "release_identity_request_count": report["release_identity_request_count"],
        "exact_match_count": report["exact_match_count"],
        "qualified_provider_packet_count": report["qualified_provider_packet_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
