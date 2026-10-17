"""Audit a facility evidence request against its provider intake template."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.facility_provider_intake import (  # noqa: E402
    audit_facility_provider_intake_template,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility-request", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit_facility_provider_intake_template(
        _load(args.facility_request), _load(args.template)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "request_case_count": report["request_case_count"],
        "template_entry_count": report["template_entry_count"],
        "blocking_reason_count": len(report["blocking_reasons"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "ALIGNED_TEMPLATE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
