"""Audit explicit HAZOP mode/scenario identity for every campaign event."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.frequency import FrequencyPlan  # noqa: E402
from lh2_tno.hazop_event_mode_binding import (  # noqa: E402
    audit_hazop_event_mode_binding,
    mode_bindings_from_diagnostic,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.provider_worklist import build_provider_release_worklist  # noqa: E402


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--provider-worklist", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--frequency-plan", type=Path)
    parser.add_argument("--mode-bindings", type=Path)
    parser.add_argument(
        "--diagnostic-hazop-result",
        type=Path,
        help="optional multi-equipment HAZOP result with explicit component_coverage bindings",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        campaign = _object(args.campaign_result)
        provider = _object(args.provider_worklist) if args.provider_worklist else None
        if provider is None and args.manifest and args.frequency_plan:
            manifest = EquipmentManifest.from_json(args.manifest)
            frequency_plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
            provider = build_provider_release_worklist(manifest, frequency_plan)
        mode_bindings = _object(args.mode_bindings) if args.mode_bindings else None
        if args.diagnostic_hazop_result:
            diagnostic = _object(args.diagnostic_hazop_result)
            diagnostic_bindings = mode_bindings_from_diagnostic(diagnostic)
            if mode_bindings is None:
                mode_bindings = diagnostic_bindings
            elif isinstance(mode_bindings.get("bindings"), list):
                mode_bindings = {"bindings": list(mode_bindings["bindings"]) + diagnostic_bindings}
            else:
                raise ValueError("--mode-bindings object must use a bindings array when combined with --diagnostic-hazop-result")
        report = audit_hazop_event_mode_binding(
            campaign,
            provider_worklist=provider,
            mode_bindings=mode_bindings,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"HAZOP event mode binding input error: {error}") from error
    report["source_records"] = {
        "campaign_result": str(args.campaign_result),
        "provider_worklist": str(args.provider_worklist) if args.provider_worklist else None,
        "manifest": str(args.manifest) if args.manifest else None,
        "frequency_plan": str(args.frequency_plan) if args.frequency_plan else None,
        "mode_bindings": str(args.mode_bindings) if args.mode_bindings else None,
        "diagnostic_hazop_result": str(args.diagnostic_hazop_result) if args.diagnostic_hazop_result else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "event_count": report["event_count"],
        "mode_bound_event_count": report["mode_bound_event_count"],
        "mode_required_event_count": report["mode_required_event_count"],
        "scenario_id_required_event_count": report["scenario_id_required_event_count"],
        "mode_conflict_event_count": report["mode_conflict_event_count"],
        "provider_event_count": report["provider_event_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 2 if report["status"] != "HAZOP_EVENT_MODE_BINDING_COMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())

