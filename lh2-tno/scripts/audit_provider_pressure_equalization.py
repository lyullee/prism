"""Audit one resolved provider packet for a pressure-equalization candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.pressure_equalization import audit_provider_pressure_equalization  # noqa: E402


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _route_from_campaign(campaign: dict, event_id: str) -> dict:
    for route in campaign.get("event_routes", []):
        if isinstance(route, dict) and route.get("event_id") == event_id:
            branches = route.get("branches")
            if isinstance(branches, list) and branches:
                request = branches[0].get("request") if isinstance(branches[0], dict) else None
                if isinstance(request, dict) and isinstance(request.get("resolved_release"), dict):
                    release = dict(request["resolved_release"])
                    release["ambient_pressure_pa_abs"] = request.get("weather", {}).get(
                        "ambient_pressure_pa_abs", release.get("ambient_pressure_pa_abs", 101325.0)
                    )
                    # Campaign requests carry the mass ledger on the resolved
                    # release already; the fallback keeps this script useful
                    # for older campaign records that only retain it on the
                    # request envelope.
                    if "provider_mass_balance" not in release and isinstance(request.get("provider_mass_balance"), dict):
                        release["provider_mass_balance"] = request["provider_mass_balance"]
                    return release
    raise KeyError(f"event route not found or has no resolved_release: {event_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--resolved-release", type=Path)
    source.add_argument("--campaign", type=Path)
    parser.add_argument("--event-id")
    parser.add_argument("--minimum-zero-flow-intervals", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.campaign is not None and not args.event_id:
        parser.error("--event-id is required with --campaign")
    packet = (
        _load(args.resolved_release)
        if args.resolved_release is not None
        else _route_from_campaign(_load(args.campaign), args.event_id)
    )
    report = audit_provider_pressure_equalization(
        packet,
        minimum_zero_flow_intervals=args.minimum_zero_flow_intervals,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "event_id": report.get("event_id"),
        "candidate_termination": report.get("candidate_termination"),
        "blocking_reasons": report.get("blocking_reasons"),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
