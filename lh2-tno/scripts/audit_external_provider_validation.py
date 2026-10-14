"""Build a restricted intake ledger for external provider validation evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.external_provider_validation import (  # noqa: E402
    ExternalProviderValidationError,
    audit_external_provider_validation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--provider-artifact-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_external_provider_validation(
            args.manifest,
            provider_artifact_root=args.provider_artifact_root,
        )
    except (ExternalProviderValidationError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"external provider validation intake error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "evidence_count": report["summary"]["evidence_count"],
        "promotion_blocked_count": report["summary"]["promotion_blocked_count"],
        "provider_artifact_count": report["provider_artifacts"]["artifact_file_count"],
        "actual_origin_provider_artifact_count": report["summary"]["actual_origin_provider_artifact_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
