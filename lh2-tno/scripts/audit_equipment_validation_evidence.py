"""Audit external LH2 equipment observation and validation-gate evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_validation_audit import (  # noqa: E402
    EquipmentValidationAuditError,
    audit_equipment_validation_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--independent-validation", type=Path, required=True)
    parser.add_argument("--topology-chain", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_equipment_validation_evidence(
            args.dataset_manifest,
            args.independent_validation,
            topology_chain_path=args.topology_chain,
        )
    except (EquipmentValidationAuditError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"equipment validation evidence input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "blocking_reason_count": len(report["blocking_reasons"]),
        "physical_validation_claim": report["physical_validation_claim"],
        "full_chain_validation_claim": report["full_chain_validation_claim"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "RESTRICTED_EQUIPMENT_OBSERVATION_EVIDENCE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
