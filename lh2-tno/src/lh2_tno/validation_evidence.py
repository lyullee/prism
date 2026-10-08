"""Evidence ledger for restricted, component-level LH2 physics validation.

The PRISM facility chain must not turn a component benchmark into a claim that
the complete source-to-risk model is validated.  This module reads the
DynamicLH2PoolX Stage-C evidence package, verifies the referenced local files
and hashes, and emits a portable record with the restricted scope made
explicit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from .contracts import Contract, Name, Positive


class ValidationEvidenceRecord(Contract):
    schema_version: Literal["1.0"] = "1.0"
    evidence_id: Name
    component: Literal["dynamiclh2poolx"]
    decision: Literal["PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE"]
    scope: Name
    source_evidence_path: Name
    source_evidence_sha256: str = Field(min_length=64, max_length=64, pattern=r"[0-9a-f]{64}")
    verified_files: dict[str, str]
    provenance_status: Literal["VERIFIED", "DECLARED_EVIDENCE_WITH_SOURCE_HASH_DRIFT"]
    hash_mismatches: tuple[str, ...] = ()
    metrics: dict[str, Positive]
    excluded_claims: tuple[Name, ...]
    physical_validation_claim: Literal[False] = False
    full_chain_validation_claim: Literal[False] = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _required_hash(root: Path, relative: str, expected: str) -> str:
    path = root / relative
    if not path.is_file():
        raise ValueError(f"validation evidence file is missing: {relative}")
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"validation evidence hash mismatch: {relative}")
    return actual


def build_restricted_pool_record(
    evidence_path: str | Path,
    source_root: str | Path,
    *,
    allow_provenance_drift: bool = False,
) -> ValidationEvidenceRecord:
    """Verify the external Stage-C evidence package and return a PRISM record.

    The expected package is the DynamicLH2PoolX review tree.  The function
    checks the two declared hold-out radius metrics, the evidence decision,
    the protocol/source manifests, and the two source files used by the
    component model.  Strict mode rejects source-tree drift.  Audit mode can
    preserve a drift record, but it still keeps the resulting validation
    claims false for the complete PRISM facility chain.
    """
    evidence_file = Path(evidence_path).resolve()
    root = Path(source_root).resolve()
    if not evidence_file.is_file():
        raise ValueError(f"validation evidence JSON is missing: {evidence_file}")
    raw = json.loads(evidence_file.read_text(encoding="utf-8"))
    if raw.get("decision") != "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE":
        raise ValueError("only the restricted Stage-C component decision is accepted")
    if raw.get("schema_version") != "1.0":
        raise ValueError("unsupported validation evidence schema")
    c2 = raw.get("c2_juel_holdout", {})
    water = c2.get("water_trial_4", {})
    aluminium = c2.get("aluminium_trial_6", {})
    c3 = raw.get("c3_hse_test6", {})
    metrics = {
        "water_trial_4_radius_rmse_m": float(water.get("rmse_m", 0.0)),
        "water_trial_4_video_band_coverage": float(water.get("video_band_coverage", 0.0)),
        "aluminium_trial_6_radius_rmse_m": float(aluminium.get("rmse_m", 0.0)),
        "aluminium_trial_6_video_band_coverage": float(aluminium.get("video_band_coverage", 0.0)),
        "hse_test6_max_absolute_unledgered_residual_kg": float(
            c3.get("maximum_absolute_unledgered_residual_kg", 0.0)
        ),
    }
    if not 0.0 < metrics["water_trial_4_radius_rmse_m"] <= 0.15:
        raise ValueError("water hold-out radius RMSE is outside the declared gate")
    if not 0.0 < metrics["aluminium_trial_6_radius_rmse_m"] <= 0.15:
        raise ValueError("aluminium hold-out radius RMSE is outside the declared gate")
    if metrics["water_trial_4_video_band_coverage"] < 0.9 or metrics["aluminium_trial_6_video_band_coverage"] < 0.9:
        raise ValueError("hold-out video coverage is below the declared gate")
    if metrics["hse_test6_max_absolute_unledgered_residual_kg"] > 1.0e-9:
        raise ValueError("HSE evidence mass residual is outside the ledger gate")

    provenance = raw.get("provenance", {})
    verified_files: dict[str, str] = {}
    hash_mismatches: list[str] = []
    for relative, expected in {
        "data/dynamic_validation_protocol.json": provenance.get("protocol_sha256"),
        "data/source_manifest.json": provenance.get("source_manifest_sha256"),
        "src/dynamiclh2poolx/dynamic_pool.py": provenance.get("dynamic_pool_py_sha256"),
        "src/dynamiclh2poolx/spreading.py": provenance.get("spreading_py_sha256"),
    }.items():
        if not isinstance(expected, str):
            raise ValueError(f"missing declared hash for {relative}")
        try:
            verified_files[relative] = _required_hash(root, relative, expected)
        except ValueError:
            if not allow_provenance_drift:
                raise
            path = root / relative
            if not path.is_file():
                raise
            verified_files[relative] = _sha256(path)
            hash_mismatches.append(relative)
    observations = raw.get("provenance", {}).get("source_observations", [])
    if not isinstance(observations, list) or not observations:
        raise ValueError("validation evidence must declare source observations")
    for relative in observations:
        if not isinstance(relative, str):
            raise ValueError("source observation paths must be strings")
        path = root / relative
        if not path.is_file():
            raise ValueError(f"validation source observation is missing: {relative}")
        verified_files[relative] = _sha256(path)

    excluded = tuple(str(item) for item in raw.get("excluded_claims", []) if item)
    if not excluded:
        raise ValueError("validation evidence must declare excluded claims")
    return ValidationEvidenceRecord(
        evidence_id="dynamiclh2poolx-stage-c-restricted-20260911",
        component="dynamiclh2poolx",
        decision=raw["decision"],
        scope="declared ground-reaching inflow; horizontal unconfined smooth-axisymmetric pool source terms",
        source_evidence_path=str(evidence_file),
        source_evidence_sha256=_sha256(evidence_file),
        verified_files=verified_files,
        provenance_status=(
            "DECLARED_EVIDENCE_WITH_SOURCE_HASH_DRIFT"
            if hash_mismatches
            else "VERIFIED"
        ),
        hash_mismatches=tuple(hash_mismatches),
        metrics=metrics,
        excluded_claims=excluded,
    )
