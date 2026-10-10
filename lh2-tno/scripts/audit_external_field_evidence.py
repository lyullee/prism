"""Verify an outdoor LH2 observation bundle without promoting QRA claims."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.external_field_evidence import (  # noqa: E402
    ExternalFieldEvidenceError,
    build_external_field_evidence_record,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--skip-hash-verification",
        action="store_true",
        help="record paths and structure without verifying channel hashes",
    )
    args = parser.parse_args()
    try:
        report = build_external_field_evidence_record(
            args.manifest,
            verify_hashes=not args.skip_hash_verification,
        )
    except (ExternalFieldEvidenceError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"external field evidence input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "event_id": report["event_id"],
                "source_rows": report["source_boundary"]["row_count"],
                "weather_rows": report["weather"]["row_count"],
                "receptor_rows": report["receptor_observations"]["row_count"],
                "model_comparison_ready": report["model_comparison_ready"],
                "physical_validation_claim": report["physical_validation_claim"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
