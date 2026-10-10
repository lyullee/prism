"""Build the facility release-closure worklist."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.release_closure_worklist import build_release_closure_worklist  # noqa: E402


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument("--facility-evidence-request", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = _load(args.facility_evidence_request) if args.facility_evidence_request else None
    report = build_release_closure_worklist(_load(args.facility_assessment), request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "case_count": report["case_count"],
        "open_case_count": report["open_case_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
