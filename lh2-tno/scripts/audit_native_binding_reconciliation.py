"""Reconcile the native lh2dt source audit with the PRISM model catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.native_binding_reconciliation import (  # noqa: E402
    NativeBindingReconciliationError,
    reconcile_native_binding_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--contract-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = reconcile_native_binding_catalog(args.binding, args.contract_audit)
    except (NativeBindingReconciliationError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"native binding reconciliation input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "native_accident_export_component_count": report["native_accident_export_component_count"],
        "reconciled_native_component_count": report["reconciled_native_component_count"],
        "blocking_reason_count": len(report["blocking_reasons"]),
    }, ensure_ascii=False))
    return 0 if report["status"] == "RECONCILED_NATIVE_INTERFACES" else 2


if __name__ == "__main__":
    raise SystemExit(main())
