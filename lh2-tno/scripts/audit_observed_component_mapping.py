"""Audit candidate generic-component mappings for observed LH2 state streams."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.observed_component_mapping_audit import audit_observed_component_mapping  # noqa: E402


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observed-state-evidence", type=Path, required=True)
    parser.add_argument("--mapping-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_observed_component_mapping(
            _load(args.observed_state_evidence),
            _load(args.mapping_manifest),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"observed component mapping input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "observed_component_count": report["observed_component_count"],
        "candidate_mapping_count": report["candidate_mapping_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "CANDIDATE_COMPONENT_CLASS_MAPPINGS_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
