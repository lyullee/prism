"""Convert explicit provider release packets into PRISM request templates.

The command only performs contract validation and context attachment.  It does
not run a provider solver, assign frequency, or infer a missing accident.
Mixed gas/liquid catalogs should be split when their source operator or
termination basis differs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_release import (
    PROVIDER_RELEASE_SCHEMA,
    ProviderReleaseContractError,
    build_consequence_request_from_provider_release,
    load_provider_release_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-release-catalog", type=Path, required=True)
    parser.add_argument(
        "--request-defaults",
        type=Path,
        required=True,
        help="JSON context with weather, ignition, domain, clock, operator and termination",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        releases = load_provider_release_catalog(args.provider_release_catalog)
        defaults = json.loads(args.request_defaults.read_text(encoding="utf-8"))
        if not isinstance(defaults, dict):
            raise ProviderReleaseContractError("request defaults must be a JSON object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProviderReleaseContractError) as error:
        raise SystemExit(f"provider request catalog input error: {error}") from error

    templates = []
    uncomputed = []
    for index, release in enumerate(releases):
        try:
            request = build_consequence_request_from_provider_release(release, defaults)
        except ProviderReleaseContractError as error:
            uncomputed.append({
                "index": index,
                "event_id": release.event_id,
                "component_id": release.component_id,
                "reason": str(error),
            })
            continue
        templates.append(request.model_dump(mode="json"))

    report = {
        "schema_version": "prism.provider_request_catalog.v1",
        "provider_release_schema": PROVIDER_RELEASE_SCHEMA,
        "templates": templates,
        "uncomputed": uncomputed,
        "promotion_policy": {
            "frequency_is_not_assigned": True,
            "missing_context_is_uncomputed": True,
            "two_sided_release_sets_require_dedicated_adapter": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    status = "COMPILED" if not uncomputed else "PARTIAL_PROVIDER_REQUEST_CATALOG"
    print(json.dumps({
        "status": status,
        "output": str(args.output),
        "provider_release_count": len(releases),
        "template_count": len(templates),
        "uncomputed_count": len(uncomputed),
        "frequency_assigned": False,
    }, ensure_ascii=False))
    return 0 if not uncomputed else 2


if __name__ == "__main__":
    raise SystemExit(main())
