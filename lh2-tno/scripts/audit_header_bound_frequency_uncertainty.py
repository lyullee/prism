from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.header_bound_frequency_uncertainty_audit import (  # noqa: E402
    audit_header_bound_frequency_uncertainty,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit explicit frequency-bound coverage in a header-bound facility bridge result."
    )
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    report = audit_header_bound_frequency_uncertainty(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(args.output),
                "bound": report["frequency_bound_scenario_count"],
                "unbound": report["frequency_unbound_scenario_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASS_DIAGNOSTIC_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

