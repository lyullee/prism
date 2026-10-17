"""Audit human-reviewed NASA pump test points without promoting QRA evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.external_pump_test_point_audit import (  # noqa: E402
    ExternalPumpTestPointAuditError,
    audit_external_pump_test_points,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ExternalPumpTestPointAuditError("manifest must be an object")
        report = audit_external_pump_test_points(manifest, source_root=args.source_root)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ExternalPumpTestPointAuditError) as error:
        raise SystemExit(f"external pump test-point audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "test_point_count": report["test_point_count"],
        "blocking_reason_count": len(report["blocking_reasons"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
