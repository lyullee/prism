"""Audit native external LH2 accident-export methods without promotion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.external_model_contract_audit import (  # noqa: E402
    ExternalModelContractAuditError,
    audit_external_model_contract,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument(
        "--prism-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="PRISM checkout containing diagnostic adapter scripts",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_external_model_contract(args.binding, args.external_root, args.prism_root)
    except (ExternalModelContractAuditError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"external model contract audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "binding_count": report["binding_count"],
        "native_accident_export_component_count": report["native_accident_export_component_count"],
        "diagnostic_adapter_contract_verified_count": report["diagnostic_adapter_contract_verified_count"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "NATIVE_ACCIDENT_EXPORT_METHODS_FOUND" else 2


if __name__ == "__main__":
    raise SystemExit(main())
