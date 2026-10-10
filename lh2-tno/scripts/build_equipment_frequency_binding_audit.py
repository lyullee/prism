#!/usr/bin/env python3
"""Build a fail-closed literature-frequency binding audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_frequency_binding_audit import (  # noqa: E402
    EquipmentFrequencyBindingAuditError,
    audit_equipment_frequency_binding,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    value["_record_path"] = str(path)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--equipment-scenario-coverage", type=Path, required=True)
    parser.add_argument("--frequency-provenance", type=Path)
    parser.add_argument("--frequency-events", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.frequency_provenance and args.frequency_events:
        raise SystemExit("choose --frequency-provenance or --frequency-events, not both")
    try:
        raw_events = None
        if args.frequency_events:
            payload = json.loads(args.frequency_events.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                raw_events = payload.get("events") or payload.get("generated_events")
            else:
                raw_events = payload
            if not isinstance(raw_events, list):
                raise ValueError("frequency event file must contain an array or an events/generated_events array")
        report = audit_equipment_frequency_binding(
            _object(args.equipment_scenario_coverage),
            frequency_provenance=_object(args.frequency_provenance) if args.frequency_provenance else None,
            frequency_events=raw_events,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError,
            EquipmentFrequencyBindingAuditError) as error:
        raise SystemExit(f"equipment frequency binding audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "resolved_asset_count": report["resolved_asset_count"],
        "frequency_event_count": report["frequency_event_count"],
        "valid_frequency_event_count": report["valid_frequency_event_count"],
        "uncomputed_family_count": report["uncomputed_family_count"],
        "facility_qra_allowed": report["promotion_gates"]["facility_qra_allowed"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
