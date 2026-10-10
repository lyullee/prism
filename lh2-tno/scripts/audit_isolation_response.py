"""Audit provider isolation success/failure responses and consumed campaign cases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.isolation_response_audit import audit_isolation_response_campaign  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-response", type=Path, required=True)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        provider_response = json.loads(args.provider_response.read_text(encoding="utf-8"))
        campaign_result = json.loads(args.campaign_result.read_text(encoding="utf-8"))
        report = audit_isolation_response_campaign(provider_response, campaign_result)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"isolation response audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "branch_count": report["branch_count"],
        "success_branch_count": report["success_branch_count"],
        "failure_branch_count": report["failure_branch_count"],
        "campaign_case_count": report["campaign_case_count"],
        "risk_atom_count": report["risk_atom_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "ISOLATION_RESPONSE_CHAIN_DIAGNOSTIC" else 2


if __name__ == "__main__":
    raise SystemExit(main())
