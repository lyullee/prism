"""Repeat the synthetic vertical-handoff campaign and report fresh timing quantiles.

This is a processing-time diagnostic, not a real-time qualification.  Each
repeat starts a new Python process and re-runs the provider-resolved campaign;
cache responses and a previously saved result are not used as the measured
physics path.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_vertical_vent.py"
OUT = ROOT / "results" / "20261009" / "vertical_vent_timing"


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * probability
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    fraction = index - low
    return ordered[low] + fraction * (ordered[high] - ordered[low])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 20:
        raise SystemExit("--repeats must be between 1 and 20")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    samples = []
    for repeat in range(args.repeats):
        started = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=ROOT, env=env,
            capture_output=True, text=True, check=False,
        )
        wall_ms = (time.perf_counter() - started) * 1000.0
        if completed.returncode != 0:
            raise RuntimeError(
                f"vertical diagnostic repeat {repeat + 1} failed:\n{completed.stderr}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"vertical diagnostic did not return JSON: {completed.stdout}") from exc
        samples.append({
            "repeat": repeat + 1,
            "reported_campaign_elapsed_ms": payload["timing"]["campaign_elapsed_ms"],
            "reported_case_median_ms": payload["timing"]["case_median_ms"],
            "wall_elapsed_ms": wall_ms,
            "executed_cases": payload["executed_cases"],
            "uncomputed_cases": payload["uncomputed_cases"],
            "status": payload["status"],
        })

    campaign = [x["reported_campaign_elapsed_ms"] for x in samples]
    wall = [x["wall_elapsed_ms"] for x in samples]
    result = {
        "benchmark": "vertical-vent-campaign",
        "repeat_count": args.repeats,
        "fresh_subprocess_each_repeat": True,
        "campaign_elapsed_ms": {
            "p50": quantile(campaign, .50),
            "p95": quantile(campaign, .95),
            "p99": quantile(campaign, .99),
            "samples": campaign,
        },
        "wall_elapsed_ms": {
            "p50": quantile(wall, .50),
            "p95": quantile(wall, .95),
            "p99": quantile(wall, .99),
            "samples": wall,
        },
        "samples": samples,
        "physical_validation_claim": False,
        "one_hz_demonstrated": False,
        "limitations": [
            "synthetic provider-resolved variable-state vertical handoff",
            "three repeats are an exploratory timing sample, not a production SLA",
            "external provider, hardware, grid and evaluation horizon remain fixed",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "benchmark.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
