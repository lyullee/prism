"""Audit the declared LH2 release-to-consequence backend chain."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.consequence_backend_chain_audit import (  # noqa: E402
    audit_consequence_backend_chain,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--backend-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_consequence_backend_chain(
            _load(args.campaign_result),
            _load(args.backend_contract),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"consequence backend chain input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "case_count": report["case_count"],
        "closed_case_count": report["closed_case_count"],
        "stage_count": report["stage_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "FULL_CONSEQUENCE_BACKEND_CHAIN_DIAGNOSTIC" else 2


if __name__ == "__main__":
    raise SystemExit(main())
