#!/usr/bin/env python3
"""Score future commissioning or literature observations against predictions.

The input format is intentionally independent of the consequence models so
that measured values remain immutable evidence. Model output is joined by
test_id and written into the predicted column before this scorer is run.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


COLUMNS = [
    "test_id", "qoi", "measured", "predicted", "unit",
    "measurement_std", "model_low", "model_high", "source",
    "condition_note",
]


@dataclass(frozen=True)
class Observation:
    test_id: str
    qoi: str
    measured: float
    predicted: float
    unit: str
    measurement_std: float | None = None
    model_low: float | None = None
    model_high: float | None = None
    source: str = ""
    condition_note: str = ""


@dataclass(frozen=True)
class Metrics:
    n: int
    mean_bias: float
    normalized_mean_bias: float
    mae: float
    rmse: float
    normalized_rmse: float
    mean_absolute_percentage_error: float
    geometric_mean_bias: float
    fraction_within_factor_two: float
    model_envelope_coverage: float | None


def _optional_number(row: dict, name: str, line: int) -> float | None:
    raw = str(row.get(name, "")).strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"row {line} {name} is not a number: {raw!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"row {line} {name} must be finite")
    return value


def read_observations(path) -> list[Observation]:
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = [name for name in COLUMNS if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("missing columns: " + ", ".join(missing))
        observations = []
        seen_keys: set[tuple[str, str]] = set()
        units_by_qoi: dict[str, str] = {}
        for line, row in enumerate(reader, start=2):
            test_id = str(row["test_id"]).strip()
            qoi = str(row["qoi"]).strip()
            unit = str(row["unit"]).strip()
            if not test_id or not qoi or not unit:
                raise ValueError(f"row {line} needs test_id, qoi, and unit")
            key = (test_id, qoi)
            if key in seen_keys:
                raise ValueError(
                    f"row {line} duplicates test_id/qoi {key!r}")
            seen_keys.add(key)
            prior_unit = units_by_qoi.setdefault(qoi, unit)
            if unit != prior_unit:
                raise ValueError(
                    f"row {line} mixes units for qoi {qoi!r}: "
                    f"{prior_unit!r} and {unit!r}")
            measured = _optional_number(row, "measured", line)
            predicted = _optional_number(row, "predicted", line)
            if measured is None or measured <= 0.0:
                raise ValueError(f"row {line} measured must be positive")
            if predicted is None or predicted < 0.0:
                raise ValueError(f"row {line} predicted must be non-negative")
            std = _optional_number(row, "measurement_std", line)
            low = _optional_number(row, "model_low", line)
            high = _optional_number(row, "model_high", line)
            if std is not None and std < 0.0:
                raise ValueError(f"row {line} measurement_std must be non-negative")
            if (low is None) != (high is None):
                raise ValueError(f"row {line} needs both model_low and model_high")
            if low is not None and not 0.0 <= low <= high:
                raise ValueError(f"row {line} model bounds are reversed")
            observations.append(Observation(
                test_id, qoi, measured, predicted, unit, std, low, high,
                str(row.get("source", "")).strip(),
                str(row.get("condition_note", "")).strip()))
    if not observations:
        raise ValueError("observation file contains no data rows")
    return observations


def metrics(observations: list[Observation]) -> Metrics:
    if not observations:
        raise ValueError("at least one observation is required")
    measured = [o.measured for o in observations]
    predicted = [o.predicted for o in observations]
    errors = [p - m for p, m in zip(predicted, measured)]
    mean_measured = sum(measured) / len(measured)
    pairs = list(zip(predicted, measured))
    envelopes = [o for o in observations
                 if o.model_low is not None and o.model_high is not None]
    envelope_coverage = None
    if envelopes:
        envelope_coverage = sum(
            o.model_low <= o.measured <= o.model_high for o in envelopes
        ) / len(envelopes)
    return Metrics(
        n=len(observations),
        mean_bias=sum(errors) / len(errors),
        normalized_mean_bias=(sum(errors) / len(errors)) / mean_measured,
        mae=sum(abs(e) for e in errors) / len(errors),
        rmse=math.sqrt(sum(e * e for e in errors) / len(errors)),
        normalized_rmse=(math.sqrt(sum(e * e for e in errors)
                                   / len(errors)) / mean_measured),
        mean_absolute_percentage_error=(
            sum(abs(p - m) / m for p, m in zip(predicted, measured))
            / len(measured)),
        geometric_mean_bias=(
            math.exp(sum(math.log(p / m) for p, m in pairs)
                     / len(pairs)) if all(p > 0.0 for p in predicted)
            else 0.0),
        fraction_within_factor_two=(
            sum(0.5 <= p / m <= 2.0 for p, m in pairs)
            / len(pairs)),
        model_envelope_coverage=envelope_coverage)


def evaluate(path) -> dict:
    observations = read_observations(path)
    groups: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        groups[observation.qoi].append(observation)
    return {
        "source": str(path),
        "n_observations": len(observations),
        "metrics_by_qoi": {
            qoi: asdict(metrics(rows)) for qoi, rows in sorted(groups.items())
        },
        "interpretation": (
            "Metrics describe agreement only for the supplied observations. "
            "They do not establish applicability outside their joint input "
            "range. Model-envelope coverage is non-probabilistic."),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("observations")
    parser.add_argument("--out", default="validation_summary.json")
    args = parser.parse_args(argv)
    payload = evaluate(args.observations)
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.out}: {payload['n_observations']} observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
