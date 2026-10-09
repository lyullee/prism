#!/usr/bin/env python3
"""Measure one fresh consequence update and repeated exact-cache updates.

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

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
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
) -> dict:
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
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
    return {
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = benchmark(args.manifest, args.campaign, args.backend_config, args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cache_hits": result["cache_hits"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
