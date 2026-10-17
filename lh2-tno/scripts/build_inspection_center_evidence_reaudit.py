"""Re-audit inspection-centre scenario and time-series evidence together.

The command creates a compact, hash-bound summary from the existing read-only
auditors and the scenario importer.  It intentionally does not build
telemetry frames, provider release packets, frequencies, or facility-QRA
inputs.  The importer is used for the scope counts so the compact record
cannot silently lose the outdoor/out-of-scope split.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_ROOT))

from audit_inspection_center_timeseries import audit_root as audit_timeseries_root  # noqa: E402
from lh2_tno.scenario_evidence import audit_scenario_root, import_scenario_evidence  # noqa: E402


SCHEMA = "prism.inspection_center_evidence_reaudit.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _display_path(path: Path) -> str:
    """Keep tracked artifact references relative to the package root."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def build_reaudit(source_root: str | Path) -> dict[str, Any]:
    root = Path(source_root).resolve()
    scenario = audit_scenario_root(root)
    scenario_import = import_scenario_evidence(root)
    timeseries = audit_timeseries_root(root, {})
    scenario_status = scenario.get("status")
    scope_counts = scenario_import.get("summary", {}).get("scope_status_counts", {})
    timeseries_aggregate = timeseries.get("aggregate", {})
    return {
        "schema_version": SCHEMA,
        "status": "SCREENING_EVIDENCE_ONLY",
        "source_root": str(root),
        "scenario_evidence": {
            "source_file_count": scenario_import.get("source_file_count"),
            "record_count": scenario_import.get("summary", {}).get("record_count"),
            "outdoor_candidate_count": scope_counts.get("CANDIDATE_OUTDOOR_SCREENING", 0),
            "out_of_scope_count": scope_counts.get("OUTSIDE_DECLARED_OUTDOOR_SCOPE", 0),
            "audit_status": scenario_status,
            "import_status": scenario_import.get("status"),
            "qualified_packet_count": 0,
            "frequency_applied": False,
        },
        "timeseries_audit": {
            "workbook_count": timeseries_aggregate.get("workbook_count"),
            "sheet_count": timeseries_aggregate.get("sheet_count"),
            "read_error_count": timeseries_aggregate.get("workbook_or_sheet_error_count"),
            "numeric_signal_unit_status_count": timeseries_aggregate.get(
                "numeric_signal_unit_status_count", {}
            ),
            "state_snapshot_binding_allowed": False,
            "frequency_applied": False,
            "sensor_frequency_learning_used": False,
        },
        "promotion_policy": (
            "Actual centre files are retained as facility-neutral scenario and signal evidence. "
            "They do not create provider release packets, assign frequency, train sensor frequency, "
            "or open facility QRA until units, tag mapping, calibration, and accident release identity are reviewed."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario-audit-output", type=Path)
    parser.add_argument("--scenario-import-output", type=Path)
    parser.add_argument("--timeseries-audit-output", type=Path)
    args = parser.parse_args()

    root = args.source_root.resolve()
    scenario = audit_scenario_root(root)
    scenario_import = import_scenario_evidence(root)
    timeseries = audit_timeseries_root(root, {})
    if args.scenario_audit_output:
        _save(args.scenario_audit_output, scenario)
    if args.scenario_import_output:
        _save(args.scenario_import_output, scenario_import)
    if args.timeseries_audit_output:
        _save(args.timeseries_audit_output, timeseries)
    summary = build_reaudit(root)
    source_artifacts = []
    for path in (args.scenario_import_output, args.timeseries_audit_output):
        if path is not None and path.exists():
            source_artifacts.append(
                {
                    "path": _display_path(path),
                    "sha256": _sha256(path),
                }
            )
    summary["source_artifacts"] = source_artifacts
    _save(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
