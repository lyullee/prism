"""Cross-check the published PRISM readiness and facility ledgers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.status_consistency import (  # noqa: E402
    build_status_consistency_report,
    load_json_object,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-status", type=Path, required=True)
    parser.add_argument("--development-goal", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--evidence-request", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument(
        "--provider-packet-input-audit",
        type=Path,
        help="optional current provider release/qualification input audit",
    )
    parser.add_argument(
        "--observed-state-release-binding-audit",
        type=Path,
        help="optional observed-state to provider-release binding audit",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_status_consistency_report(
            current_status=load_json_object(args.current_status),
            development_goal=load_json_object(args.development_goal),
            audit=load_json_object(args.audit),
            assessment=load_json_object(args.assessment),
            evidence_request=load_json_object(args.evidence_request),
            ledger=load_json_object(args.ledger),
            coverage=load_json_object(args.coverage),
            audit_filename=args.audit.name,
            assessment_filename=args.assessment.name,
            evidence_request_filename=args.evidence_request.name,
            ledger_filename=args.ledger.name,
            coverage_filename=args.coverage.name,
            provider_packet_input_audit=(
                load_json_object(args.provider_packet_input_audit)
                if args.provider_packet_input_audit is not None
                else None
            ),
            provider_packet_input_audit_filename=(
                args.provider_packet_input_audit.name
                if args.provider_packet_input_audit is not None
                else None
            ),
            observed_state_release_binding_audit=(
                load_json_object(args.observed_state_release_binding_audit)
                if args.observed_state_release_binding_audit is not None
                else None
            ),
            observed_state_release_binding_audit_filename=(
                args.observed_state_release_binding_audit.name
                if args.observed_state_release_binding_audit is not None
                else None
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"status consistency input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "check_count": len(report["checks"]),
        "blocking_reason_count": len(report["blocking_reasons"]),
        "facility_ir_fn_promotion": report["facility_ir_fn_promotion"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "CONSISTENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
