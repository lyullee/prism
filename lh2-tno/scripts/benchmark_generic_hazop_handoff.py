#!/usr/bin/env python3
"""Benchmark the generic current/forecast HAZOP handoff.

This measures the state-frame -> operating-mode -> HAZOP selection -> evidence
coverage path.  It deliberately does not run an equipment provider, SLABx-LH2,
ignition, or facility IR/F-N calculation; therefore the result is timing
evidence for the orchestration seam and never a fresh-physics real-time claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

from run_generic_facility_hazop_handoff import build_handoff  # noqa: E402


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], quantile: float) -> float:
    """Return a conservative nearest-rank percentile."""
    if not values:
        raise ValueError("values must be non-empty")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * (len(ordered) - 1))))
    return ordered[index]


def benchmark(
    frames_path: Path,
    tables_path: Path,
    current_frames_path: Path,
    current_attachments_path: Path,
    forecast_attachments_path: Path,
    repetitions: int = 10,
    warmup: int = 1,
) -> dict[str, Any]:
    if isinstance(repetitions, bool) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if isinstance(warmup, bool) or warmup < 0:
        raise ValueError("warmup must be a nonnegative integer")

    frames = _load(frames_path)
    tables = _load(tables_path)
    current_frames = _load(current_frames_path)
    current_attachments = _load(current_attachments_path)
    forecast_attachments = _load(forecast_attachments_path)

    for _ in range(warmup):
        build_handoff(frames, tables, current_frames, current_attachments, forecast_attachments)

    elapsed_ms: list[float] = []
    result: dict[str, Any] | None = None
    for _ in range(repetitions):
        started = time.perf_counter()
        result = build_handoff(
            frames,
            tables,
            current_frames,
            current_attachments,
            forecast_attachments,
        )
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)

    assert result is not None
    current_summary = result["current_evidence_coverage"]["summary"]
    forecast_summary = result["forecast_evidence_coverage"]["summary"]
    values = sorted(elapsed_ms)
    return {
        "schema_version": "prism.generic_hazop_handoff_timing.v1",
        "facility_id": result["facility_id"],
        "component_count": len(result["component_ids"]),
        "operating_modes": result["operating_modes"],
        "current_request_count": current_summary["request_count"],
        "forecast_request_count": forecast_summary["request_count"],
        "current_evidence_complete_count": current_summary["evidence_complete_count"],
        "forecast_evidence_complete_count": forecast_summary["evidence_complete_count"],
        "repetitions": repetitions,
        "warmup": warmup,
        "elapsed_ms_values": elapsed_ms,
        "min_ms": min(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values),
        "input_sha256": {
            "frames": _digest(frames_path),
            "tables": _digest(tables_path),
            "current_frames": _digest(current_frames_path),
            "current_attachments": _digest(current_attachments_path),
            "forecast_attachments": _digest(forecast_attachments_path),
        },
        "measurement": {
            "clock": "time.perf_counter",
            "unit": "ms",
            "scope": "state frames -> operating mode -> HAZOP selection -> four-block evidence coverage",
            "same_process_repeated_calls": True,
            "provider_release_physics_included": False,
            "slabx_lh2_physics_included": False,
            "ignition_damage_physics_included": False,
            "facility_ir_fn_included": False,
        },
        "policy": {
            "fresh_physics_realtime_claim": False,
            "one_hz_service_level_claim": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Timing covers orchestration and exact evidence lookup only. It must not be "
            "used as a fresh provider/SLABx-LH2 or facility-QRA latency guarantee."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--tables", type=Path, required=True)
    parser.add_argument("--current-frames", type=Path, required=True)
    parser.add_argument("--current-attachments", type=Path, required=True)
    parser.add_argument("--forecast-attachments", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = benchmark(
        args.frames,
        args.tables,
        args.current_frames,
        args.current_attachments,
        args.forecast_attachments,
        args.repetitions,
        args.warmup,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "p95_ms": result["p95_ms"], "p99_ms": result["p99_ms"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
