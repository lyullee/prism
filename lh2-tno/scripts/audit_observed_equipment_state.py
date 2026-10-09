#!/usr/bin/env python3
"""Normalize observed LH2 telemetry into a state-only evidence ledger.

The input manifest maps source columns to SI quantities.  It can read CSV and
XLSX files when ``openpyxl`` is available (the bundled workspace runtime
provides it).  The output is intentionally diagnostic-only and cannot create
an accident or assign an event frequency.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.observed_state_evidence import build_observed_state_evidence  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _convert(value: Any, rule: dict[str, Any]) -> float | None:
    raw = _number(value)
    if raw is None:
        return None
    unit = str(rule.get("unit", "si")).lower()
    if unit in {"c", "degc", "°c"}:
        raw += 273.15
    elif unit in {"mpa"}:
        raw *= 1_000_000.0
    elif unit in {"kpa"}:
        raw *= 1_000.0
    elif unit in {"bar"}:
        raw *= 100_000.0
    elif unit in {"g/s", "g_s"}:
        raw /= 1_000.0
    elif unit not in {"si", "pa", "k", "kg", "kg/s", "fraction", "m", "s"}:
        raise ValueError(f"unsupported unit conversion: {unit}")
    raw = raw * float(rule.get("scale", 1.0)) + float(rule.get("offset", 0.0))
    return raw if math.isfinite(raw) else None


def _time_seconds(value: Any, *, index: int, rule: dict[str, Any]) -> float:
    if value is None or value == "":
        return index * float(rule.get("cadence_s", 1.0))
    numeric = _number(value)
    if numeric is not None:
        mode = str(rule.get("mode", "seconds")).lower()
        if mode == "minutes":
            return numeric * 60.0
        if mode == "hours":
            return numeric * 3600.0
        if mode == "step":
            return numeric * float(rule.get("cadence_s", 1.0))
        return numeric
    if isinstance(value, datetime):
        base = rule.get("base_timestamp")
        if isinstance(base, str):
            origin = datetime.fromisoformat(base)
            return (value - origin).total_seconds()
    return index * float(rule.get("cadence_s", 1.0))


def _read_csv(path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    with path.open("r", encoding=source.get("encoding", "utf-8-sig"), newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows


def _read_xlsx(path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        import openpyxl
    except ImportError as error:
        raise RuntimeError("XLSX input requires openpyxl; use the bundled workspace Python runtime") from error
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = source.get("sheet")
    if sheet is None:
        index = int(source.get("sheet_index", 0))
        worksheet = workbook.worksheets[index]
    else:
        worksheet = workbook[sheet]
    iterator = worksheet.iter_rows(values_only=True)
    header = next(iterator, None)
    if not header:
        return []
    names = [str(value).strip() if value is not None else "" for value in header]
    return [dict(zip(names, row)) for row in iterator]


def _source_from_manifest(spec: dict[str, Any], *, source_root: Path | None) -> dict[str, Any]:
    relative = Path(str(spec["path"]))
    path = relative if relative.is_absolute() else ((source_root / relative) if source_root else relative)
    if not path.exists():
        raise FileNotFoundError(path)
    fmt = str(spec.get("format", path.suffix.lstrip(".")).lower())
    rows = _read_xlsx(path, spec) if fmt in {"xlsx", "xlsm"} else _read_csv(path, spec)
    time_rule = spec.get("time", {})
    if not isinstance(time_rule, dict):
        raise ValueError(f"source {spec.get('source_id')} time rule must be an object")
    signal_map = spec.get("signals")
    if not isinstance(signal_map, dict) or not signal_map:
        raise ValueError(f"source {spec.get('source_id')} requires a non-empty signals mapping")
    samples: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        values: dict[str, Any] = {}
        for quantity, rule_value in signal_map.items():
            rule = rule_value if isinstance(rule_value, dict) else {"column": rule_value}
            column = rule.get("column", quantity)
            converted = _convert(row.get(column), rule)
            if converted == 0.0 and rule.get("zero_is_missing") is True:
                converted = None
            if quantity == "pressure" and converted is not None and converted <= 0 and rule.get("nonpositive_is_missing") is True:
                converted = None
            if converted is not None:
                values[quantity] = {
                    "value_si": converted,
                    "sensor_location": rule.get("sensor_location"),
                    "quality": "valid",
                }
        if not values:
            continue
        samples.append(
            {
                "captured_at_s": _time_seconds(row.get(time_rule.get("column")), index=index, rule=time_rule),
                "values": values,
                "quality": "valid",
            }
        )
    source = dict(spec)
    source.update(
        {
            "source_path": str(relative),
            "resolved_source_path": str(path),
            "source_sha256": _sha256(path),
            "format": fmt,
            "signal_map": signal_map,
            "samples": samples,
        }
    )
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = _load(args.manifest)
    if manifest.get("schema_version") != "prism.observed_state_input_manifest.v1":
        raise SystemExit("manifest schema_version must be prism.observed_state_input_manifest.v1")
    specs = manifest.get("sources")
    if not isinstance(specs, list) or not specs:
        raise SystemExit("manifest requires a non-empty sources list")
    manifest_source_root = manifest.get("source_root")
    source_root = args.source_root
    if source_root is None and isinstance(manifest_source_root, str) and manifest_source_root:
        source_root = Path(manifest_source_root)
    try:
        sources = [_source_from_manifest(spec, source_root=source_root) for spec in specs]
        report = build_observed_state_evidence(sources)
    except (OSError, UnicodeDecodeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise SystemExit(f"observed equipment state audit failed: {error}") from error
    report["manifest"] = {
        "path": str(args.manifest),
        "schema_version": manifest.get("schema_version"),
        "source_root": str(source_root) if source_root else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "source_count": report["source_count"],
        "sample_count": report["sample_count"],
        "component_count": report["component_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
