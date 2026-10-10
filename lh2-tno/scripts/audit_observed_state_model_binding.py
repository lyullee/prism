"""Audit observed LH2 signals against the facility-neutral model catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.observed_state_model_binding_audit import audit_observed_state_model_binding  # noqa: E402


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observed-state-evidence", type=Path, required=True)
    parser.add_argument("--component-mapping-manifest", type=Path, required=True)
    parser.add_argument("--model-binding-catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_observed_state_model_binding(
            _load(args.observed_state_evidence),
            _load(args.component_mapping_manifest),
            _load(args.model_binding_catalog),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"observed state model binding input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "observed_component_count": report["observed_component_count"],
        "state_model_bound_component_count": report["state_model_bound_component_count"],
        "diagnostic_release_adapter_component_count": report["diagnostic_release_adapter_component_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "STATE_MODEL_BINDINGS_DIAGNOSTIC_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
