#!/usr/bin/env python3
"""Rebaseline an external field manifest to the current channel bytes.

This is a provenance repair step only.  It never promotes observations to an
accident release, frequency, or physical-validation claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.field_manifest_rebaseline import (  # noqa: E402
    FieldManifestRebaselineError,
    rebaseline_field_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-id")
    parser.add_argument(
        "--acknowledge-source-rebaseline",
        action="store_true",
        help="acknowledge that hashes are being replaced with current file bytes",
    )
    args = parser.parse_args()
    try:
        report = rebaseline_field_manifest(
            args.manifest,
            acknowledged=args.acknowledge_source_rebaseline,
            manifest_id=args.manifest_id,
        )
    except (FieldManifestRebaselineError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"field manifest rebaseline input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = report["field_evidence_manifest"]
    print(json.dumps({
        "status": report["rebaseline"]["status"],
        "manifest_id": manifest["manifest_id"],
        "promotion_allowed": manifest["promotion_allowed"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
