"""Review external provider artifacts against current generic packet identities."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_artifact_match_review import (  # noqa: E402
    audit_external_provider_artifact_matches,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--closure-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_external_provider_artifact_matches(args.source_root, args.closure_audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "candidate_count": report["candidate_count"],
        "exact_match_count": report["exact_match_count"],
        "qualification_artifact_count": report["qualification_artifact_count"],
        "physical_validation_artifact_count": report["physical_validation_artifact_count"],
        "complete_facility_qra_artifact_count": report["complete_facility_qra_artifact_count"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "EXACT_MATCH_REQUIRES_QUALIFICATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
