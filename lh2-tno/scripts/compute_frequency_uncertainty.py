"""Reweight a saved campaign or facility ledger using reviewed frequency bounds."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.uncertainty import (  # noqa: E402
    LiteratureFrequencyScenario,
    literature_frequency_uncertainty,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _scenarios(path: Path) -> tuple[LiteratureFrequencyScenario, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    rows = value.get("scenarios") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a scenario array or {{\"scenarios\": [...]}}")
    return tuple(LiteratureFrequencyScenario.model_validate(row) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reweight saved PRISM risk atoms without rerunning physics."
    )
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = _object(args.ledger)
        scenarios = _scenarios(args.scenarios)
        report = literature_frequency_uncertainty(result, scenarios)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"frequency uncertainty input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "scenario_count": len(report["scenarios"]),
        "fresh_physics_executed": report["fresh_physics_executed"],
        "facility_credible_interval": report["facility_credible_interval"],
        "correlation_comparison_present": report["correlation_comparison_present"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
