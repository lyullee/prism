"""Build a per-response qualification-gap ledger from a workspace scan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.external_provider_response_gap_audit import (  # noqa: E402
    audit_external_provider_response_gaps,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-record", type=Path, required=True)
    parser.add_argument("--root-label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_external_provider_response_gaps(
        args.scan_record,
        root_label=args.root_label,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "provider_response_count": report["provider_response_count"],
        "strict_termination_candidate_count": report["strict_termination_candidate_count"],
        "qualification_sidecar_count": report["qualification_sidecar_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
