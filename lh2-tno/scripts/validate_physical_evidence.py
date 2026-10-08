"""Verify and normalize the restricted DynamicLH2PoolX validation evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.validation_evidence import build_restricted_pool_record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path, help="Stage-C evidence JSON")
    parser.add_argument("--source-root", required=True, type=Path, help="review tree containing data/ and src/")
    parser.add_argument("--output", required=True, type=Path, help="normalized PRISM evidence record")
    parser.add_argument(
        "--allow-provenance-drift",
        action="store_true",
        help="record declared hash drift instead of treating it as verified evidence",
    )
    args = parser.parse_args()
    record = build_restricted_pool_record(
        args.evidence,
        args.source_root,
        allow_provenance_drift=args.allow_provenance_drift,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE",
        "component": record.component,
        "verified_files": len(record.verified_files),
        "provenance_status": record.provenance_status,
        "hash_mismatches": record.hash_mismatches,
        "metrics": record.metrics,
        "physical_validation_claim": record.physical_validation_claim,
        "full_chain_validation_claim": record.full_chain_validation_claim,
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
