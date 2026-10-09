"""Inventory external digital-twin JSON outputs without QRA promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_artifact_audit import audit_provider_artifact_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_provider_artifact_root(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "artifact_count": report["artifact_count"],
        "provider_response_count": report["provider_response_count"],
        "qualification_artifact_count": report["qualification_artifact_count"],
        "physical_validation_artifact_count": report["physical_validation_artifact_count"],
        "complete_facility_qra_artifact_count": report["complete_facility_qra_artifact_count"],
    }, ensure_ascii=False))
    return 0 if report["status"] != "MISSING_SOURCE_ROOT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
