"""Audit generic LH2 component-model binding coverage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_model_binding import (  # noqa: E402
    EquipmentModelBindingError,
    audit_equipment_model_binding,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_equipment_model_binding(args.manifest, args.binding)
    except (EquipmentModelBindingError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"equipment model binding input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "component_count": report["component_count"],
        "blocking_reason_count": len(report["blocking_reasons"]),
        "accident_release_claim": report["accident_release_claim"],
    }, ensure_ascii=False))
    return 0 if report["status"] in {
        "STATE_ONLY_BOUND", "ACCIDENT_RELEASE_INTERFACE_BOUND"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
