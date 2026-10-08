"""Build a fail-closed provider packet work queue from a scenario audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.scenario_evidence import build_provider_packet_request_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, type=Path, help="scenario evidence audit JSON")
    parser.add_argument("--output", required=True, type=Path, help="provider packet request catalog JSON")
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    catalog = build_provider_packet_request_catalog(audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": catalog["status"],
        "request_count": catalog["request_count"],
        "candidate_family_request_counts": catalog["candidate_family_request_counts"],
        "frequency_assigned": catalog["provider_promotion"]["frequency_assigned"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
