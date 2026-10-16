"""Validate provider responses against open PRISM release requests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.release_boundary_evidence_intake import (  # noqa: E402
    build_provider_termination_evidence_catalog,
    validate_release_boundary_evidence_response,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--catalog-output",
        type=Path,
        help="Optional provider-termination catalog for the case-level audit.",
    )
    parser.add_argument(
        "--facility-assessment",
        type=Path,
        help="Optional facility assessment to re-audit with --catalog-output.",
    )
    parser.add_argument(
        "--facility-evidence-request",
        type=Path,
        help="Optional case-level evidence request catalog used with --facility-assessment.",
    )
    parser.add_argument(
        "--case-audit-output",
        type=Path,
        help="Optional output path for the case-level release-boundary re-audit.",
    )
    args = parser.parse_args()
    requests = json.loads(args.requests.read_text(encoding="utf-8-sig"))
    responses = json.loads(args.responses.read_text(encoding="utf-8-sig"))
    if not isinstance(requests, dict) or not isinstance(responses, (dict, list)):
        raise SystemExit("requests must be an object and responses must be an object or array")
    report = validate_release_boundary_evidence_response(requests, responses)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog = None
    if args.catalog_output is not None or args.case_audit_output is not None:
        catalog = build_provider_termination_evidence_catalog(
            requests,
            responses,
            validation_report=report,
        )
    if args.catalog_output is not None:
        args.catalog_output.parent.mkdir(parents=True, exist_ok=True)
        args.catalog_output.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.case_audit_output is not None:
        if args.facility_assessment is None:
            raise SystemExit("--case-audit-output requires --facility-assessment")
        if args.facility_evidence_request is None:
            raise SystemExit("--case-audit-output requires --facility-evidence-request")
        from lh2_tno.release_boundary_case_audit import (  # noqa: E402
            build_release_boundary_case_audit,
        )

        assessment = json.loads(args.facility_assessment.read_text(encoding="utf-8-sig"))
        evidence_request = json.loads(
            args.facility_evidence_request.read_text(encoding="utf-8-sig")
        )
        if not isinstance(assessment, dict) or not isinstance(evidence_request, dict):
            raise SystemExit("facility assessment and evidence request must be JSON objects")
        case_audit = build_release_boundary_case_audit(
            assessment,
            facility_evidence_request=evidence_request,
            provider_termination_evidence=catalog,
        )
        args.case_audit_output.parent.mkdir(parents=True, exist_ok=True)
        args.case_audit_output.write_text(
            json.dumps(case_audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"status": report["status"], "ready_count": report["ready_count"], "row_count": report["row_count"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
