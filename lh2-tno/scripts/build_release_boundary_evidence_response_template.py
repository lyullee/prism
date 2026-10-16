"""Build a blank provider-response template from open release requests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.release_boundary_evidence_intake import (  # noqa: E402
    build_release_boundary_evidence_response_template,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requests = json.loads(args.requests.read_text(encoding="utf-8-sig"))
    if not isinstance(requests, dict):
        raise SystemExit("request file must contain an object")
    report = build_release_boundary_evidence_response_template(requests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "response_count": len(report["responses"]), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
