"""Overlay exact reviewed-isolation packets onto campaign evidence.

The overlay is deliberately a packet-selection operation, not a qualification
operation.  Each selected packet must match the declared event and component;
the caller may also require an exact accident port.  Provider promotion,
frequency assignment, physical validation, and facility-QRA promotion remain
false in the returned evidence record.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.provider_release import (  # noqa: E402
    ResolvedGasRelease,
    ResolvedGasReleaseSet,
    ResolvedLiquidRelease,
    load_provider_emergency_relief,
    load_provider_release,
    load_provider_release_set,
)


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _path(raw: str, root: Path) -> Path:
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else root / candidate


def _load_release(path: Path) -> Any:
    raw = _object(path)
    if raw.get("provider_export_schema") == "prism.resolved_release_set.v1":
        return load_provider_release_set(path)
    if raw.get("event_kind") == "emergency_relief":
        return load_provider_emergency_relief(path)
    return load_provider_release(path)


def _ports(release: Any) -> list[str]:
    if isinstance(release, ResolvedGasReleaseSet):
        return [str(item.port_id) for item in release.releases]
    if isinstance(release, (ResolvedGasRelease, ResolvedLiquidRelease)):
        return [str(release.port_id)]
    raise ValueError("unsupported provider release type")


def _event_id(release: Any) -> str:
    return str(release.event_id)


def build_overlay(
    base: dict[str, Any],
    mapping: dict[str, Any],
    *,
    packet_root: Path,
    base_packet_root: Path | None = None,
) -> dict[str, Any]:
    rows = base.get("rows")
    if not isinstance(rows, list):
        raise ValueError("base evidence rows must be an array")
    selected = mapping.get("mappings")
    if not isinstance(selected, list) or not selected:
        raise ValueError("overlay mappings must be a non-empty array")

    by_event = {
        row.get("event_id"): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("event_id"), str)
    }
    output_rows = [json.loads(json.dumps(row, ensure_ascii=False)) for row in rows]
    output_by_event = {row.get("event_id"): row for row in output_rows}
    if base_packet_root is not None:
        for row in output_rows:
            evidence = row.get("evidence") if isinstance(row, dict) else None
            paths = evidence.get("resolved_packet_paths") if isinstance(evidence, dict) else None
            if not isinstance(paths, list):
                continue
            evidence["resolved_packet_paths"] = [
                str((base_packet_root / path).as_posix())
                if isinstance(path, str) and not Path(path).is_absolute()
                else path
                for path in paths
            ]
    rebound: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(selected):
        if not isinstance(item, dict):
            raise ValueError(f"mappings[{index}] must be an object")
        event_id = item.get("event_id")
        packet = item.get("resolved_packet_path")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError(f"mappings[{index}] requires event_id")
        if event_id in seen:
            raise ValueError(f"duplicate overlay event_id: {event_id}")
        seen.add(event_id)
        current = by_event.get(event_id)
        if current is None:
            raise ValueError(f"overlay event is absent from base evidence: {event_id}")
        if not isinstance(packet, str) or not packet:
            raise ValueError(f"mappings[{index}] requires resolved_packet_path")
        packet_path = _path(packet, packet_root)
        if not packet_path.exists():
            raise FileNotFoundError(packet_path)
        release = _load_release(packet_path)
        if _event_id(release) != event_id:
            raise ValueError(f"packet event_id disagrees with overlay: {event_id}")
        component_id = str(current.get("component_id") or "")
        if str(release.component_id) != component_id:
            raise ValueError(f"packet component_id disagrees with overlay: {event_id}")
        expected_port = item.get("expected_port_id")
        ports = _ports(release)
        if expected_port is not None and str(expected_port) not in ports:
            raise ValueError(f"packet port_id disagrees with overlay: {event_id}")
        row = output_by_event[event_id]
        evidence = row.setdefault("evidence", {})
        if not isinstance(evidence, dict):
            raise ValueError(f"base evidence row has invalid evidence object: {event_id}")
        evidence.update(
            {
                "exact_opening_match": True,
                "strict_packet_valid": True,
                "resolved_packet_paths": [packet],
                "overlay_type": "reviewed_isolation_success_diagnostic",
                "overlay_provider_termination_basis": str(
                    getattr(release, "termination_basis", "")
                ),
                "overlay_provider_port_ids": ports,
            }
        )
        rebound.append(
            {
                "event_id": event_id,
                "component_id": component_id,
                "resolved_packet_path": packet,
                "provider_result_digest": str(release.provider_result_digest),
                "termination_basis": str(release.termination_basis),
                "port_ids": ports,
            }
        )

    result = json.loads(json.dumps(base, ensure_ascii=False))
    result["rows"] = output_rows
    result["status"] = "CUSTOM_ISOLATION_PACKET_OVERLAY_DIAGNOSTIC"
    result["overlay"] = {
        "schema_version": "prism.isolation_packet_evidence_overlay.v1",
        "selected_count": len(rebound),
        "rows": rebound,
        "qualified_provider_packet_count": 0,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "interpretation": (
            "Exact reviewed-isolation packets are selected for diagnostic replay. "
            "The overlay does not infer frequency, promote provider evidence, or "
            "close the facility QRA."
        ),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-evidence", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--base-packet-root",
        type=Path,
        help="Optional root to prefix non-overlay packet paths inherited from the base evidence.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_overlay(
            _object(args.base_evidence),
            _object(args.overlay),
            packet_root=args.packet_root,
            base_packet_root=args.base_packet_root,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"isolation packet overlay input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "overlay_count": result["overlay"]["selected_count"],
                "output": str(args.output),
                "promotion": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
