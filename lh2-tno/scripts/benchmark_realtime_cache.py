#!/usr/bin/env python3
"""Measure fresh, warm-worker, and repeated exact-cache consequence updates.

The benchmark intentionally reports the two modes separately.  A cache hit is
useful for a 1 Hz monitor when the normalized request is unchanged, but it does
not turn a fresh physics run into a real-time service guarantee.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import (  # noqa: E402
    BackendConfig,
    IsolatedBackend,
    PersistentIsolatedBackend,
    tree_digest,
)
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.consequences import ConsequenceRequest  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.service import ConsequenceService  # noqa: E402


def _backend_config(path: Path) -> BackendConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for package in raw.get("packages", []):
        package["sha256"] = tree_digest(Path(package["root"]))
    return BackendConfig.model_validate_json(json.dumps(raw, ensure_ascii=False))


def benchmark(
    manifest_path: Path,
    campaign_path: Path,
    backend_path: Path,
    repetitions: int = 20,
    persistent_fresh_repetitions: int = 0,
) -> dict:
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if (
        isinstance(persistent_fresh_repetitions, bool)
        or not isinstance(persistent_fresh_repetitions, int)
        or persistent_fresh_repetitions < 0
    ):
        raise ValueError("persistent_fresh_repetitions must be a nonnegative integer")
    manifest = EquipmentManifest.from_json(manifest_path)
    facility = manifest.to_facility()
    campaign = RiskCampaign.model_validate_json(campaign_path.read_text(encoding="utf-8"))
    routes = [route for route in campaign.event_routes if route.branches and route.branches[0].request]
    if not routes:
        raise ValueError("campaign has no physical request to benchmark")
    request = routes[0].branches[0].request
    assert request is not None
    backend = _backend_config(backend_path)
    service = ConsequenceService(
        ResearchPipeline(facility, IsolatedBackend(backend)), capacity=max(4, repetitions)
    )
    fresh = service.evaluate(request)
    cached = [service.evaluate(request) for _ in range(repetitions)]
    cache_ms = [float(row["service"]["service_elapsed_ms"]) for row in cached]
    cache_p95 = sorted(cache_ms)[int(0.95 * (len(cache_ms) - 1))]
    first_release = request.resolved_liquid_release or request.resolved_release
    result = {
        "schema_version": "prism.realtime_cache_benchmark.v1",
        "facility_id": facility.id,
        "request_event_id": first_release.event_id if first_release is not None else None,
        "fresh_physics_elapsed_ms": fresh["service"]["service_elapsed_ms"],
        "fresh_backend_elapsed_ms": fresh["service"]["physics_run_elapsed_ms"],
        "cache_elapsed_ms_values": cache_ms,
        "cache_median_ms": statistics.median(cache_ms),
        "cache_p95_ms": cache_p95,
        "cache_hits": sum(bool(row["service"]["exact_cache_hit"]) for row in cached),
        "one_hz_deadline_s": 1.0,
        "fresh_physics_meets_one_hz": fresh["service"]["service_elapsed_ms"] / 1000 <= 1.0,
        "cache_meets_one_hz_all_samples": all(value / 1000 <= 1.0 for value in cache_ms),
        "realtime_fresh_physics_claim": False,
        "interpretation": (
            "Exact cache samples meet a 1 Hz lookup deadline in this run; the fresh physics "
            "sample is measured separately and is not a 1 Hz service-level claim."
        ),
    }
    if persistent_fresh_repetitions:
        # Change a declared weather input on every call so the service cannot
        # answer from its exact-result cache.  The source packet, model pins,
        # and consequence settings remain unchanged.
        persistent_backend = PersistentIsolatedBackend(backend)
        try:
            persistent_service = ConsequenceService(
                ResearchPipeline(facility, persistent_backend),
                capacity=max(4, persistent_fresh_repetitions),
            )
            warm_rows = []
            for index in range(persistent_fresh_repetitions):
                weather = request.weather.model_copy(
                    update={
                        "wind_speed_m_s": request.weather.wind_speed_m_s
                        + (index + 1) * 0.1
                    }
                )
                changed_request = request.model_copy(update={"weather": weather})
                warm_rows.append(persistent_service.evaluate(changed_request))
        finally:
            persistent_backend.close()
        warm_ms = [float(row["service"]["service_elapsed_ms"]) for row in warm_rows]
        warm_backend_ms = [
            float(row["service"]["physics_run_elapsed_ms"]) for row in warm_rows
        ]
        steady_ms = warm_ms[1:] or warm_ms
        warm_p95 = sorted(steady_ms)[int(0.95 * (len(steady_ms) - 1))]
        result["persistent_fresh_physics"] = {
            "persistent_worker": True,
            "request_count": len(warm_rows),
            "startup_included_in_first_sample": True,
            "service_elapsed_ms_values": warm_ms,
            "backend_elapsed_ms_values": warm_backend_ms,
            "startup_elapsed_ms": warm_ms[0],
            "steady_elapsed_ms_values": steady_ms,
            "steady_p50_ms": statistics.median(steady_ms),
            "steady_median_ms": statistics.median(steady_ms),
            "steady_p95_ms": warm_p95,
            "steady_p99_ms": sorted(steady_ms)[int(0.99 * (len(steady_ms) - 1))],
            "fresh_physics_meets_one_hz": all(value <= 1000.0 for value in warm_ms),
            "steady_fresh_physics_meets_one_hz": all(
                value <= 1000.0 for value in (warm_ms[1:] or warm_ms)
            ),
            "realtime_fresh_physics_claim": False,
            "interpretation": (
                "A pinned worker session removes repeated interpreter startup and preserves "
                "fresh physics on changed weather inputs. This diagnostic does not qualify "
                "fresh-physics 1 Hz service unless every measured sample is within 1 s."
            ),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument(
        "--persistent-fresh-repetitions",
        type=int,
        default=0,
        help="optional changed-input fresh-physics samples through one pinned warm worker",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = benchmark(
        args.manifest,
        args.campaign,
        args.backend_config,
        args.repetitions,
        args.persistent_fresh_repetitions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cache_hits": result["cache_hits"],
                "persistent_fresh_samples": result.get("persistent_fresh_physics", {}).get(
                    "request_count", 0
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
