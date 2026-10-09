"""Index saved native lh2dt accident packets without promoting risk claims."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.native_packet_coverage import build_native_packet_coverage_ledger  # noqa: E402


DEFAULT_GLOBS = (
    "results/20261015/storage_tank_worklist_packets/AREA_*pct",
    "results/20261012/dynamic_pipe_worklist_AREA_*pct",
    "results/20261013/valve_worklist_AREA_*pct",
    "results/20261012/mapped_pump_worklist_g*",
    "results/20261012/vent_stack_worklist_g1",
    "results/20261014/vaporizer_worklist_g*",
    "results/20261014/reliquefier_worklist_G*",
    "results/20261018/native_layered_tank_smoke_chain",
    "results/20261018/native_dynamic_pipe_full_bore_facility_frequency",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=ROOT)
    parser.add_argument("--provider-worklist", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packet-glob", action="append", dest="packet_globs")
    args = parser.parse_args()
    root = args.results_root.resolve()
    patterns = tuple(args.packet_globs or DEFAULT_GLOBS)
    packet_dirs: list[Path] = []
    for pattern in patterns:
        packet_dirs.extend(sorted(root.glob(pattern)))
    worklist = None
    if args.provider_worklist:
        value = json.loads(args.provider_worklist.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SystemExit("provider worklist must contain a JSON object")
        worklist = value
    ledger = build_native_packet_coverage_ledger(root, packet_dirs, worklist)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": ledger["status"],
        "packet_count": ledger["packet_count"],
        "consequence_chain_event_count": ledger["consequence_chain_event_count"],
        "frequency_bound_event_count": ledger["frequency_bound_event_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
