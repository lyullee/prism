"""Validate provider responses against open PRISM release requests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.release_boundary_evidence_intake import (  # noqa: E402
    validate_release_boundary_evidence_response,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requests = json.loads(args.requests.read_text(encoding="utf-8-sig"))
    responses = json.loads(args.responses.read_text(encoding="utf-8-sig"))
    if not isinstance(requests, dict) or not isinstance(responses, (dict, list)):
        raise SystemExit("requests must be an object and responses must be an object or array")
    report = validate_release_boundary_evidence_response(requests, responses)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "ready_count": report["ready_count"], "row_count": report["row_count"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
