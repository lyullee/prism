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
    source_id = _name(source_id, "source_id")
    component_id = _name(component_id, "component_id")
    timestamp_column = _name(timestamp_column, "timestamp_column")
    if origin not in _ORIGINS:
        raise TabularRuntimeAdapterError(f"unsupported origin: {origin}")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise TabularRuntimeAdapterError("delimiter must be one character")
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

    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
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
    if not rows:
        raise TabularRuntimeAdapterError("CSV source contains no data rows")

    samples: list[dict[str, Any]] = []
    previous_time: float | None = None
    for index, row in enumerate(rows, start=2):
        raw_time = row.get(timestamp_column)
        source_time_s = _finite(raw_time, f"row {index}.{timestamp_column}") * timestamp_scale_to_s
        if source_time_s < 0.0:
            raise TabularRuntimeAdapterError(f"row {index} source time must be non-negative")
        if previous_time is not None and source_time_s <= previous_time:
            raise TabularRuntimeAdapterError(
                f"CSV source times must be strictly increasing at row {index}"
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

    return {
        "schema_version": SCHEMA,
        "source_id": source_id,
        "source_path": str(source_path),
        "source_sha256": digest,
        "format": "csv" if delimiter == "," else "delimited",
        "component_id": component_id,
        "origin": origin,
        "samples": samples,
        "operating_mode": operating_mode if operating_mode_column is None else None,
        "tabular_binding": {
            "timestamp_column": timestamp_column,
            "timestamp_scale_to_s": timestamp_scale_to_s,
            "operating_mode_column": operating_mode_column,
            "delimiter": delimiter,
            "arrival_delay_s": arrival_delay_s,
            "normalizer_mapping_is_explicit": True,
        },
        "policy": {
            "units_inferred": False,
            "pressure_basis_inferred": False,
            "operating_mode_inferred": False,
            "accident_fields_created": False,
            "frequency_inference_performed": False,
            "provider_release_created": False,
        },
    }


def build_runtime_frames_from_csv(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Load one CSV source and select its latest state runtime frame."""

    source = load_csv_runtime_source(path, **kwargs)
    return build_observed_state_runtime_frames([source])

