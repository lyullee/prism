"""Strict CSV/TSV-to-runtime-state adapter for digital-twin integrations.

This module accepts a reviewed tabular historian or simulator export and
builds the source payload consumed by ``build_observed_state_runtime_frames``.
Every engineering unit, pressure basis, sensor location, timestamp column and
operating-mode source is supplied by the caller. Header names, value ranges
and row order are never used to infer missing metadata.

The adapter produces state samples only. It never creates an accident, release
duration, inventory boundary, annual frequency or consequence result.
"""
from __future__ import annotations

import csv
import hashlib
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .inspection_timeseries import frame_from_row
from .observed_state_runtime import build_observed_state_runtime_frames
from .telemetry import TelemetryNormalizer


SCHEMA = "prism.tabular_runtime_source.v1"
_ORIGINS = {
    "historian_measured",
    "figure_digitized",
    "video_recovered",
    "reconstructed",
    "model_prediction",
    "synthetic",
}


class TabularRuntimeAdapterError(ValueError):
    """Raised when a tabular state export is not explicitly reviewable."""


def _name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TabularRuntimeAdapterError(f"{field} must be a non-empty string")
    return value.strip()


def _finite(value: Any, field: str, *, nonnegative: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise TabularRuntimeAdapterError(f"{field} must be numeric") from error
    if not math.isfinite(number) or (nonnegative and number < 0.0):
        raise TabularRuntimeAdapterError(
            f"{field} must be finite" + (" and non-negative" if nonnegative else "")
        )
    return number


def _source_time_seconds(
    value: Any,
    field: str,
    *,
    scale_to_s: float,
    timestamp_base: str | datetime | None,
) -> float:
    """Convert an explicitly supplied numeric or datetime source timestamp."""
    if isinstance(value, datetime):
        if timestamp_base is None:
            raise TabularRuntimeAdapterError(
                f"{field} is a datetime; provide timestamp_base explicitly"
            )
        if isinstance(timestamp_base, str):
            try:
                base = datetime.fromisoformat(timestamp_base)
            except ValueError as error:
                raise TabularRuntimeAdapterError(
                    "timestamp_base must be an ISO-8601 datetime"
                ) from error
        elif isinstance(timestamp_base, datetime):
            base = timestamp_base
        else:
            raise TabularRuntimeAdapterError(
                "timestamp_base must be an ISO-8601 datetime or datetime object"
            )
        if (value.tzinfo is None) != (base.tzinfo is None):
            raise TabularRuntimeAdapterError(
                f"{field} and timestamp_base must use the same timezone awareness"
            )
        return (value - base).total_seconds() * scale_to_s
    return _finite(value, field) * scale_to_s


def _numeric_row(
    row: Mapping[str, Any],
    bindings: Mapping[str, Mapping[str, Any]],
    index: int,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for column in bindings:
        if column not in row:
            raise TabularRuntimeAdapterError(
                f"row {index} is missing explicitly bound column {column}"
            )
        raw = row[column]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raise TabularRuntimeAdapterError(
                f"row {index} has an empty value for explicitly bound column {column}"
            )
        values[column] = _finite(raw, f"row {index}.{column}")
    return values


def _check_bindings(
    bindings: Mapping[str, Mapping[str, Any]],
    normalizer: TelemetryNormalizer,
    component_id: str,
) -> None:
    if not isinstance(bindings, Mapping) or not bindings:
        raise TabularRuntimeAdapterError("bindings must be a non-empty mapping")
    mappings = getattr(normalizer, "mappings", None)
    if not isinstance(mappings, Mapping):
        raise TabularRuntimeAdapterError("normalizer must expose explicit tag mappings")
    for column, binding in bindings.items():
        column_name = _name(column, "bindings column")
        if not isinstance(binding, Mapping):
            raise TabularRuntimeAdapterError(f"bindings[{column_name}] must be an object")
        tag = _name(binding.get("tag"), f"bindings[{column_name}].tag")
        unit = _name(binding.get("unit"), f"bindings[{column_name}].unit")
        if binding.get("quality") != "valid":
            raise TabularRuntimeAdapterError(
                f"bindings[{column_name}].quality must be 'valid'"
            )
        mapping = mappings.get(tag)
        if mapping is None:
            raise TabularRuntimeAdapterError(
                f"bindings[{column_name}] tag {tag} is absent from the normalizer"
            )
        if mapping.component_id != component_id:
            raise TabularRuntimeAdapterError(
                f"bindings[{column_name}] tag {tag} maps to component {mapping.component_id}, "
                f"not {component_id}"
            )
        if mapping.source_unit != unit:
            raise TabularRuntimeAdapterError(
                f"bindings[{column_name}] unit {unit} disagrees with normalizer unit {mapping.source_unit}"
            )


def _build_runtime_source_from_rows(
    source_path: Path,
    *,
    source_id: str,
    component_id: str,
    timestamp_column: str,
    bindings: Mapping[str, Mapping[str, Any]],
    normalizer: TelemetryNormalizer,
    rows: list[Mapping[str, Any]],
    operating_mode_column: str | None,
    operating_mode: str | None,
    origin: str,
    arrival_delay_s: float,
    timestamp_scale_to_s: float,
    timestamp_base: str | datetime | None,
    ambient_pressure_pa: float | None,
    format_name: str,
    format_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one source from already decoded rows.

    CSV and XLSX decoding deliberately happens outside this function.  Keeping
    row validation in one path prevents the two formats from acquiring
    different unit, timestamp, or operating-mode semantics.
    """
    source_id = _name(source_id, "source_id")
    component_id = _name(component_id, "component_id")
    timestamp_column = _name(timestamp_column, "timestamp_column")
    if origin not in _ORIGINS:
        raise TabularRuntimeAdapterError(f"unsupported origin: {origin}")
    arrival_delay_s = _finite(arrival_delay_s, "arrival_delay_s", nonnegative=True)
    timestamp_scale_to_s = _finite(
        timestamp_scale_to_s, "timestamp_scale_to_s", nonnegative=True
    )
    if timestamp_scale_to_s <= 0.0:
        raise TabularRuntimeAdapterError("timestamp_scale_to_s must be positive")
    if operating_mode_column is None and operating_mode is None:
        raise TabularRuntimeAdapterError(
            "provide operating_mode_column or explicit operating_mode"
        )
    if operating_mode is not None:
        operating_mode = _name(operating_mode, "operating_mode")
    if operating_mode_column is not None:
        operating_mode_column = _name(operating_mode_column, "operating_mode_column")
    _check_bindings(bindings, normalizer, component_id)
    reserved = {timestamp_column}
    if operating_mode_column:
        reserved.add(operating_mode_column)
    overlap = sorted(reserved.intersection(str(column) for column in bindings))
    if overlap:
        raise TabularRuntimeAdapterError(
            "timestamp/mode columns cannot also be signal bindings: " + ", ".join(overlap)
        )
    if not rows:
        raise TabularRuntimeAdapterError(f"{format_name.upper()} source contains no data rows")

    samples: list[dict[str, Any]] = []
    previous_time: float | None = None
    for index, row in enumerate(rows, start=2):
        if not isinstance(row, Mapping):
            raise TabularRuntimeAdapterError(f"row {index} must be an object")
        raw_time = row.get(timestamp_column)
        source_time_s = _source_time_seconds(
            raw_time,
            f"row {index}.{timestamp_column}",
            scale_to_s=timestamp_scale_to_s,
            timestamp_base=timestamp_base,
        )
        if source_time_s < 0.0:
            raise TabularRuntimeAdapterError(f"row {index} source time must be non-negative")
        if previous_time is not None and source_time_s <= previous_time:
            raise TabularRuntimeAdapterError(
                f"{format_name.upper()} source times must be strictly increasing at row {index}"
            )
        previous_time = source_time_s
        numeric_row = _numeric_row(row, bindings, index)
        frame = frame_from_row(
            numeric_row,
            stream_id=source_id,
            sequence=index - 2,
            source_time_s=source_time_s,
            arrival_time_s=source_time_s + arrival_delay_s,
            origin=origin,
            bindings=bindings,
        )
        normalized = normalizer.normalize(
            frame,
            now_s=source_time_s + arrival_delay_s,
            ambient_pressure_pa=ambient_pressure_pa,
        )
        mode = operating_mode
        if operating_mode_column is not None:
            mode = _name(row.get(operating_mode_column), f"row {index}.{operating_mode_column}")
            if operating_mode is not None and mode != operating_mode:
                raise TabularRuntimeAdapterError(
                    f"row {index} operating mode conflicts with explicit operating_mode"
                )
        sample = {
            "captured_at_s": source_time_s,
            "quality": "valid",
            "values": {
                tag: {**value, "quality": "valid"}
                for tag, value in normalized["values"].items()
            },
        }
        if mode is not None:
            sample["operating_mode"] = mode
        samples.append(sample)

    binding_metadata = {
        "timestamp_column": timestamp_column,
        "timestamp_scale_to_s": timestamp_scale_to_s,
        "timestamp_base": timestamp_base.isoformat() if isinstance(timestamp_base, datetime) else timestamp_base,
        "operating_mode_column": operating_mode_column,
        "arrival_delay_s": arrival_delay_s,
        "normalizer_mapping_is_explicit": True,
    }
    if format_metadata:
        binding_metadata.update(format_metadata)
    return {
        "schema_version": SCHEMA,
        "source_id": source_id,
        "source_path": str(source_path),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "format": format_name,
        "component_id": component_id,
        "origin": origin,
        "samples": samples,
        "operating_mode": operating_mode if operating_mode_column is None else None,
        "tabular_binding": binding_metadata,
        "policy": {
            "units_inferred": False,
            "pressure_basis_inferred": False,
            "operating_mode_inferred": False,
            "accident_fields_created": False,
            "frequency_inference_performed": False,
            "provider_release_created": False,
        },
    }


def load_csv_runtime_source(
    path: str | Path,
    *,
    source_id: str,
    component_id: str,
    timestamp_column: str,
    bindings: Mapping[str, Mapping[str, Any]],
    normalizer: TelemetryNormalizer,
    operating_mode_column: str | None = None,
    operating_mode: str | None = None,
    origin: str = "historian_measured",
    delimiter: str = ",",
    encoding: str = "utf-8-sig",
    arrival_delay_s: float = 0.0,
    timestamp_scale_to_s: float = 1.0,
    timestamp_base: str | datetime | None = None,
    ambient_pressure_pa: float | None = None,
) -> dict[str, Any]:
    """Load one explicit CSV/TSV state stream as a runtime source mapping.

    ``timestamp_column`` contains numeric source time. If a site export uses
    an epoch or milliseconds, the caller must supply the corresponding
    ``timestamp_scale_to_s`` explicitly. At least one of
    ``operating_mode_column`` or ``operating_mode`` is required because HAZOP
    selection must not guess the operating mode from signals.
    """

    source_path = Path(path)
    if not source_path.is_file():
        raise TabularRuntimeAdapterError(f"CSV source does not exist: {source_path}")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise TabularRuntimeAdapterError("delimiter must be one character")
    with source_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        headers = reader.fieldnames or []
        if timestamp_column not in headers:
            raise TabularRuntimeAdapterError(
                f"CSV header is missing timestamp column {timestamp_column}"
            )
        if operating_mode_column and operating_mode_column not in headers:
            raise TabularRuntimeAdapterError(
                f"CSV header is missing operating-mode column {operating_mode_column}"
            )
        rows = list(reader)
    return _build_runtime_source_from_rows(
        source_path,
        source_id=source_id,
        component_id=component_id,
        timestamp_column=timestamp_column,
        bindings=bindings,
        normalizer=normalizer,
        rows=rows,
        operating_mode_column=operating_mode_column,
        operating_mode=operating_mode,
        origin=origin,
        arrival_delay_s=arrival_delay_s,
        timestamp_scale_to_s=timestamp_scale_to_s,
        timestamp_base=timestamp_base,
        ambient_pressure_pa=ambient_pressure_pa,
        format_name="csv" if delimiter == "," else "delimited",
        format_metadata={"delimiter": delimiter},
    )


def load_xlsx_runtime_source(
    path: str | Path,
    *,
    source_id: str,
    component_id: str,
    timestamp_column: str,
    bindings: Mapping[str, Mapping[str, Any]],
    normalizer: TelemetryNormalizer,
    operating_mode_column: str | None = None,
    operating_mode: str | None = None,
    origin: str = "historian_measured",
    sheet: str | None = None,
    sheet_index: int = 0,
    arrival_delay_s: float = 0.0,
    timestamp_scale_to_s: float = 1.0,
    timestamp_base: str | datetime | None = None,
    ambient_pressure_pa: float | None = None,
) -> dict[str, Any]:
    """Load one explicit XLSX state stream using the same strict row contract.

    ``openpyxl`` is intentionally optional.  A workbook is accepted only when
    the caller identifies the sheet and binds every signal, unit, timestamp,
    and operating-mode field explicitly; no header or sheet is guessed.
    """
    source_path = Path(path)
    if not source_path.is_file():
        raise TabularRuntimeAdapterError(f"XLSX source does not exist: {source_path}")
    try:
        import openpyxl
    except ImportError as error:
        raise TabularRuntimeAdapterError(
            "XLSX input requires openpyxl; install it in the runtime used by the connector"
        ) from error
    if not isinstance(sheet_index, int) or sheet_index < 0:
        raise TabularRuntimeAdapterError("sheet_index must be a non-negative integer")
    workbook = openpyxl.load_workbook(source_path, read_only=True, data_only=True)
    try:
        if sheet is None:
            if sheet_index >= len(workbook.worksheets):
                raise TabularRuntimeAdapterError(
                    f"sheet_index {sheet_index} is outside workbook sheet count {len(workbook.worksheets)}"
                )
            worksheet = workbook.worksheets[sheet_index]
        else:
            sheet = _name(sheet, "sheet")
            if sheet not in workbook.sheetnames:
                raise TabularRuntimeAdapterError(f"workbook does not contain sheet {sheet}")
            worksheet = workbook[sheet]
        iterator = worksheet.iter_rows(values_only=True)
        header = next(iterator, None)
        if not header:
            raise TabularRuntimeAdapterError("XLSX sheet has no header row")
        headers = [str(value).strip() if value is not None else "" for value in header]
        if any(not value for value in headers):
            raise TabularRuntimeAdapterError("XLSX header contains an empty column name")
        if len(set(headers)) != len(headers):
            raise TabularRuntimeAdapterError("XLSX header contains duplicate column names")
        rows = [dict(zip(headers, row)) for row in iterator]
    finally:
        workbook.close()
    return _build_runtime_source_from_rows(
        source_path,
        source_id=source_id,
        component_id=component_id,
        timestamp_column=timestamp_column,
        bindings=bindings,
        normalizer=normalizer,
        rows=rows,
        operating_mode_column=operating_mode_column,
        operating_mode=operating_mode,
        origin=origin,
        arrival_delay_s=arrival_delay_s,
        timestamp_scale_to_s=timestamp_scale_to_s,
        timestamp_base=timestamp_base,
        ambient_pressure_pa=ambient_pressure_pa,
        format_name="xlsx",
        format_metadata={"sheet": sheet, "sheet_index": sheet_index},
    )


def build_runtime_frames_from_csv(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Load one CSV source and select its latest state runtime frame."""

    source = load_csv_runtime_source(path, **kwargs)
    return build_observed_state_runtime_frames([source])


def build_runtime_frames_from_xlsx(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Load one XLSX source and select its latest state runtime frame."""

    source = load_xlsx_runtime_source(path, **kwargs)
    return build_observed_state_runtime_frames([source])


__all__ = [
    "TabularRuntimeAdapterError",
    "build_runtime_frames_from_csv",
    "build_runtime_frames_from_xlsx",
    "load_csv_runtime_source",
    "load_xlsx_runtime_source",
]

