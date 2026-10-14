"""Build the case-level release-boundary promotion audit for a facility assessment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.release_boundary_case_audit import build_release_boundary_case_audit  # noqa: E402


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument(
        "--facility-evidence-request",
        type=Path,
        help="optional exact facility case evidence-request catalog",
    )
    parser.add_argument(
        "--provider-termination-evidence",
        type=Path,
        help="optional provider-owned termination evidence catalog",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--residual-tolerance-kg", type=float, default=1e-8)
    args = parser.parse_args()
    try:
        provider_termination_evidence = (
            _object(args.provider_termination_evidence)
            if args.provider_termination_evidence
            else None
        )
        if provider_termination_evidence is not None:
            provider_termination_evidence["_record_path"] = str(
                args.provider_termination_evidence
            )
        report = build_release_boundary_case_audit(
            _object(args.facility_assessment),
            residual_tolerance_kg=args.residual_tolerance_kg,
            facility_evidence_request=(
                _object(args.facility_evidence_request)
                if args.facility_evidence_request
                else None
            ),
            provider_termination_evidence=(
                provider_termination_evidence
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"release boundary case audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "case_count": report["case_count"],
        "strict_release_boundary_eligible_case_count": report[
            "strict_release_boundary_eligible_case_count"
        ],
        "strict_release_boundary_blocked_case_count": report[
            "strict_release_boundary_blocked_case_count"
        ],
        "facility_ir_fn_promotion": report["facility_ir_fn_promotion"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "CASE_BOUNDARY_CLOSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
