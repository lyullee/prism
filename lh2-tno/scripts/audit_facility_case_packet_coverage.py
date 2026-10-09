"""Audit promoted provider evidence against every facility case request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.facility_case_packet_coverage import (  # noqa: E402
    audit_facility_case_packet_coverage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument(
        "--provider-evidence-catalog",
        type=Path,
        help="optional prism.provider_packet_evidence.v1 object/array",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        request_document = json.loads(args.requests.read_text(encoding="utf-8"))
        evidence = (
            json.loads(args.provider_evidence_catalog.read_text(encoding="utf-8"))
            if args.provider_evidence_catalog
            else ()
        )
        report = audit_facility_case_packet_coverage(request_document, evidence)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"facility case packet coverage input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "case_request_count": report["case_request_count"],
        "qualified_provider_case_count": report["qualified_provider_case_count"],
        "qualified_provider_event_count": report["qualified_provider_event_count"],
        "blocking_reasons": report["blocking_reasons"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "QUALIFIED_FULL_CASE_COVERAGE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
