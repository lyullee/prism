"""Sample saved risk atoms under reviewed literature frequency distributions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.uncertainty import (  # noqa: E402
    LiteratureFrequencyDistributionScenario,
    sample_literature_frequency_distributions,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _scenarios(path: Path) -> tuple[LiteratureFrequencyDistributionScenario, ...]:
    value = _object(path)
    rows = value.get("scenarios")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain {{\"scenarios\": [...]}}")
    return tuple(LiteratureFrequencyDistributionScenario.model_validate(row) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draws", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261009)
    args = parser.parse_args()
    try:
        result = _object(args.ledger)
        scenarios = _scenarios(args.scenarios)
        report = sample_literature_frequency_distributions(
            result, scenarios, draws=args.draws, seed=args.seed
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"frequency distribution input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "scenario_count": len(report["scenarios"]),
        "draws": args.draws,
        "fresh_physics_executed": report["fresh_physics_executed"],
        "frequency_distribution_credible_interval": report["frequency_distribution_credible_interval"],
        "facility_credible_interval": report["facility_credible_interval"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
