"""Audit the external DynamicLH2PoolX physical-evidence record.

The external DynamicLH2PoolX workspace contains useful component evidence for
LH2 pool source terms.  It is deliberately kept separate from PRISM's
equipment-release and facility-QRA gates: a restricted spreading or heat
transfer comparison does not validate an accident release, atmospheric
dispersion, ignition, or IR/F-N result.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "prism.dynamiclh2poolx_evidence_audit.v1"
ACCEPTED_DECISION = "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE"


class DynamicLH2PoolXEvidenceAuditError(ValueError):
    """Raised when a DynamicLH2PoolX evidence record is malformed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise DynamicLH2PoolXEvidenceAuditError(f"cannot read evidence file: {path}") from error
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise DynamicLH2PoolXEvidenceAuditError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DynamicLH2PoolXEvidenceAuditError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise DynamicLH2PoolXEvidenceAuditError(f"{label} must be a JSON object: {path}")
    return value


def _path(root: Path, relative: str | Path | None, default: str) -> Path:
    value = Path(relative) if relative is not None else Path(default)
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def _csv_summary(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise DynamicLH2PoolXEvidenceAuditError(f"{label} is missing: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = list(reader.fieldnames or [])
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise DynamicLH2PoolXEvidenceAuditError(f"cannot read {label}: {path}") from error
    return {"path": str(path), "sha256": _sha256(path), "row_count": len(rows), "fields": fields}


def _source(path: Path, role: str) -> dict[str, Any]:
    return {"role": role, "path": str(path), "sha256": _sha256(path)}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def audit_dynamiclh2poolx_evidence(
    source_root: str | Path,
    *,
    stage_evidence_path: str | Path | None = None,
    stage_protocol_path: str | Path | None = None,
    source_manifest_path: str | Path | None = None,
    dynamic_validation_protocol_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a digest-bound, fail-closed audit of DynamicLH2PoolX evidence.

    ``source_root`` is the external DynamicLH2PoolX workspace.  All claims in
    the returned object remain component-scoped.  Hash drift is retained as an
    explicit provenance condition rather than silently treated as a clean
    validation replay.
    """
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise DynamicLH2PoolXEvidenceAuditError(f"source root is missing: {root}")

    stage_file = _path(root, stage_evidence_path, "data/stage_c_evidence.json")
    protocol_file = _path(root, stage_protocol_path, "data/stage_c_protocol.json")
    manifest_file = _path(root, source_manifest_path, "data/source_manifest.json")
    validation_protocol_file = _path(
        root, dynamic_validation_protocol_path, "data/dynamic_validation_protocol.json"
    )
    stage = _read_json(stage_file, "Stage-C evidence")
    protocol = _read_json(protocol_file, "Stage-C protocol")
    source_manifest = _read_json(manifest_file, "source manifest")
    validation_protocol = _read_json(validation_protocol_file, "dynamic validation protocol")

    implementation_files = {
        "dynamic_pool_py": root / "src" / "dynamiclh2poolx" / "dynamic_pool.py",
        "spreading_py": root / "src" / "dynamiclh2poolx" / "spreading.py",
    }
    observation_files = {
        "juel3155_radius_observations": root / "data" / "juel3155_radius_observations.csv",
        "hse_rr985_test6_radius": root / "data" / "hse_rr985_test6_radius.csv",
    }
    for label, path in {**implementation_files, **observation_files}.items():
        if not path.is_file():
            raise DynamicLH2PoolXEvidenceAuditError(f"required {label} file is missing: {path}")

    provenance = _mapping(stage.get("provenance"))
    current_hashes = {
        "protocol_sha256": _sha256(protocol_file),
        "source_manifest_sha256": _sha256(manifest_file),
        "dynamic_pool_py_sha256": _sha256(implementation_files["dynamic_pool_py"]),
        "spreading_py_sha256": _sha256(implementation_files["spreading_py"]),
    }
    hash_comparisons = {
        key: {
            "declared": provenance.get(key),
            "current": value,
            "matches": provenance.get(key) == value,
        }
        for key, value in current_hashes.items()
    }
    hash_mismatch_count = sum(not row["matches"] for row in hash_comparisons.values())

    component_checks = _mapping(stage.get("component_checks"))
    component_checks_complete = bool(component_checks) and all(
        value is True for value in component_checks.values()
    )
    decision_ok = stage.get("decision") == ACCEPTED_DECISION
    # Stage-C evidence is governed by the Stage-C protocol.  The broader
    # dynamic-validation protocol is a parent/release protocol with its own
    # identifier, so it must be present but is not expected to have the same
    # ID as the Stage-C protocol.
    protocol_ids_match = (
        stage.get("protocol_id") == protocol.get("protocol_id")
        and bool(validation_protocol.get("protocol_id"))
    )

    juel = _csv_summary(observation_files["juel3155_radius_observations"], "JUEL radius observations")
    hse = _csv_summary(observation_files["hse_rr985_test6_radius"], "HSE Test 6 radius observations")
    c2 = _mapping(stage.get("c2_juel_holdout"))
    holdout_trials = c2.get("holdout_trials") if isinstance(c2.get("holdout_trials"), list) else []
    calibration_trials = c2.get("calibration_trials") if isinstance(c2.get("calibration_trials"), list) else []
    holdout_rows = sum(
        int(_mapping(c2.get(key)).get("n", 0) or 0)
        for key in ("water_trial_4", "aluminium_trial_6")
    )
    holdout_is_disjoint = not set(holdout_trials).intersection(calibration_trials)
    c3 = _mapping(stage.get("c3_hse_test6"))

    blockers: list[str] = []
    if not decision_ok:
        blockers.append("Stage-C decision is not the accepted restricted component-scope decision")
    if not component_checks_complete:
        blockers.append("Stage-C component checks are incomplete or not all true")
    if not protocol_ids_match:
        blockers.append("Stage-C protocol identifiers are inconsistent")
    if not holdout_is_disjoint:
        blockers.append("calibration and holdout trials overlap")

    if blockers:
        status = "BLOCKED_DYNAMICLH2POOLX_EVIDENCE"
    elif hash_mismatch_count:
        status = "RESTRICTED_COMPONENT_EVIDENCE_CURRENT_SOURCE_REPLAY_WITH_EXTERNAL_EVIDENCE_DRIFT"
    else:
        status = "RESTRICTED_COMPONENT_EVIDENCE"

    sources = [
        _source(stage_file, "Stage-C evidence decision and metrics"),
        _source(protocol_file, "Stage-C protocol"),
        _source(validation_protocol_file, "dynamic validation protocol"),
        _source(manifest_file, "source manifest"),
        *(_source(path, role) for role, path in implementation_files.items()),
        *(_source(path, role) for role, path in observation_files.items()),
    ]
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "source_root": str(root),
        "decision": stage.get("decision"),
        "provenance_status": (
            "CURRENT_SOURCE_REPLAY_WITH_EXTERNAL_EVIDENCE_DRIFT"
            if hash_mismatch_count
            else "CURRENT_SOURCE_REPLAY_MATCHES_DECLARED_EVIDENCE"
        ),
        "sources": sources,
        "hash_comparisons": hash_comparisons,
        "hash_mismatch_count": hash_mismatch_count,
        "protocol": {
            "stage_protocol_id": stage.get("protocol_id"),
            "stage_protocol_file_id": protocol.get("protocol_id"),
            "dynamic_validation_protocol_id": validation_protocol.get("protocol_id"),
            "identifiers_match": protocol_ids_match,
        },
        "component_checks": dict(component_checks),
        "observations": {
            "juel3155_radius_observations": juel,
            "hse_rr985_test6_radius": hse,
            "calibration_trials": calibration_trials,
            "holdout_trials": holdout_trials,
            "holdout_row_count": holdout_rows,
            "holdout_is_disjoint": holdout_is_disjoint,
        },
        "metrics": {
            "c0_relative_unledgered_residual": _mapping(stage.get("c0")).get(
                "relative_unledgered_residual"
            ),
            "c1_spatial_liquid_mass_relative_change": _mapping(
                _mapping(stage.get("c1")).get("spatial_refinement")
            ).get("liquid_mass_relative_change"),
            "c1_spatial_cumulative_evaporation_relative_change": _mapping(
                _mapping(stage.get("c1")).get("spatial_refinement")
            ).get("cumulative_evaporation_relative_change"),
            "water_trial_4_radius_rmse_m": _mapping(c2.get("water_trial_4")).get("rmse_m"),
            "aluminium_trial_6_radius_rmse_m": _mapping(c2.get("aluminium_trial_6")).get(
                "rmse_m"
            ),
            "water_trial_4_video_band_coverage": _mapping(c2.get("water_trial_4")).get(
                "video_band_coverage"
            ),
            "aluminium_trial_6_video_band_coverage": _mapping(c2.get("aluminium_trial_6")).get(
                "video_band_coverage"
            ),
            "hse_test6_end_of_release_radius_m": c3.get("end_of_release_radius_m"),
            "hse_test6_trajectory_rmse_m_diagnostic_only": c3.get(
                "trajectory_rmse_m_diagnostic_only"
            ),
            "hse_test6_max_absolute_unledgered_residual_kg": c3.get(
                "maximum_absolute_unledgered_residual_kg"
            ),
        },
        "scope": {
            "supports": [
                "declared ground-reaching LH2 inflow",
                "horizontal unconfined smooth-axisymmetric pool source terms",
                "restricted spreading holdout radius and mass-ledger checks",
                "numerical convergence and conservation checks",
            ],
            "excludes": [
                "jet impact, breakup, and deposition fraction",
                "asymmetric spreading and detached liquid pieces",
                "sloped terrain, drainage, barriers, buildings, or complex geometry",
                "atmospheric concentration or LFL-distance validation",
                "equipment accident release, isolation, and inventory depletion",
                "ignition, fire, explosion, IR/F-N, and facility-QRA validation",
            ],
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "claims": {
            "restricted_component_evidence": not bool(blockers),
            "independent_physical_validation_claim": False,
            "full_chain_validation_claim": False,
            "accident_release_validation_claim": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
        },
        "promotion_policy": {
            "hash_drift_is_retained_as_provenance_status": True,
            "component_evidence_is_not_accident_release_validation": True,
            "component_evidence_is_not_atmospheric_dispersion_validation": True,
            "component_evidence_is_not_facility_qra_validation": True,
            "frequency_is_not_inferred_from_physical_observations": True,
            "no_implicit_accident_substitution": True,
        },
        "required_next_evidence": [
            "reviewed source-term observations matched to an explicit PRISM equipment release packet",
            "independent downstream dispersion comparison with declared geometry and clock",
            "facility-level ignition, population, IR/F-N, and accident-family validation",
        ],
    }


__all__ = [
    "ACCEPTED_DECISION",
    "AUDIT_SCHEMA",
    "DynamicLH2PoolXEvidenceAuditError",
    "audit_dynamiclh2poolx_evidence",
]
