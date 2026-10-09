"""Repair facility-ledger family metadata and rebuild its exact scope matrix."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.accident_scope import MAJOR_ACCIDENT_FAMILIES  # noqa: E402
from lh2_tno.facility_scope_matrix import (  # noqa: E402
    build_scope_matrix_from_facility_ledger,
    repair_facility_ledger_scenario_families,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility-ledger", type=Path, required=True)
    parser.add_argument(
        "--family-override",
        action="append",
        default=[],
        metavar="EVENT_ID=FAMILY[,FAMILY...]",
        help=(
            "exact event-ID override for provider-specific families; repeat the option. "
            "No prefix or substring matching is accepted."
        ),
    )
    parser.add_argument("--repaired-ledger-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--required-family",
        action="append",
        dest="required_families",
        choices=MAJOR_ACCIDENT_FAMILIES,
        help="limit the regenerated matrix; repeat the option",
    )
    args = parser.parse_args()
    try:
        ledger = _object(args.facility_ledger)
        overrides: dict[str, list[str]] = {}
        for raw in args.family_override:
            event_id, separator, values = raw.partition("=")
            if not separator or not event_id.strip() or not values.strip():
                raise ValueError(
                    "--family-override must use EVENT_ID=FAMILY[,FAMILY...]"
                )
            families = [value.strip() for value in values.split(",") if value.strip()]
            if not families:
                raise ValueError("family override must contain at least one family")
            if event_id in overrides:
                raise ValueError(f"duplicate exact family override: {event_id}")
            overrides[event_id] = families
        repaired = repair_facility_ledger_scenario_families(
            ledger,
            event_family_overrides=overrides,
        )
        families = tuple(args.required_families or MAJOR_ACCIDENT_FAMILIES)
        matrix = build_scope_matrix_from_facility_ledger(
            repaired,
            required_families=families,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"ledger scope matrix input error: {error}") from error

    if args.repaired_ledger_output:
        args.repaired_ledger_output.parent.mkdir(parents=True, exist_ok=True)
        args.repaired_ledger_output.write_text(
            json.dumps(repaired, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "COMPLETE" if matrix["matrix_complete"] else "INCOMPLETE_DECLARED_SCOPE",
        "output": str(args.output),
        "repaired_ledger_output": str(args.repaired_ledger_output) if args.repaired_ledger_output else None,
        "event_count": matrix["event_count"],
        "case_count": matrix["case_count"],
        "conditional_uncomputed_case_count": matrix["conditional_uncomputed_case_count"],
        "blocking_reason_count": len(matrix["blocking_reasons"]),
    }, ensure_ascii=False))
    return 0 if matrix["matrix_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
