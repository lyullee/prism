"""Audit historical provider-like JSON without promoting it to a packet.

Older PRISM development folders contain release-shaped synthetic outputs.  A
missing ``provider_export_schema`` is a material provenance gap, so this
module reports it explicitly instead of adding the field or passing the file
to the current provider loader.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .provider_release import (
    ProviderReleaseContractError,
    load_provider_emergency_relief,
    load_provider_release,
)


LEGACY_AUDIT_SCHEMA = "prism.legacy_provider_artifact_audit.v1"


def _iter_objects(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_objects(child)


def _json_paths(root: Path) -> list[Path]:
    excluded = {".git", "__pycache__", "build", "dist", "node_modules"}
    return sorted(
        path for path in root.rglob("*.json")
        if not any(part in excluded or part.startswith(".venv") for part in path.parts)
    )


def audit_legacy_provider_artifacts(root: str | Path) -> dict[str, Any]:
    """Return a non-promoting audit of release-shaped historical JSON.

    A candidate is an object with an explicit accident event and the minimum
    provider clock fields.  Current-schema candidates are strict-validated for
    diagnostics, while schema-less candidates remain legacy and are never
    modified.  The result is evidence, not a release catalog.
    """
    root = Path(root)
    files_scanned = 0
    invalid_json = 0
    candidates: list[dict[str, Any]] = []
    strict_failures: list[dict[str, str]] = []
    missing_fields: Counter[str] = Counter()
    qualified = 0

    for path in _json_paths(root):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            invalid_json += 1
            continue
        files_scanned += 1
        for obj in _iter_objects(value):
            event_kind = obj.get("event_kind")
            if event_kind not in {"accidental_leak", "emergency_relief"}:
                continue
            required = ["steps", "duration_s"]
            if event_kind == "accidental_leak":
                required.insert(0, "failure_opening_diameter_m")
            if any(field not in obj for field in required):
                continue
            relative = str(path.relative_to(root))
            entry = {
                "file": relative,
                "event_id": obj.get("event_id"),
                "component_id": obj.get("component_id"),
                "event_kind": event_kind,
                "provider_export_schema": obj.get("provider_export_schema"),
            }
            if "provider_export_schema" not in obj:
                missing_fields["provider_export_schema"] += 1
                entry["status"] = "LEGACY_MISSING_SCHEMA"
                candidates.append(entry)
                continue
            try:
                if event_kind == "emergency_relief":
                    load_provider_emergency_relief(obj)
                else:
                    load_provider_release(obj)
            except (ProviderReleaseContractError, ValueError, TypeError) as error:
                entry["status"] = "CURRENT_SCHEMA_STRICT_FAILURE"
                entry["error"] = str(error)
                strict_failures.append({"file": relative, "error": str(error)})
            else:
                entry["status"] = "CURRENT_SCHEMA_QUALIFIED"
                qualified += 1
            candidates.append(entry)

    legacy_count = sum(item["status"] == "LEGACY_MISSING_SCHEMA" for item in candidates)
    if not candidates:
        status = "NO_RELEASE_SHAPED_ARTIFACTS"
    elif legacy_count:
        status = "LEGACY_OUTPUT_REQUIRES_EXPLICIT_SCHEMA_MIGRATION"
    else:
        status = "CURRENT_SCHEMA_ARTIFACTS_AUDITED"
    return {
        "schema": LEGACY_AUDIT_SCHEMA,
        "status": status,
        "root": str(root),
        "files_scanned": files_scanned,
        "invalid_json_files": invalid_json,
        "release_shaped_candidate_count": len(candidates),
        "legacy_missing_schema_count": legacy_count,
        "qualified_current_schema_count": qualified,
        "strict_validation_failure_count": len(strict_failures),
        "missing_field_counts": dict(missing_fields),
        "strict_validation_failures": strict_failures,
        "candidates": candidates,
        "promotion_policy": {
            "schema_is_never_added": True,
            "legacy_output_is_not_a_facility_provider_packet": True,
            "facility_ir_fn_allowed": False,
        },
    }
