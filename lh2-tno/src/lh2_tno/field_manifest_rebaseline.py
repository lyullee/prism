"""Explicitly rebaseline a field-evidence manifest to its current files.

Field bundles are kept outside the PRISM repository.  A source export can be
copied or regenerated after a manifest was created, which leaves an otherwise
usable comparison in ``HASH_DRIFT``.  This helper records that the manifest
hashes were deliberately replaced with the bytes that are present now.  It
does not make the source independent, does not create a provider release
packet, and cannot open a physical-validation or frequency gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .external_field_evidence import REQUIRED_CHANNELS


REBASELINE_SCHEMA = "prism.external_field_manifest_rebaseline.v1"


class FieldManifestRebaselineError(ValueError):
    """Raised when a field manifest cannot be rebaselined safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise FieldManifestRebaselineError(f"cannot read field channel: {path}") from error
    return digest.hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FieldManifestRebaselineError(f"invalid field manifest: {path}") from error
    if not isinstance(value, Mapping):
        raise FieldManifestRebaselineError("field manifest must be an object")
    return dict(value)


def _nested_manifest(wrapper: Mapping[str, Any]) -> dict[str, Any]:
    if wrapper.get("schema") == "degali.field-evidence-manifest.v1":
        return dict(wrapper)
    if wrapper.get("schema") == "degali.field-evidence-manifest-execution.v1":
        nested = wrapper.get("field_evidence_manifest")
        if not isinstance(nested, Mapping):
            raise FieldManifestRebaselineError(
                "execution wrapper has no field_evidence_manifest object"
            )
        return dict(nested)
    raise FieldManifestRebaselineError("unsupported field manifest schema")


def rebaseline_field_manifest(
    manifest_path: str | Path,
    *,
    acknowledged: bool = False,
    manifest_id: str | None = None,
) -> dict[str, Any]:
    """Return a copy of ``manifest_path`` with current channel hashes.

    ``acknowledged`` is intentionally required so callers cannot silently
    erase provenance drift.  The returned wrapper keeps the original declared
    hashes in ``rebaseline.previous_channel_sha256`` and records that no
    independent review or promotion was performed.
    """
    if not acknowledged:
        raise FieldManifestRebaselineError(
            "explicit acknowledgement is required to rebaseline source hashes"
        )
    source_path = Path(manifest_path).resolve()
    wrapper = _read(source_path)
    manifest = _nested_manifest(wrapper)
    if manifest.get("scope") != "lh2_free_field":
        raise FieldManifestRebaselineError("only an outdoor lh2_free_field manifest is accepted")
    if manifest.get("promotion_allowed") is not False:
        raise FieldManifestRebaselineError("manifest must keep promotion_allowed=false")
    readiness = manifest.get("evidence_readiness")
    if not isinstance(readiness, Mapping) or readiness.get("promotion_allowed") is not False:
        raise FieldManifestRebaselineError(
            "manifest evidence_readiness must keep promotion_allowed=false"
        )
    rows = manifest.get("channel_artifacts")
    if not isinstance(rows, list):
        raise FieldManifestRebaselineError("channel_artifacts must be a list")
    by_channel: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise FieldManifestRebaselineError(f"channel_artifacts[{index}] must be an object")
        channel = raw.get("channel")
        path_value = raw.get("path")
        declared = raw.get("sha256")
        if not isinstance(channel, str) or channel in by_channel:
            raise FieldManifestRebaselineError(f"invalid or duplicate channel at index {index}")
        if not isinstance(path_value, str) or not path_value:
            raise FieldManifestRebaselineError(f"channel_artifacts[{index}].path is invalid")
        if not isinstance(declared, str) or len(declared) != 64:
            raise FieldManifestRebaselineError(f"channel_artifacts[{index}].sha256 is invalid")
        by_channel[channel] = {
            "channel": channel,
            "path": path_value,
            "sha256": declared,
        }
    missing = sorted(set(REQUIRED_CHANNELS) - set(by_channel))
    if missing:
        raise FieldManifestRebaselineError(
            "manifest is missing required channels: " + ", ".join(missing)
        )

    previous = {channel: by_channel[channel]["sha256"] for channel in REQUIRED_CHANNELS}
    observed: dict[str, str] = {}
    updated_rows: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        channel = str(row["channel"])
        file_path = Path(str(row["path"])).resolve()
        if not file_path.is_file():
            raise FieldManifestRebaselineError(
                f"field channel file is missing: {channel}: {file_path}"
            )
        actual = _sha256(file_path)
        observed[channel] = actual
        row["sha256"] = actual
        updated_rows.append(row)

    if manifest_id is not None:
        if not manifest_id.strip():
            raise FieldManifestRebaselineError("manifest_id cannot be empty")
        new_id = manifest_id.strip()
    else:
        old_id = str(manifest.get("manifest_id") or "field-manifest")
        new_id = f"{old_id}-rebaselined"

    updated_manifest = copy.deepcopy(manifest)
    updated_manifest["manifest_id"] = new_id
    updated_manifest["channel_artifacts"] = updated_rows
    updated_manifest["rebaseline"] = {
        "schema_version": REBASELINE_SCHEMA,
        "status": "HASHES_REBASED_TO_CURRENT_FILES",
        "source_manifest_path": str(source_path),
        "source_manifest_sha256": _sha256(source_path),
        "previous_channel_sha256": previous,
        "current_channel_sha256": observed,
        "independent_reverification": False,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "promotion_allowed": False,
        "reason": "the external source files were retained and only their current bytes were rehashed",
    }
    updated_readiness = dict(readiness)
    updated_readiness["gate_codes"] = sorted(
        set(updated_readiness.get("gate_codes", []))
        | {"manifest_hashes_rebaselined_current_files", "manifest_not_promoted"}
    )
    updated_manifest["evidence_readiness"] = updated_readiness
    updated_manifest["promotion_allowed"] = False

    return {
        "schema": "degali.field-evidence-manifest-execution.v1",
        "input": {
            "audit_root": updated_manifest.get("audit_root"),
            "source_manifest_path": str(source_path),
        },
        "field_evidence_manifest": updated_manifest,
        "rebaseline": updated_manifest["rebaseline"],
    }


__all__ = [
    "FieldManifestRebaselineError",
    "REBASELINE_SCHEMA",
    "rebaseline_field_manifest",
]
