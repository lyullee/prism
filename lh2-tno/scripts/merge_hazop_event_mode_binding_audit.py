"""Merge explicit base/extension HAZOP bindings and run the canonical audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.hazop_event_mode_binding_merge import (  # noqa: E402
    merge_hazop_event_mode_bindings,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--base-binding", type=Path, required=True)
    parser.add_argument("--extension-binding", type=Path)
    parser.add_argument("--provider-worklist", type=Path)
    parser.add_argument(
        "--overlap-policy",
        choices=("error", "base_wins"),
        default="error",
        help="how to handle extension rows already present in the base record",
    )
    parser.add_argument(
        "--replace-event-id",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="literal event-id replacement applied in order; repeatable",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replacements: list[tuple[str, str]] = []
    for value in args.replace_event_id:
        if "=" not in value:
            raise SystemExit("--replace-event-id must use OLD=NEW")
        old, new = value.split("=", 1)
        replacements.append((old, new))
    try:
        report = merge_hazop_event_mode_bindings(
            _object(args.campaign_result),
            _object(args.base_binding),
            _object(args.extension_binding) if args.extension_binding else None,
            provider_worklist=(
                _object(args.provider_worklist) if args.provider_worklist else None
            ),
            event_id_replacements=replacements,
            overlap_policy=args.overlap_policy,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"HAZOP binding merge input error: {error}") from error
    report["source_records"] = {
        "campaign_result": str(args.campaign_result),
        "base_binding": str(args.base_binding),
        "extension_binding": str(args.extension_binding) if args.extension_binding else None,
        "provider_worklist": str(args.provider_worklist) if args.provider_worklist else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "event_count": report["event_count"],
        "mode_bound_event_count": report["mode_bound_event_count"],
        "merge": report["merge"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "HAZOP_EVENT_MODE_BINDING_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
