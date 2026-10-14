"""Audit support-center HAZOP operating-mode evidence without inventing bindings.

The inspection-center package contains three useful kinds of evidence:

* operation-sequence CSV files with explicit scenario, tank, step and hazard
  columns;
* a PDF/PPTX description of the three process scenarios; and
* predicted/training time series with PT/TT/DPT tags.

Only the first two are treated as qualitative HAZOP evidence here.  Numeric
time-series values remain withheld from state-snapshot binding until a reviewed
tag/unit map is supplied.  This audit never creates accident frequencies or
release packets from normal operation data.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SCHEMA = "prism.hazop_operating_mode_evidence_audit.v1"

SEQUENCE_SOURCES: tuple[tuple[str, str], ...] = (
    ("1. 액화수소 인수 시나리오 데이터/액화수소인수_운전시퀀스.csv", "receiving"),
    ("2. 액화수소 저장(벤트) 시나리오 데이터/액화수소저장벤트_운전시퀀스.csv", "storage_vent"),
    ("3. 액화수소 공급 시나리오 데이터/수소공급_운전시퀀스.csv", "supply"),
)

DESCRIPTION_SOURCES: tuple[str, ...] = (
    "액화수소 인수·저장(벤트)·공급 시나리오 설명자료.pdf",
    "액화수소 인수·저장(벤트)·공급 시나리오 설명자료.pptx",
)

REQUIRED_FIELDS = (
    "시나리오",
    "탱크",
    "절차번호",
    "동작내용",
    "위험성분류",
    "누출_예상고장",
    "누출_위험",
    "누출_조치방법",
    "화재_예상고장",
    "화재_위험",
    "화재_조치방법",
    "폭발_예상고장",
    "폭발_위험",
    "폭발_조치방법",
)

HAZARD_FIELDS = {
    "leak": ("누출_예상고장", "누출_위험", "누출_조치방법", "누출_근거기준"),
    "fire": ("화재_예상고장", "화재_위험", "화재_조치방법", "화재_근거기준"),
    "explosion": ("폭발_예상고장", "폭발_위험", "폭발_조치방법", "폭발_근거기준"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_csv(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw, 0, min(1, len(raw)), f"cannot decode {path}")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mode_from_explicit_labels(scenario: str, supply_mode: str) -> tuple[str, str]:
    """Return a mode key and its evidence basis from labels only.

    No pressure, temperature, action, equipment or release value is examined.
    """
    if "인수" in scenario:
        return "receiving", "explicit scenario label: 액화수소 인수"
    if "저장" in scenario and "벤트" in scenario:
        return "storage_vent", "explicit scenario label: 액화수소 저장(벤트)"
    if "공급" in scenario:
        if supply_mode == "기체수소":
            return "supply_gas", "explicit 공급모드 label: 기체수소"
        if supply_mode == "액화수소":
            return "supply_liquid", "explicit 공급모드 label: 액화수소"
        return "supply_unspecified", "explicit scenario label: 수소 공급; 공급모드 missing or unrecognised"
    return "unmapped", "source scenario label not in the supported dictionary"


def _stable_row_id(mode_key: str, tank: str, procedure: str, row_number: int) -> str:
    raw = "|".join((mode_key, tank, procedure, str(row_number)))
    return f"support-center:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _read_sequence(path: Path, expected_group: str) -> dict[str, Any]:
    text, encoding = _decode_csv(path)
    reader = csv.DictReader(io.StringIO(text))
    fields = [str(value) for value in (reader.fieldnames or [])]
    missing = [field for field in REQUIRED_FIELDS if field not in fields]
    rows: list[dict[str, Any]] = []
    scenario_counts: Counter[str] = Counter()
    mode_counts: Counter[str] = Counter()
    tank_counts: Counter[str] = Counter()
    hazard_class_counts: Counter[str] = Counter()
    hazard_presence = Counter()
    errors: list[str] = []
    for row_number, raw in enumerate(reader, start=2):
        row = {str(key): _text(value) for key, value in raw.items() if key is not None}
        scenario = row.get("시나리오", "")
        supply_mode = row.get("공급모드", "")
        tank = row.get("탱크", "")
        procedure = row.get("절차번호", "")
        mode_key, mode_basis = _mode_from_explicit_labels(scenario, supply_mode)
        if mode_key == "unmapped":
            errors.append(f"row {row_number}: unsupported explicit scenario label")
        if not scenario or not tank or not procedure or not row.get("동작내용"):
            errors.append(f"row {row_number}: missing scenario/tank/procedure/action")
        scenario_counts[scenario] += 1
        mode_counts[mode_key] += 1
        tank_counts[tank] += 1
        hazard_class_counts[row.get("위험성분류", "")] += 1
        present: list[str] = []
        for category, category_fields in HAZARD_FIELDS.items():
            if any(row.get(field) for field in category_fields):
                present.append(category)
                hazard_presence[category] += 1
        rows.append(
            {
                "source_row": row_number,
                "source_row_id": _stable_row_id(mode_key, tank, procedure, row_number),
                "scenario_label": scenario,
                "supply_mode_label": supply_mode or None,
                "operating_mode_key": mode_key,
                "operating_mode_basis": mode_basis,
                "tank_label": tank,
                "procedure_number": procedure,
                "action": row.get("동작내용", ""),
                "hazard_class": row.get("위험성분류") or None,
                "hazard_categories_present": present,
                "qualitative_hazop_evidence": {
                    category: {
                        "failure": row.get(fields[0]) or None,
                        "risk": row.get(fields[1]) or None,
                        "safeguard_or_action": row.get(fields[2]) or None,
                        "reference": row.get(fields[3]) or None,
                    }
                    for category, fields in HAZARD_FIELDS.items()
                },
                "frequency_binding": "WITHHELD_NO_EVENT_FREQUENCY_IN_SOURCE",
                "release_packet_binding": "WITHHELD_NO_RELEASE_PACKET_IN_SOURCE",
            }
        )
    return {
        "relative_path": None,
        "expected_group": expected_group,
        "encoding": encoding,
        "field_names": fields,
        "missing_required_fields": missing,
        "row_count": len(rows),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "operating_mode_counts": dict(sorted(mode_counts.items())),
        "tank_counts": dict(sorted(tank_counts.items())),
        "hazard_class_counts": dict(sorted(hazard_class_counts.items())),
        "hazard_category_presence_counts": dict(sorted(hazard_presence.items())),
        "rows": rows,
        "errors": errors,
    }


def _extract_pdf_text(path: Path) -> tuple[str | None, str | None]:
    try:
        from pypdf import PdfReader
    except Exception:
        return None, "pypdf_unavailable"
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages), None
    except Exception as error:  # pragma: no cover - depends on malformed external PDFs
        return None, f"pdf_read_error:{type(error).__name__}"


def _extract_pptx_text(path: Path) -> tuple[str | None, str | None]:
    try:
        with zipfile.ZipFile(path) as archive:
            parts = [name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
            texts: list[str] = []
            for name in sorted(parts):
                root = ElementTree.fromstring(archive.read(name))
                texts.extend(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
            return "\n".join(texts), None
    except Exception as error:  # pragma: no cover - depends on external package validity
        return None, f"pptx_read_error:{type(error).__name__}"


def _description_record(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".pdf":
        text, error = _extract_pdf_text(path)
    else:
        text, error = _extract_pptx_text(path)
    anchors = {
        "receiving_scenario": "액화수소인수" in (text or "") or "액화수소 인수" in (text or ""),
        "storage_vent_scenario": "저장" in (text or "") and "벤트" in (text or ""),
        "supply_scenario": "액화수소공급" in (text or "") or "수소공급" in (text or ""),
        "pressure_vent_setpoints": "6.5" in (text or "") and "6.0" in (text or ""),
        "sensor_or_prediction_description": "센서" in (text or "") and ("예측" in (text or "") or "학습" in (text or "")),
    }
    return {
        "relative_path": None,
        "suffix": path.suffix.lower(),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "read_status": "READ" if text is not None else "READ_ERROR",
        "read_error": error,
        "page_or_slide_text_length": len(text or ""),
        "anchors": anchors,
    }


def _load_timeseries_audit(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("timeseries audit must contain a JSON object")
    return dict(payload)


def audit_hazop_operating_mode_evidence(
    source_root: str | Path,
    *,
    timeseries_audit_path: str | Path | None = None,
) -> dict[str, Any]:
    """Audit explicit support-center HAZOP modes and retain state-binding gates."""
    root = Path(source_root)
    if not root.is_dir():
        raise ValueError(f"source_root is not a directory: {root}")
    sequence_records: list[dict[str, Any]] = []
    sequence_errors: list[str] = []
    for relative, expected_group in SEQUENCE_SOURCES:
        path = root / relative
        if not path.is_file():
            sequence_errors.append(f"missing sequence source: {relative}")
            continue
        record = _read_sequence(path, expected_group)
        record["relative_path"] = relative
        record["sha256"] = _sha256(path)
        record["size_bytes"] = path.stat().st_size
        sequence_records.append(record)
        sequence_errors.extend(f"{relative}: {error}" for error in record["errors"])

    description_records: list[dict[str, Any]] = []
    description_errors: list[str] = []
    for relative in DESCRIPTION_SOURCES:
        path = root / relative
        if not path.is_file():
            description_errors.append(f"missing description source: {relative}")
            continue
        record = _description_record(path)
        record["relative_path"] = relative
        description_records.append(record)
        if record["read_status"] != "READ":
            description_errors.append(f"{relative}: {record['read_error']}")

    timeseries_path = Path(timeseries_audit_path) if timeseries_audit_path else None
    timeseries = _load_timeseries_audit(timeseries_path)
    aggregate = timeseries.get("aggregate", {}) if isinstance(timeseries, Mapping) else {}
    reviewed_units = bool(aggregate.get("reviewed_unit_map_supplied"))
    unit_status_counts = aggregate.get("numeric_signal_unit_status_count", {})
    unit_status_clear = isinstance(unit_status_counts, Mapping) and not any(
        str(key).upper() in {"MISSING_OR_UNCONFIRMED", "UNKNOWN"} and int(value or 0) > 0
        for key, value in unit_status_counts.items()
    )
    numeric_state_binding_allowed = reviewed_units and unit_status_clear
    status = (
        "HAZOP_OPERATING_MODE_EVIDENCE_AUDIT_WITH_STATE_BINDING_ALLOWED"
        if not sequence_errors and not description_errors and numeric_state_binding_allowed
        else "HAZOP_OPERATING_MODE_EVIDENCE_AUDIT_WITH_STATE_BINDING_WITHHELD"
    )
    all_rows = [row for record in sequence_records for row in record["rows"]]
    scenario_counts = Counter(row["scenario_label"] for row in all_rows)
    mode_counts = Counter(row["operating_mode_key"] for row in all_rows)
    hazard_counts = Counter(row.get("hazard_class") or "" for row in all_rows)
    return {
        "schema_version": SCHEMA,
        "status": status,
        "source_root": str(root),
        "sequence_source_count": len(sequence_records),
        "sequence_row_count": len(all_rows),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "operating_mode_counts": dict(sorted(mode_counts.items())),
        "hazard_class_counts": dict(sorted(hazard_counts.items())),
        "sequence_sources": sequence_records,
        "description_sources": description_records,
        "timeseries_audit": {
            "source_path": str(timeseries_path) if timeseries_path else None,
            "source_schema": timeseries.get("schema_version") if isinstance(timeseries, Mapping) else None,
            "reviewed_unit_map_supplied": reviewed_units,
            "numeric_signal_unit_status_count": dict(unit_status_counts) if isinstance(unit_status_counts, Mapping) else {},
            "numeric_state_binding_allowed": numeric_state_binding_allowed,
            "status": "REVIEWED_UNIT_MAP_CLEAR" if numeric_state_binding_allowed else "WITHHELD_UNITS_UNCONFIRMED",
        },
        "errors": sequence_errors + description_errors,
        "policy": {
            "operating_mode_from_explicit_labels_only": True,
            "mode_inference_from_numeric_values_performed": False,
            "mode_inference_from_equipment_or_release_bin_performed": False,
            "frequency_inference_performed": False,
            "release_packet_generation_performed": False,
            "normal_timeseries_promoted_to_accident_evidence": False,
            "state_snapshot_binding_performed": False,
            "state_snapshot_binding_allowed": numeric_state_binding_allowed,
            "unit_and_tag_review_required_before_numeric_binding": True,
            "source_rows_are_qualitative_hazop_evidence_only": True,
        },
        "coverage": {
            "qualitative_hazop_rows_closed": bool(sequence_records) and not sequence_errors,
            "explicit_operating_mode_rows_closed": all(
                row["operating_mode_key"] in {"receiving", "storage_vent", "supply_gas", "supply_liquid"}
                for row in all_rows
            ),
            "frequency_event_binding_closed": False,
            "release_consequence_binding_closed": False,
            "numeric_monitoring_state_binding_closed": numeric_state_binding_allowed,
        },
    }
