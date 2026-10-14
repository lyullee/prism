"""Create a digest-bound DynamicLH2PoolX physical-evidence audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.dynamiclh2poolx_evidence_audit import (  # noqa: E402
    DynamicLH2PoolXEvidenceAuditError,
    audit_dynamiclh2poolx_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--stage-evidence", type=Path)
    parser.add_argument("--stage-protocol", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--dynamic-validation-protocol", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_dynamiclh2poolx_evidence(
            args.source_root,
            stage_evidence_path=args.stage_evidence,
            stage_protocol_path=args.stage_protocol,
            source_manifest_path=args.source_manifest,
            dynamic_validation_protocol_path=args.dynamic_validation_protocol,
        )
    except (OSError, UnicodeDecodeError, ValueError, TypeError, DynamicLH2PoolXEvidenceAuditError) as error:
        raise SystemExit(f"DynamicLH2PoolX evidence audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output.resolve()),
        "hash_mismatch_count": report["hash_mismatch_count"],
        "holdout_row_count": report["observations"]["holdout_row_count"],
        "restricted_component_evidence": report["claims"]["restricted_component_evidence"],
        "physical_validation_claim": report["claims"]["independent_physical_validation_claim"],
    }, ensure_ascii=False))
    return 0 if report["status"].startswith("RESTRICTED_COMPONENT_EVIDENCE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
