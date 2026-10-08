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
import re
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from statistics import median
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


def _time_axis_index(header: list[str]) -> int | None:
    """Return an explicit time column index without assigning units to numbers."""
    for index, value in enumerate(header):
        lowered = value.strip().lower()
        if any(token in lowered for token in ("timestamp", "date_time", "datetime", "일시", "시간")):
            return index
    return None


def _explicit_unit(header: str) -> str | None:
    match = re.search(r"\(([^()]*)\)", header)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _sensor_column_evidence(header: list[str], time_index: int | None) -> list[dict[str, Any]]:
    evidence = []
    for index, value in enumerate(header):
        if index == time_index or not value.strip():
            continue
        lowered = value.strip().lower()
        upper = value.strip().upper()
        sensor_token = any(token in lowered for token in (
            "sensor", "pressure", "temperature", "flow", "level", "압력", "온도", "유량", "레벨", "차압",
        ))
        short_tag = re.search(r"(?:^|[^A-Z])(?:DPT|PT|TT|FT|LT)\s*[-_ ]?\d", upper) is not None
        if sensor_token or short_tag:
            evidence.append({
                "column_index": index,
                "header": value,
                "explicit_unit": _explicit_unit(value),
            })
    return evidence


def _parse_time_value(value: Any) -> datetime | None:
    """Parse typed/ISO time values only; numeric samples stay untyped."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, time):
        return datetime.combine(date(2000, 1, 1), value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for candidate in (text, text.replace("/", "-"), text.rstrip("Z")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, pattern).replace(year=2000, month=1, day=1)
        except ValueError:
            continue
    time_fragment = re.search(r"(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?)(?!\d)", text)
    if time_fragment:
        for pattern in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(time_fragment.group(1), pattern).replace(
                    year=2000, month=1, day=1
                )
            except ValueError:
                continue
    return None


def _telemetry_evidence(header: list[str], data_rows: list[tuple[Any, ...]], kind: str) -> dict[str, Any]:
    time_index = _time_axis_index(header)
    sensor_columns = _sensor_column_evidence(header, time_index)
    parsed_times = []
    if time_index is not None:
        for row in data_rows:
            if time_index < len(row):
                parsed = _parse_time_value(row[time_index])
                if parsed is not None:
                    parsed_times.append(parsed)
    intervals = [
        (later - earlier).total_seconds()
        for earlier, later in zip(parsed_times, parsed_times[1:])
        if (later - earlier).total_seconds() >= 0
    ]
    metadata_presence = {
        "component_mapping": any(
            any(token in value.strip().lower() for token in ("component_id", "asset_id", "equipment", "설비", "탱크"))
            for value in header
        ),
        "sensor_location": any(
            any(token in value.strip().lower() for token in ("sensor_location", "location", "위치", "노즐"))
            for value in header
        ),
        "pressure_basis": any(
            any(token in value.strip().lower() for token in ("pressure_basis", "gauge", "absolute", "압력기준", "게이지", "절대"))
            for value in header
        ),
        "provider_release_ownership": any(
            any(token in value.strip().lower() for token in ("provider", "release_owner", "방출공급자"))
            for value in header
        ),
    }
    missing_metadata = [name for name, present in metadata_presence.items() if not present]
    candidate = time_index is not None and bool(sensor_columns)
    return {
        "kind": kind,
        "time_axis_header": header[time_index] if time_index is not None else None,
        "time_axis_present": time_index is not None,
        "sample_count": len(data_rows),
        "parseable_time_count": len(parsed_times),
        "first_time": parsed_times[0].isoformat() if parsed_times else None,
        "last_time": parsed_times[-1].isoformat() if parsed_times else None,
        "sample_interval_s": {
            "count": len(intervals),
            "min": min(intervals) if intervals else None,
            "median": median(intervals) if intervals else None,
            "max": max(intervals) if intervals else None,
            "numeric_time_values_withheld": time_index is not None and any(
                time_index < len(row) and isinstance(row[time_index], (int, float)) and not isinstance(row[time_index], bool)
                for row in data_rows
            ),
        },
        "sensor_columns": sensor_columns,
        "metadata_presence": metadata_presence,
        "missing_metadata": missing_metadata,
        "telemetry_candidate": candidate,
        "promotion_status": (
            "TELEMETRY_CANDIDATE_METADATA_INCOMPLETE" if candidate and missing_metadata
            else "TELEMETRY_CANDIDATE_READY_FOR_PROVIDER_MAPPING" if candidate
            else "NO_TELEMETRY_CANDIDATE"
        ),
    }


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
        data_rows = list(iterator)
        row_count = 1 + len(data_rows)
        telemetry = _telemetry_evidence(header, data_rows, _classify_header(header))
        sheets.append({
            "sheet": worksheet.title,
            "row_count": row_count,
            "column_count": len(header),
            "header": header[:32],
            "kind": _classify_header(header),
            "promotion_status": "TIME_SERIES_OR_SEQUENCE_ONLY_PROVIDER_PACKET_MISSING",
            "telemetry": telemetry,
        })
    telemetry_candidate_sheet_count = sum(
        1 for sheet in sheets if sheet["telemetry"]["telemetry_candidate"]
    )
    telemetry_metadata_incomplete_sheet_count = sum(
        1
        for sheet in sheets
        if sheet["telemetry"]["promotion_status"] == "TELEMETRY_CANDIDATE_METADATA_INCOMPLETE"
    )
    return {
        "file": str(path.relative_to(root)),
        "sha256": _sha256(path),
        "status": "READ_ONLY_WORKBOOK_AUDITED",
        "sheet_count": len(sheets),
        "telemetry_candidate_sheet_count": telemetry_candidate_sheet_count,
        "telemetry_metadata_incomplete_sheet_count": telemetry_metadata_incomplete_sheet_count,
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
    telemetry_candidate_sheet_count = sum(
        report.get("telemetry_candidate_sheet_count", 0) for report in workbook_reports
    )
    telemetry_metadata_incomplete_sheet_count = sum(
        report.get("telemetry_metadata_incomplete_sheet_count", 0) for report in workbook_reports
    )
    telemetry_parseable_time_sheet_count = sum(
        1
        for report in workbook_reports
        for sheet in report.get("sheets", [])
        if sheet.get("telemetry", {}).get("parseable_time_count", 0) > 1
    )
    interval_profiles = Counter()
    for report in workbook_reports:
        for sheet in report.get("sheets", []):
            telemetry = sheet.get("telemetry", {})
            median_interval = telemetry.get("sample_interval_s", {}).get("median")
            if median_interval is not None and telemetry.get("telemetry_candidate"):
                interval_profiles[str(median_interval)] += 1
    blockers = []
    if records:
        blockers.append("scenario registers describe candidate hazards but contain no resolved provider release packet")
    if sequence_sheet_count or timeseries_sheet_count:
        blockers.append("workbook sequence/time-series exports lack release mass-flow, termination, geometry, and provider ownership fields")
    if telemetry_candidate_sheet_count:
        blockers.append("workbook sensor traces have a time axis but lack component mapping, sensor location, pressure basis, and provider release ownership")
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
            "telemetry_candidate_sheet_count": telemetry_candidate_sheet_count,
            "telemetry_metadata_incomplete_sheet_count": telemetry_metadata_incomplete_sheet_count,
            "telemetry_parseable_time_sheet_count": telemetry_parseable_time_sheet_count,
            "telemetry_median_interval_s_profiles": dict(sorted(interval_profiles.items(), key=lambda item: float(item[0]))),
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
