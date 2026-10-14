"""Attach an explicit frequency-port map to an executed extension result."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.frequency_port_binding import (  # noqa: E402
    bind_frequency_ports_to_campaign_result,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--event-port-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    try:
        result, audit = bind_frequency_ports_to_campaign_result(
            _load(args.campaign_result), _load(args.event_port_map)
        )
        _save(args.output, result)
        _save(args.audit, audit)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"frequency port result binding failed: {error}") from error
    print(json.dumps({"status": audit["status"], "output": str(args.output.resolve()), "audit": str(args.audit.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
