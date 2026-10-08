"""Read-only audit for scenario registers and time-series exports.

The inspection-centre workbooks and CSV registers are useful evidence for
equipment states, operating steps, and accident-family candidates.  They are
not resolved provider release packets.  This module inventories them without
turning a pressure/temperature trace, a scenario description, or a vent
command into a release rate or accident frequency.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


SCENARIO_EVIDENCE_SCHEMA = "prism.scenario_evidence_audit.v1"
PROVIDER_RELEASE_REQUIRED_FIELDS = (
    "provider_export_schema",
    "event_kind",
    "event_id",
    "component_id",
    "port_id",
    "position_enu_m",
    "direction_enu",
    "steps",
    "duration_s",
    "available_mass_kg",
    "cumulative_mass_out_kg",
    "termination_provenance",
    "property_basis",
    "provider_source_digest",
    "provider_result_digest",
)

_FIELD_ALIASES = {
    "scenario": ("시나리오", "scenario", "scenario_id"),
    "asset": ("탱크", "tank", "asset_id", "component_id", "equipment"),
    "step": ("절차번호", "step", "sequence", "step_id"),
    "operation": ("동작내용", "action", "operation", "command"),
    "hazard_class": ("위험성분류", "hazard_class", "hazard_type"),
    "leak_failure": ("누출_예상고장", "leak_failure", "release_failure"),
    "leak_hazard": ("누출_위험", "leak_hazard", "release_hazard"),
    "fire_hazard": ("화재_위험", "fire_hazard"),
    "explosion_hazard": ("폭발_위험", "explosion_hazard"),
}

_FAMILY_BY_HAZARD_CLASS = {
    "flange_connect": ("pipe_hole", "vessel_hole"),
    "purge_vent": ("vent_hole",),
    "relief_vent": ("vent_hole",),
    "valve_close": ("valve_hole",),
    "main_line_open": ("pipe_hole",),
    "supply_start": ("pipe_hole", "valve_hole"),
    "vaporizer_pass": ("vaporizer_hole",),
    "pressure_rise_monitor": ("vent_hole", "inventory_over_600s"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _decode_csv(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949", "euc-kr", "utf-16"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw, 0, min(1, len(raw)), "unsupported scenario CSV encoding")


def _value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _scenario_record(path: Path, root: Path, row_number: int, row: dict[str, Any]) -> dict[str, Any]:
    hazard_class = _value(row, _FIELD_ALIASES["hazard_class"])
    family = _FAMILY_BY_HAZARD_CLASS.get(str(hazard_class), ())
    return {
        "file": str(path.relative_to(root)),
        "row_number": row_number,
        "scenario": _value(row, _FIELD_ALIASES["scenario"]),
        "asset": _value(row, _FIELD_ALIASES["asset"]),
        "step": _value(row, _FIELD_ALIASES["step"]),
        "operation": _value(row, _FIELD_ALIASES["operation"]),
        "hazard_class": hazard_class,
        "candidate_accident_families": list(family),
        "hazard_text": {
            "leak_failure": _value(row, _FIELD_ALIASES["leak_failure"]),
            "leak_hazard": _value(row, _FIELD_ALIASES["leak_hazard"]),
            "fire_hazard": _value(row, _FIELD_ALIASES["fire_hazard"]),
            "explosion_hazard": _value(row, _FIELD_ALIASES["explosion_hazard"]),
        },
        "promotion_status": "SCENARIO_ONLY_PROVIDER_PACKET_MISSING",
        "missing_provider_fields": list(PROVIDER_RELEASE_REQUIRED_FIELDS),
        "frequency_assigned": False,
    }


def _audit_csv(path: Path, root: Path) -> dict[str, Any]:
    text, encoding = _decode_csv(path)
    rows = list(csv.DictReader(text.splitlines()))
    records = []
    for index, row in enumerate(rows, start=2):
        if any(_value(row, aliases) is not None for aliases in _FIELD_ALIASES.values()):
            records.append(_scenario_record(path, root, index, row))
    return {
        "file": str(path.relative_to(root)),
        "sha256": _sha256(path),
        "encoding": encoding,
        "row_count": len(rows),
        "scenario_row_count": len(records),
        "scenario_records": records,
    }


def _classify_header(header: list[str]) -> str:
    joined = "|".join(header)
    if any(key in joined for key in ("timestamp", "일시", "시간")):
        return "timeseries"
    if any(key in joined for key in ("from_step", "progress_pct", "action", "절차", "동작")):
        return "sequence_timeseries"
    return "metadata_or_unknown"


def _audit_workbook(path: Path, root: Path) -> dict[str, Any]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return {
            "file": str(path.relative_to(root)),
            "sha256": _sha256(path),
            "status": "WORKBOOK_READER_UNAVAILABLE",
            "sheet_count": None,
            "sheets": [],
        }
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for worksheet in workbook.worksheets:
        iterator = worksheet.iter_rows(values_only=True)
        first = next(iterator, ())
        header = [str(value) if value is not None else "" for value in first]
        row_count = 1
        for _ in iterator:
            row_count += 1
        sheets.append({
            "sheet": worksheet.title,
            "row_count": row_count,
            "column_count": len(header),
            "header": header[:32],
            "kind": _classify_header(header),
            "promotion_status": "TIME_SERIES_OR_SEQUENCE_ONLY_PROVIDER_PACKET_MISSING",
        })
    return {
        "file": str(path.relative_to(root)),
        "sha256": _sha256(path),
        "status": "READ_ONLY_WORKBOOK_AUDITED",
        "sheet_count": len(sheets),
        "sheets": sheets,
    }


def audit_scenario_root(root: str | Path) -> dict[str, Any]:
    """Audit center-style CSV/XLSX scenario evidence without promotion."""
    root_path = Path(root)
    if not root_path.exists():
        return {
            "schema": SCENARIO_EVIDENCE_SCHEMA,
            "status": "MISSING_SOURCE_ROOT",
            "source_root": str(root_path),
            "blocking_reasons": ["scenario evidence root does not exist"],
        }
    csv_reports = []
    workbook_reports = []
    errors = []
    for path in sorted(root_path.rglob("*")):
        if not path.is_file() or any(part in {".git", "__pycache__", ".venv"} for part in path.parts):
            continue
        try:
            if path.suffix.lower() == ".csv":
                csv_reports.append(_audit_csv(path, root_path))
            elif path.suffix.lower() in {".xlsx", ".xlsm"}:
                workbook_reports.append(_audit_workbook(path, root_path))
        except (OSError, UnicodeError, ValueError, RuntimeError) as error:
            errors.append({"file": str(path.relative_to(root_path)), "error": str(error)})

    records = [record for report in csv_reports for record in report["scenario_records"]]
    family_counts = Counter(
        family
        for record in records
        for family in record["candidate_accident_families"]
    )
    sequence_sheet_count = sum(
        1
        for report in workbook_reports
        for sheet in report.get("sheets", [])
        if sheet.get("kind") == "sequence_timeseries"
    )
    timeseries_sheet_count = sum(
        1
        for report in workbook_reports
        for sheet in report.get("sheets", [])
        if sheet.get("kind") == "timeseries"
    )
    blockers = []
    if records:
        blockers.append("scenario registers describe candidate hazards but contain no resolved provider release packet")
    if sequence_sheet_count or timeseries_sheet_count:
        blockers.append("workbook sequence/time-series exports lack release mass-flow, termination, geometry, and provider ownership fields")
    if errors:
        blockers.append("one or more scenario evidence files could not be read")
    return {
        "schema": SCENARIO_EVIDENCE_SCHEMA,
        "status": "SCENARIO_EVIDENCE_ONLY" if records or workbook_reports else "NO_SCENARIO_EVIDENCE",
        "source_root": str(root_path),
        "files": {
            "csv_count": len(csv_reports),
            "workbook_count": len(workbook_reports),
            "csv_rows": sum(report["row_count"] for report in csv_reports),
            "scenario_rows": len(records),
            "sequence_sheet_count": sequence_sheet_count,
            "timeseries_sheet_count": timeseries_sheet_count,
        },
        "candidate_accident_family_counts": dict(sorted(family_counts.items())),
        "scenario_records": records,
        "csv_reports": csv_reports,
        "workbook_reports": workbook_reports,
        "provider_promotion": {
            "qualified_packet_count": 0,
            "frequency_assigned": False,
            "required_fields": list(PROVIDER_RELEASE_REQUIRED_FIELDS),
            "scenario_rows_are_not_release_packets": True,
        },
        "errors": errors,
        "blocking_reasons": list(dict.fromkeys(blockers)),
    }

