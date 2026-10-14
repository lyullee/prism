"""Build explicit HAZOP mode bindings for namespaced LH2 extension events."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.hazop_extension_mode_binding import bind_hazop_extension_modes  # noqa: E402


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-audit", type=Path, required=True)
    parser.add_argument("--mode-binding", type=Path, required=True)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--extension-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = bind_hazop_extension_modes(
        _load(args.runtime_audit),
        _load(args.mode_binding),
        _load(args.campaign_result),
        _load(args.extension_config),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, key in (
        ("hazop_runtime_audit_extension_bound.json", "runtime_audit"),
        ("hazop_mode_binding_extension_bound.json", "mode_binding"),
        ("hazop_selection_event_binding_extension_bound.json", "selection_event_audit"),
    ):
        (args.output_dir / name).write_text(
            json.dumps(result[key], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    summary = {
        "schema_version": "prism.hazop_extension_mode_binding_diagnostic.v1",
        "status": result["selection_event_audit"]["status"],
        "extension_component_count": result["extension_component_count"],
        "extension_event_count": result["extension_event_count"],
        "bound_event_count": result["selection_event_audit"]["bound_event_count"],
        "unbound_event_count": result["selection_event_audit"]["unbound_event_count"],
        "frequency_assignment_performed": False,
        "provider_release_created": False,
        "facility_qra_claim": False,
    }
    (args.output_dir / "verification.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "HAZOP_SELECTION_EVENT_BINDING_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
