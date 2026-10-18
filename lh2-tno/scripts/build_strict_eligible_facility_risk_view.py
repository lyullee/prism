"""Build the strict-eligible diagnostic facility-risk contribution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.strict_eligible_facility_risk import build_strict_eligible_facility_risk_view


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility-assessment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    assessment = json.loads(args.facility_assessment.read_text(encoding="utf-8"))
    view = build_strict_eligible_facility_risk_view(assessment)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": view["status"], "selected_risk_atom_count": view["selected_risk_atom_count"], "excluded_risk_atom_count": view["excluded_risk_atom_count"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
