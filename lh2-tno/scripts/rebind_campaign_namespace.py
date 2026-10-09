"""Namespace one disjoint diagnostic campaign for facility ledger merging."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.campaign_namespace import rebind_campaign_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--source-facility-id", required=True)
    parser.add_argument("--facility-id", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--source-asset-id", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--source-component-id", required=True)
    parser.add_argument("--component-id", required=True)
    parser.add_argument(
        "--receptor-map",
        action="append",
        default=[],
        metavar="SOURCE=TARGET",
        help="Explicit receptor mapping; endpoint maximum is used for collisions.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = json.loads(args.campaign_result.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("campaign result must be a JSON object")
        receptor_map: dict[str, str] = {}
        for raw in args.receptor_map:
            source, separator, target = raw.partition("=")
            if not separator or not source or not target:
                raise ValueError(f"receptor map must use SOURCE=TARGET: {raw}")
            receptor_map[source] = target
        rebound = rebind_campaign_result(
            result,
            source_facility_id=args.source_facility_id,
            facility_id=args.facility_id,
            namespace=args.namespace,
            source_asset_id=args.source_asset_id,
            asset_id=args.asset_id,
            source_component_id=args.source_component_id,
            component_id=args.component_id,
            receptor_map=receptor_map,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"campaign namespace rebind input error: {error}") from error
    provenance = rebound["campaign_namespace_rebind"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rebound, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.provenance_output.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "CAMPAIGN_NAMESPACE_REBOUND_FOR_FACILITY_MERGE",
        "output": str(args.output),
        "provenance_output": str(args.provenance_output),
        "event_count": provenance["event_count"],
        "diagnostic_only": True,
        "facility_qra_claim": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
