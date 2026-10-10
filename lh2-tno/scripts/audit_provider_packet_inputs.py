"""Audit a batch manifest of provider release packets and qualification sidecars."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_packet_input_audit import audit_provider_packet_inputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_provider_packet_inputs(args.manifest)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"provider packet manifest input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "input_record_count": report["input_record_count"],
        "accepted_provider_packet_count": report["accepted_provider_packet_count"],
        "rejected_record_count": report["rejected_record_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "QUALIFIED_PROVIDER_PACKET_CATALOG" else 2


if __name__ == "__main__":
    raise SystemExit(main())
