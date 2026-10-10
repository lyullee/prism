"""Audit replay and source integrity for observed LH2 state evidence.

The audit is intentionally narrower than physical validation.  It verifies
that the source files named by an observed-state manifest still exist, have
the recorded bytes, and that a regenerated state-only evidence ledger is the
same as the reviewed ledger.  It never creates an accident release, assigns a
frequency, or qualifies a provider packet.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

from .observed_state_evidence import OBSERVED_STATE_EVIDENCE_SCHEMA


REPLAY_SCHEMA = "prism.observed_state_source_replay_audit.v1"
_MANIFEST_SCHEMA = "prism.observed_state_input_manifest.v1"
_HEX64 = set("0123456789abcdef")


def _load_object(value: Mapping[str, Any] | str | Path, name: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} must contain an object")
    return loaded


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relative_path(value: Any) -> str:
    return str(value).replace("\\", "/")


def audit_observed_state_replay(
    manifest: Mapping[str, Any] | str | Path,
    evidence: Mapping[str, Any] | str | Path,
    *,
    regenerated_evidence: Mapping[str, Any] | str | Path | None = None,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a fail-closed source replay audit.

    ``regenerated_evidence`` is optional so an existing ledger can first be
    checked for source integrity.  When supplied, it must be byte-equivalent
    at the canonical JSON level to the reviewed evidence ledger.
    """
    manifest_obj = _load_object(manifest, "manifest")
    evidence_obj = _load_object(evidence, "evidence")
    if manifest_obj.get("schema_version") != _MANIFEST_SCHEMA:
        raise ValueError(f"manifest schema_version must be {_MANIFEST_SCHEMA}")
    if evidence_obj.get("schema_version") != OBSERVED_STATE_EVIDENCE_SCHEMA:
        raise ValueError(
            f"evidence schema_version must be {OBSERVED_STATE_EVIDENCE_SCHEMA}"
        )
    sources = manifest_obj.get("sources")
    rows = evidence_obj.get("source_rows")
    if not isinstance(sources, list) or not sources:
        raise ValueError("manifest sources must be a non-empty list")
    if not isinstance(rows, list):
        raise ValueError("evidence source_rows must be a list")

    manifest_source_root = source_root
    if manifest_source_root is None:
        manifest_source_root = manifest_obj.get("source_root")
    root = Path(manifest_source_root) if manifest_source_root else None
    row_by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("evidence source_rows must contain objects")
        source_id = row.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("evidence source_rows require source_id")
        if source_id in row_by_id:
            raise ValueError(f"duplicate evidence source_id: {source_id}")
        row_by_id[source_id] = row

    source_results: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    manifest_ids: list[str] = []
    for spec in sources:
        if not isinstance(spec, Mapping):
            raise ValueError("manifest sources must contain objects")
        source_id = spec.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("manifest source_id must be a non-empty string")
        if source_id in manifest_ids:
            raise ValueError(f"duplicate manifest source_id: {source_id}")
        manifest_ids.append(source_id)
        relative = _relative_path(spec.get("path"))
        candidate = Path(str(spec.get("path", "")))
        if not candidate.is_absolute() and root is not None:
            candidate = root / candidate
        candidate = candidate.resolve()
        evidence_row = row_by_id.get(source_id)
        expected_sha = evidence_row.get("source_sha256") if evidence_row else None
        actual_sha = None
        exists = candidate.is_file()
        if exists:
            actual_sha = _sha256(candidate)
        hash_format_valid = isinstance(expected_sha, str) and len(expected_sha) == 64 and set(expected_sha.lower()) <= _HEX64
        hash_match = bool(exists and hash_format_valid and actual_sha == expected_sha.lower())
        row_match = bool(
            evidence_row
            and _relative_path(evidence_row.get("source_path")) == relative
            and evidence_row.get("component_id") == spec.get("component_id")
            and evidence_row.get("origin") == spec.get("origin", "historian_measured")
        )
        if not exists:
            blocking_reasons.append(f"{source_id}: source file is missing: {candidate}")
        elif not hash_format_valid:
            blocking_reasons.append(f"{source_id}: evidence source_sha256 is not a SHA-256 digest")
        elif not hash_match:
            blocking_reasons.append(f"{source_id}: source SHA-256 does not match evidence")
        if evidence_row is None:
            blocking_reasons.append(f"{source_id}: evidence row is missing")
        elif not row_match:
            blocking_reasons.append(f"{source_id}: manifest and evidence metadata do not match")
        source_results.append(
            {
                "source_id": source_id,
                "relative_path": relative,
                "resolved_path": str(candidate),
                "component_id": spec.get("component_id"),
                "exists": exists,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "sha256_match": hash_match,
                "manifest_evidence_metadata_match": row_match,
                "evidence_sample_count": evidence_row.get("sample_count") if evidence_row else None,
                "evidence_snapshot_digest_set_sha256": (
                    evidence_row.get("snapshot_digest_set_sha256") if evidence_row else None
                ),
            }
        )

    extra_ids = sorted(set(row_by_id) - set(manifest_ids))
    if extra_ids:
        blocking_reasons.append(f"evidence contains unlisted source IDs: {extra_ids}")

    evidence_policy = evidence_obj.get("policy")
    policy_ok = (
        isinstance(evidence_policy, Mapping)
        and evidence_policy.get("state_only") is True
        and evidence_policy.get("release_scenario_generated") is False
        and evidence_policy.get("frequency_inference_performed") is False
        and evidence_policy.get("sensor_frequency_learning_used") is False
        and evidence_policy.get("provider_packet_promoted") is False
        and evidence_policy.get("physical_validation_claim") is False
        and evidence_policy.get("facility_qra_claim") is False
        and evidence_policy.get("diagnostic_only") is True
    )
    if not policy_ok:
        blocking_reasons.append("evidence policy is not state-only diagnostic policy")

    regeneration = {
        "performed": regenerated_evidence is not None,
        "canonical_digest_match": None,
        "reviewed_canonical_digest": _canonical_digest(evidence_obj),
        "regenerated_canonical_digest": None,
    }
    if regenerated_evidence is not None:
        regenerated_obj = _load_object(regenerated_evidence, "regenerated_evidence")
        regeneration["regenerated_canonical_digest"] = _canonical_digest(regenerated_obj)
        regeneration["canonical_digest_match"] = (
            regeneration["reviewed_canonical_digest"]
            == regeneration["regenerated_canonical_digest"]
        )
        if regeneration["canonical_digest_match"] is not True:
            blocking_reasons.append("regenerated evidence does not match reviewed evidence")

    status = "SOURCE_REPLAY_MATCHED" if not blocking_reasons else "SOURCE_REPLAY_BLOCKED"
    return {
        "schema_version": REPLAY_SCHEMA,
        "status": status,
        "source_count": len(sources),
        "matched_source_count": sum(
            1
            for row in source_results
            if row["sha256_match"] and row["manifest_evidence_metadata_match"]
        ),
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "source_rows": source_results,
        "evidence_policy_valid": policy_ok,
        "regeneration": regeneration,
        "promotion_policy": {
            "state_only": True,
            "release_scenario_generated": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "The source files and normalized state ledger are reproducible and hash-consistent. "
            "This is input-integrity evidence only; it does not qualify an accident release, "
            "assign a frequency, or promote facility IR/F-N."
        ),
    }


__all__ = ["REPLAY_SCHEMA", "audit_observed_state_replay"]
