"""Create a fail-closed digest-bound SLABx-LH2 validation evidence ledger."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.slabx_validation_audit import (  # noqa: E402
    audit_slabx_lh2_validation_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument(
        "--source-file",
        action="append",
        default=[],
        help="relative source file under --source-root; may be repeated",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_slabx_lh2_validation_evidence(
            args.results,
            args.audit,
            source_root=args.source_root,
            relative_source_paths=args.source_file,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"SLABx validation audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "check_count": len(report["checks"]),
        "blocking_reason_count": len(report["blocking_reasons"]),
        "physical_validation_claim": report["physical_validation_claim"],
        "facility_qra_claim": report["facility_qra_claim"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
