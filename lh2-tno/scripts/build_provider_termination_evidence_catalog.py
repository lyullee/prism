"""Build the provider-owned termination evidence catalog used by release audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_termination_evidence_catalog import (  # noqa: E402
    build_provider_termination_evidence_catalog,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-catalog-dir", type=Path)
    parser.add_argument("--inventory-provider-responses", type=Path)
    parser.add_argument("--inventory-resolved-releases", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--inventory-source-event-prefix",
        default="equipment-inventory-campaign/",
    )
    parser.add_argument(
        "--inventory-target-event-prefix",
        default="generic-lh2-full-scope-example/inventory-depletion/inventory-depletion/",
    )
    args = parser.parse_args()
    try:
        provider_responses = (
            _object(args.inventory_provider_responses)
            if args.inventory_provider_responses
            else None
        )
        resolved_releases = (
            _object(args.inventory_resolved_releases)
            if args.inventory_resolved_releases
            else None
        )
        report = build_provider_termination_evidence_catalog(
            storage_catalog_dir=args.storage_catalog_dir,
            inventory_provider_responses=provider_responses,
            inventory_resolved_releases=resolved_releases,
            inventory_source_paths={
                "provider_responses": str(args.inventory_provider_responses)
                if args.inventory_provider_responses
                else "",
                "resolved_releases": str(args.inventory_resolved_releases)
                if args.inventory_resolved_releases
                else "",
            },
            inventory_source_event_prefix=args.inventory_source_event_prefix,
            inventory_target_event_prefix=args.inventory_target_event_prefix,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"provider termination evidence input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "row_count": report["row_count"],
        "event_count": report["event_count"],
        "error_count": len(report["errors"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] in {"EVIDENCE_CATALOG_READY", "EVIDENCE_CATALOG_PARTIAL"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
