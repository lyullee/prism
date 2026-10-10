"""Build the fail-closed PRISM validation evidence matrix."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.validation_evidence_matrix import (  # noqa: E402
    ValidationEvidenceMatrixError,
    build_validation_evidence_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool-record", type=Path, required=True)
    parser.add_argument("--equipment-audit", type=Path, required=True)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument("--native-contract", type=Path)
    parser.add_argument("--slabx-validation", type=Path)
    parser.add_argument("--ijhe-audit", type=Path)
    parser.add_argument("--external-sweep", type=Path)
    parser.add_argument("--external-field-evidence", type=Path)
    parser.add_argument("--external-field-comparison", type=Path)
    parser.add_argument("--preslhy-slabx-window-comparison", type=Path)
    parser.add_argument("--slabx-source-validation-gates", type=Path)
    parser.add_argument("--slabx-direct-comparison", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        matrix = build_validation_evidence_matrix(
            args.pool_record,
            args.equipment_audit,
            args.facility_assessment,
            native_contract_path=args.native_contract,
            slabx_validation_path=args.slabx_validation,
            ijhe_audit_path=args.ijhe_audit,
            external_sweep_path=args.external_sweep,
            external_field_path=args.external_field_evidence,
            external_field_comparison_path=args.external_field_comparison,
            preslhy_slabx_window_path=args.preslhy_slabx_window_comparison,
            slabx_source_validation_gate_path=args.slabx_source_validation_gates,
            slabx_direct_comparison_path=args.slabx_direct_comparison,
        )
    except (ValidationEvidenceMatrixError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"validation evidence matrix input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": matrix["status"],
        "decision": matrix["decision"],
        "domain_count": len(matrix["evidence_domains"]),
        "blocking_reason_count": len(matrix["blocking_reasons"]),
        "physical_validation_claim": matrix["physical_validation_claim"],
        "facility_qra_claim": matrix["facility_qra_claim"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0 if matrix["status"] == "RESTRICTED_EVIDENCE_MATRIX" else 2


if __name__ == "__main__":
    raise SystemExit(main())
