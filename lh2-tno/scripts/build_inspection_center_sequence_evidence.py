"""Extract conservative operating-sequence evidence from an LH2 CSV.

The inspection-centre sequence file is useful for documenting what an
operator is expected to do when storage pressure rises.  It is not an
accident experiment and it does not contain a qualified PSV capacity,
mass-flow history, inventory ledger, or failure-frequency population.  This
adapter therefore produces a HAZOP/input provenance sidecar only.  It never
creates a provider release packet or promotes facility QRA evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "prism.inspection_center_operation_sequence_evidence.v1"
REQUIRED_COLUMNS = {
    "시나리오",
    "탱크",
    "절차번호",
    "동작내용",
    "위험성분류",
    "누출_예상고장",
    "누출_근거기준",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _float_bar_to_pa(value: float) -> float:
    return value * 100_000.0


def _pressure_bar_values(text: str) -> list[float]:
    # Keep this deliberately narrow: only explicit ``number bar`` tokens are
    # converted.  No pressure is inferred from a tag, alarm, or prose alone.
    return [float(match) for match in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*bar", text, flags=re.IGNORECASE)]


def _row_evidence(row: dict[str, str]) -> dict[str, Any]:
    action = row.get("동작내용", "")
    note = row.get("비고", "")
    combined = f"{action} {note}"
    pressures_bar = _pressure_bar_values(combined)
    return {
        "procedure_number": row.get("절차번호", ""),
        "action": action,
        "tank_or_scope": row.get("탱크", ""),
        "hazard_classification": row.get("위험성분류", ""),
        "expected_leak_failure": row.get("누출_예상고장", ""),
        "leak_basis_reference": row.get("누출_근거기준", ""),
        "explicit_pressure_bar": pressures_bar,
        "explicit_pressure_pa": [_float_bar_to_pa(value) for value in pressures_bar],
        "source_row_digest": hashlib.sha256(
            json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


def build_record(*, source_path: Path, scenario: str | None = None) -> dict[str, Any]:
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"sequence CSV is missing required columns: {missing}")
        rows = [dict(row) for row in reader]

    selected = [row for row in rows if scenario is None or row.get("시나리오") == scenario]
    evidence_rows = [_row_evidence(row) for row in selected]
    all_pressures_pa = [
        pressure
        for row in evidence_rows
        for pressure in row["explicit_pressure_pa"]
    ]
    # The CSV documents an operating sequence.  It does not prove that a
    # relief discharged to completion.  Keep these fields explicit so a
    # downstream release-boundary gate cannot accidentally treat them as true.
    relief_rows = [
        row for row in evidence_rows if row["hazard_classification"] == "relief_vent"
    ]
    close_rows = [
        row for row in evidence_rows if row["hazard_classification"] == "valve_close"
    ]
    return {
        "schema_version": SCHEMA,
        "status": "OPERATION_SEQUENCE_SCREENED_DIAGNOSTIC_ONLY",
        "source": {
            "path": source_path.as_posix(),
            "sha256": sha256_file(source_path),
            "encoding": "utf-8-sig",
            "scenario_filter": scenario,
            "row_count_total": len(rows),
            "row_count_selected": len(selected),
        },
        "operating_sequence": {
            "rows": evidence_rows,
            "explicit_pressure_pa": sorted(set(all_pressures_pa)),
            "relief_operation_row_count": len(relief_rows),
            "close_operation_row_count": len(close_rows),
            "observed_relief_setpoint_candidate_pa": max(all_pressures_pa)
            if relief_rows and all_pressures_pa
            else None,
            "observed_operational_close_threshold_candidate_pa": min(all_pressures_pa)
            if close_rows and all_pressures_pa
            else None,
        },
        "evidence_suitability": {
            "operating_sequence_for_hazop": {
                "available": bool(evidence_rows),
                "promotion": "diagnostic_only",
            },
            "relief_setpoint": {
                "available_as_observed_candidate": bool(relief_rows and all_pressures_pa),
                "promotion": "requires_owner_review",
                "reason": "CSV pressure labels are operational evidence, not a certified relief-device setpoint.",
            },
            "release_boundary": {
                "available": False,
                "missing_fields": [
                    "provider relief capacity or mass-flow history",
                    "physical discharge-complete event",
                    "initial/final inventory and mass residual",
                ],
            },
            "failure_frequency": {
                "available": False,
                "sensor_frequency_learning_used": False,
            },
        },
        "promotion_gates": {
            "hazop_sequence_reference_allowed": bool(evidence_rows),
            "provider_packet_created": False,
            "provider_packet_qualified": False,
            "release_boundary_closed": False,
            "frequency_applied": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
        },
        "interpretation": (
            "The source records an operator sequence and explicit pressure labels. "
            "It may support HAZOP provenance, but it does not close a provider "
            "release boundary or supply a failure frequency."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--scenario")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = build_record(source_path=args.source, scenario=args.scenario)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "schema": SCHEMA, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
