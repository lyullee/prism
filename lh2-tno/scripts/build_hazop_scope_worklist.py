"""Build the explicit HAZOP-to-provider scope worklist.

This command joins the representative multi-equipment HAZOP diagnostic with
the complete frequency-event/provider boundary.  It records which
family/component pairs were dispatched, which were applicable but absent,
and which have no exact frequency-event binding.  It never creates a release
packet or infers a missing frequency.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan  # noqa: E402
from lh2_tno.hazop_scope_worklist import build_hazop_scope_worklist  # noqa: E402
from lh2_tno.provider_worklist import build_provider_release_worklist  # noqa: E402


def _json_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--diagnostic-result", type=Path, required=True)
    parser.add_argument(
        "--provider-worklist",
        type=Path,
        help="existing prism.provider_release_worklist.v1 JSON; mutually exclusive with --frequency-plan",
    )
    parser.add_argument(
        "--frequency-plan",
        type=Path,
        help="frequency plan used to build a fresh provider worklist",
    )
    parser.add_argument("--model-binding", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return exit code 2 when any scope or provider gap remains",
    )
    args = parser.parse_args()
    try:
        if bool(args.provider_worklist) == bool(args.frequency_plan):
            raise ValueError("provide exactly one of --provider-worklist or --frequency-plan")
        manifest = EquipmentManifest.from_json(args.manifest)
        diagnostic = _json_object(args.diagnostic_result)
        scope_catalog = diagnostic.get("scope_catalog")
        if not isinstance(scope_catalog, dict):
            raise ValueError("diagnostic result does not contain a scope_catalog object")
        if args.provider_worklist:
            provider_worklist = _json_object(args.provider_worklist)
        else:
            frequency_plan = FrequencyPlan.model_validate_json(
                args.frequency_plan.read_text(encoding="utf-8")
            )
            provider_worklist = build_provider_release_worklist(
                manifest,
                frequency_plan,
                model_binding=args.model_binding,
            )
        report = build_hazop_scope_worklist(
            manifest,
            scope_catalog,
            provider_worklist,
            runtime=diagnostic,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"HAZOP scope worklist input error: {error}") from error

    report["source_records"] = {
        "manifest": str(args.manifest),
        "diagnostic_result": str(args.diagnostic_result),
        "provider_worklist": str(args.provider_worklist) if args.provider_worklist else None,
        "frequency_plan": str(args.frequency_plan) if args.frequency_plan else None,
        "model_binding": str(args.model_binding) if args.model_binding else None,
    }
    report["diagnostic_status"] = diagnostic.get("status")
    report["diagnostic_facility_handoff_status"] = diagnostic.get("facility_handoff_status")
    report["diagnostic_facility_qra_promotion"] = (
        (diagnostic.get("policy") or {}).get("facility_qra_promotion")
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    summary = report["summary"]
    print(json.dumps({
        "status": report["status"],
        "family_component_row_count": summary["family_component_row_count"],
        "dispatched_diagnostic_component_count": summary["dispatched_diagnostic_component_count"],
        "applicable_not_dispatched_component_count": summary["applicable_not_dispatched_component_count"],
        "no_frequency_binding_component_count": summary["no_frequency_binding_component_count"],
        "provider_event_count": summary["provider_event_count"],
        "provider_uncomputed_event_count": summary["provider_uncomputed_event_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 2 if args.strict and report["status"] != "PROVIDER_SCOPE_COMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())

