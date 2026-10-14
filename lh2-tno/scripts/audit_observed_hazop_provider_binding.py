from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.observed_hazop_provider_binding import (  # noqa: E402
    audit_observed_hazop_provider_binding,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    value["_record_path"] = str(path)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit observed HAZOP scenario to explicit provider-event identity bindings."
    )
    parser.add_argument("--observed-hazop-runtime-audit", type=Path, required=True)
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--binding-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_observed_hazop_provider_binding(
            _object(args.observed_hazop_runtime_audit),
            _object(args.provider_worklist),
            _object(args.binding_map),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"observed HAZOP provider binding input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "selected_scenario_count": report["selected_scenario_count"],
        "bound_scenario_count": report["bound_scenario_count"],
        "blocking_reason_count": len(report["blocking_reasons"]),
    }, ensure_ascii=False))
    return 0 if report["status"] == "OBSERVED_HAZOP_PROVIDER_EVENT_BINDINGS_DIAGNOSTIC" else 2


if __name__ == "__main__":
    raise SystemExit(main())
