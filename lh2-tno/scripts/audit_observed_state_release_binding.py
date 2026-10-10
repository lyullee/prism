"""Audit an explicit observed-state to provider-release binding manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.observed_state_release_binding_audit import (  # noqa: E402
    audit_observed_state_release_binding,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observed-state-evidence", type=Path, required=True)
    parser.add_argument("--provider-packet-input-audit", type=Path, required=True)
    parser.add_argument("--binding-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_observed_state_release_binding(
            _load(args.observed_state_evidence),
            _load(args.provider_packet_input_audit),
            _load(args.binding_manifest),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"observed state release binding input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "observed_component_count": report["observed_component_count"],
        "mapped_component_count": report["mapped_component_count"],
        "provider_packet_evidence_count": report["provider_packet_evidence_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "STATE_AND_PROVIDER_RELEASE_BOUND_DIAGNOSTIC" else 2


if __name__ == "__main__":
    raise SystemExit(main())
