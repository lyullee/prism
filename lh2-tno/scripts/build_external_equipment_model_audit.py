#!/usr/bin/env python3
"""Audit external LH2 equipment-model readiness without release promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.external_equipment_model_audit import (  # noqa: E402
    ExternalEquipmentModelAuditError,
    audit_external_equipment_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--private-inputs-audit", type=Path, required=True)
    parser.add_argument("--connection-event-register", type=Path, required=True)
    parser.add_argument("--observation-judgements", type=Path, required=True)
    parser.add_argument("--pid-evidence", type=Path)
    parser.add_argument("--port-mappings", type=Path)
    parser.add_argument("--component-bindings", type=Path)
    parser.add_argument("--flow-crosswalk", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_external_equipment_model(
            args.assets,
            args.private_inputs_audit,
            args.connection_event_register,
            args.observation_judgements,
            pid_evidence_path=args.pid_evidence,
            port_mappings_path=args.port_mappings,
            component_bindings_path=args.component_bindings,
            flow_crosswalk_path=args.flow_crosswalk,
        )
    except (ExternalEquipmentModelAuditError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"external equipment model audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "asset_count": report["asset_count"],
        "state_model_ready_asset_count": report["state_model_ready_asset_count"],
        "accident_release_packet_allowed": report["promotion_gates"]["accident_release_packet_allowed"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
