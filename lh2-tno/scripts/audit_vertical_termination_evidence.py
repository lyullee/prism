"""Audit provider termination evidence for the vertical-handoff campaign."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.vertical_termination_evidence import (  # noqa: E402
    build_vertical_termination_evidence_search,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify vertical-handoff termination evidence without promoting synthetic horizons."
    )
    parser.add_argument("--vertical-catalog-dir", type=Path, required=True)
    parser.add_argument("--vertical-chain-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chain = _object(args.vertical_chain_audit) if args.vertical_chain_audit else None
    result = build_vertical_termination_evidence_search(
        args.vertical_catalog_dir,
        vertical_chain_audit=chain,
    )
    if args.vertical_chain_audit:
        result["vertical_chain_audit"] = str(args.vertical_chain_audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "source_catalog_event_count": result["source_catalog_event_count"],
        "not_supplied_event_count": result["not_supplied_event_count"],
        "not_supplied_case_count": result["not_supplied_case_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
