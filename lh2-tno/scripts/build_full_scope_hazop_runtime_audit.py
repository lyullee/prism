"""Build the full-scope qualitative HAZOP/event identity audit.

This command expands the seven-row multi-equipment diagnostic table only for
explicit campaign families that were absent from the representative runtime
table.  It does not execute a provider release or a consequence model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.hazop_scope_runtime import build_full_scope_hazop_runtime_audit  # noqa: E402


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-table-set",
        type=Path,
        default=ROOT / "results/20261113/hazop_multiequipment_hazop_table_set_v4.json",
    )
    parser.add_argument(
        "--runtime-frames",
        type=Path,
        default=ROOT / "results/20261113/hazop_multiequipment_provider_isolation_diagnostic_v5.json",
        help="diagnostic record containing a frames object",
    )
    parser.add_argument(
        "--campaign-result",
        type=Path,
        required=True,
        help="campaign_result.json containing the 24 explicit event/case rows",
    )
    parser.add_argument(
        "--mode-bindings",
        type=Path,
        default=ROOT / "examples/native_lh2_full_scope_hazop_mode_binding.json",
    )
    parser.add_argument("--now-s", type=float, default=12.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base_table_set = _load(args.base_table_set)
    diagnostic = _load(args.runtime_frames)
    frames = diagnostic.get("frames") if isinstance(diagnostic, dict) else None
    if not isinstance(frames, dict):
        raise SystemExit("runtime diagnostic must contain a frames object")
    report = build_full_scope_hazop_runtime_audit(
        base_table_set,
        frames,
        _load(args.campaign_result),
        _load(args.mode_bindings),
        now_s=float(args.now_s),
    )
    _save(args.output, report)
    _save(
        args.output.with_name(args.output.stem + "_table_set.json"),
        report["table_set"],
    )
    _save(
        args.output.with_name(args.output.stem + "_observed_runtime.json"),
        report["observed_hazop_runtime_audit"],
    )
    _save(
        args.output.with_name(args.output.stem + "_event_binding.json"),
        report["hazop_selection_event_binding"],
    )
    print(json.dumps({
        "status": report["status"],
        "selected_scenario_count": report["selected_scenario_count"],
        "frequency_event_count": report["frequency_event_count"],
        "bound_event_count": report["bound_event_count"],
        "unbound_event_count": report["unbound_event_count"],
        "added_hazop_row_count": report["table_set"]["scope_audit"]["added_row_count"],
        "blocking_reasons": report["blocking_reasons"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
