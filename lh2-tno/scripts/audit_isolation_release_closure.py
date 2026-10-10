"""Audit isolation-success/failure termination and mass closure."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.isolation_release_closure import audit_isolation_release_closure  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_isolation_release_closure(
        args.campaign_result,
        verification=args.verification,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "case_count": report["case_count"],
        "success_case_count": report["success_case_count"],
        "failure_case_count": report["failure_case_count"],
        "maximum_mass_residual_kg": report["maximum_mass_residual_kg"],
        "qualified_provider_packet_case_count": report["qualified_provider_packet_case_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
