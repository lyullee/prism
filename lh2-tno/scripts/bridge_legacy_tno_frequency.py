#!/usr/bin/env python3
"""Bridge an exported legacy TNO scenario list into PRISM events.

The input is deliberately an export rather than an import of the external
TNO source tree.  This keeps the two distributions independent while making
the handoff reproducible and hash-pinned.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.contracts import Facility
from lh2_tno.legacy_frequency_bridge import bridge_digest, bridge_legacy_scenarios


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, required=True,
                        help="JSON array, or object containing a scenarios array, exported by legacy TNO")
    parser.add_argument("--component-map", type=Path, required=True,
                        help="JSON object mapping exact legacy scenario_id to PRISM component_id")
    parser.add_argument("--source-sha256", required=True,
                        help="SHA-256 of the pinned legacy taxonomy/generator source")
    parser.add_argument("--source", default="external legacy TNO taxonomy.enumerate_scenarios")
    parser.add_argument("--facility", type=Path,
                        help="optional PRISM Facility JSON; mapped component IDs are checked")
    parser.add_argument("--basis", choices=("TNO_PURPLE_LOC", "LH2_LITERATURE"),
                        default="TNO_PURPLE_LOC")
    parser.add_argument("--plan-id", default="legacy-tno")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    source_data = _load_json(args.scenarios)
    scenarios = source_data.get("scenarios") if isinstance(source_data, dict) else source_data
    if not isinstance(scenarios, list):
        parser.error("--scenarios must contain a JSON array or {scenarios: []}")
    component_map = _load_json(args.component_map)
    if not isinstance(component_map, dict):
        parser.error("--component-map must contain a JSON object")
    facility = None
    if args.facility:
        facility = Facility.model_validate_json(args.facility.read_text(encoding="utf-8"))
    events, audit = bridge_legacy_scenarios(
        scenarios,
        component_map,
        plan_id=args.plan_id,
        source=args.source,
        source_sha256=args.source_sha256,
        facility=facility,
        basis=args.basis,
    )
    result = {
        "schema_version": "prism.legacy_tno_frequency_bridge_result.v1",
        "bridge_audit": audit,
        "bridge_audit_digest": bridge_digest(audit),
        "events": [event.model_dump(mode="json") for event in events],
        "frequency_inference_performed": False,
        "facility_qra_promotion": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "BRIDGED_DIAGNOSTIC_ONLY",
        "output": str(args.output.resolve()),
        "legacy_scenario_count": audit["legacy_scenario_count"],
        "bridged_event_count": audit["bridged_event_count"],
        "frequency_inference_performed": False,
        "facility_qra_promotion": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
