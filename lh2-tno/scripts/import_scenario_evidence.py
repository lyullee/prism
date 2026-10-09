"""Import external LH2 procedure/failure tables as non-promoting evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.scenario_evidence import import_scenario_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import CSV scenario evidence without assigning frequency or facility risk."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = import_scenario_evidence(args.root)
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"scenario evidence input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "source_file_count": report["source_file_count"],
        "record_count": report["summary"]["record_count"],
        "outdoor_candidate_count": report["summary"]["scope_status_counts"].get("CANDIDATE_OUTDOOR_SCREENING", 0),
        "out_of_scope_count": report["summary"]["scope_status_counts"].get("OUTSIDE_DECLARED_OUTDOOR_SCOPE", 0),
        "frequency_applied": report["policy"]["frequency_applied"],
        "facility_qra_claim": report["policy"]["facility_qra_claim"],
    }, ensure_ascii=False))
    return 0 if report["status"] != "FAILED_SCREENING_EVIDENCE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
