"""Audit release-shaped legacy outputs without modifying or promoting them."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.legacy_artifact_audit import audit_legacy_provider_artifacts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_legacy_provider_artifacts(args.provider_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "release_shaped_candidate_count": report["release_shaped_candidate_count"],
        "legacy_missing_schema_count": report["legacy_missing_schema_count"],
        "qualified_current_schema_count": report["qualified_current_schema_count"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "NO_RELEASE_SHAPED_ARTIFACTS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
