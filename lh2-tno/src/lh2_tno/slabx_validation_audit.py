"""Audit the external SLABx-LH2 consequence-model evidence.

The SLABx-LH2 project contains independent comparisons against cryogenic
hydrogen and dense-gas validation data.  This module records the evidence in a
portable, digest-bound ledger while keeping its scope below the facility-QRA
promotion gate: it cannot create an equipment release packet, assign a
frequency, or validate ignition and F-N calculations.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


SLABX_VALIDATION_SCHEMA = "prism.slabx_lh2_validation_audit.v1"


class SlabxValidationAuditError(ValueError):
    """Raised when a SLABx-LH2 evidence ledger is malformed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise SlabxValidationAuditError(f"cannot read SLABx evidence file: {path}") from error
    return digest.hexdigest()


def _load_object(path: str | Path) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).resolve()
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SlabxValidationAuditError(f"invalid SLABx evidence JSON: {resolved}") from error
    if not isinstance(value, dict):
        raise SlabxValidationAuditError(f"SLABx evidence must be an object: {resolved}")
    return resolved, value


def _source_files(
    *,
    results_path: Path,
    audit_path: Path,
    source_root: str | Path | None,
    relative_source_paths: Iterable[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    files: list[dict[str, Any]] = []
    blockers: list[str] = []
    files.append({"role": "model_results", "path": str(results_path), "sha256": _sha256(results_path)})
    files.append({"role": "reproducibility_audit", "path": str(audit_path), "sha256": _sha256(audit_path)})
    if source_root is None:
        if tuple(relative_source_paths):
            blockers.append("relative SLABx source paths require --source-root")
        return files, blockers
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise SlabxValidationAuditError(f"SLABx source root is missing: {root}")
    for relative in relative_source_paths:
        if not isinstance(relative, str) or not relative.strip():
            raise SlabxValidationAuditError("SLABx source paths must be nonempty strings")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise SlabxValidationAuditError(f"SLABx source path escapes source root: {relative}") from error
        if not path.is_file():
            blockers.append(f"missing SLABx source file: {relative}")
            continue
        files.append({"role": "source_manifest", "relative_path": relative, "sha256": _sha256(path)})
    return files, blockers


def audit_slabx_lh2_validation_evidence(
    results_path: str | Path,
    audit_path: str | Path,
    *,
    source_root: str | Path | None = None,
    relative_source_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a restricted, digest-bound SLABx-LH2 evidence report.

    The external results and audit are treated as evidence, never as PRISM
    accident inputs.  A ``RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE`` status
    means the required component-level checks are internally consistent; it
    deliberately leaves all facility-QRA claims false.
    """
    results_file, results = _load_object(results_path)
    audit_file, audit = _load_object(audit_path)
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    def check(name: str, passed: bool, evidence: Mapping[str, Any], reason: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "BLOCKED", "evidence": dict(evidence)})
        if not passed:
            blockers.append(reason)

    check(
        "model_identity",
        isinstance(results.get("slabx_lh2_version"), str)
        and isinstance(results.get("slabx_version"), str)
        and bool(results.get("slabx_lh2_version"))
        and bool(results.get("slabx_version")),
        {"slabx_lh2_version": results.get("slabx_lh2_version"), "slabx_version": results.get("slabx_version")},
        "SLABx-LH2 result does not declare model versions",
    )
    audit_checks = audit.get("checks")
    def _audit_check_passed(name: str, value: Any) -> bool:
        if name == "passed":
            return value is True
        if isinstance(value, bool):
            return value is True
        # The external reproducibility ledger uses positive counts for checks
        # such as ``dynamic_tests_passed`` and ``quasi_steady_tests_passed``.
        return name.endswith("_passed") and isinstance(value, (int, float)) and value > 0

    audit_checks_are_true = (
        isinstance(audit_checks, Mapping)
        and bool(audit_checks)
        and all(_audit_check_passed(str(name), value) for name, value in audit_checks.items())
    )
    audit_passed = audit.get("passed") is True or (
        isinstance(audit_checks, Mapping) and audit_checks.get("passed") is True
    )
    check(
        "reproducibility_audit",
        audit_passed and audit_checks_are_true,
        {
            "passed": audit.get("passed", audit_checks.get("passed") if isinstance(audit_checks, Mapping) else None),
            "check_count": len(audit_checks) if isinstance(audit_checks, Mapping) else None,
            "dynamic_tests_passed": audit_checks.get("dynamic_tests_passed") if isinstance(audit_checks, Mapping) else None,
            "quasi_steady_tests_passed": audit_checks.get("quasi_steady_tests_passed") if isinstance(audit_checks, Mapping) else None,
        },
        "SLABx reproducibility audit is incomplete or contains a failed check",
    )
    ffi = results.get("ffi")
    flacs = results.get("flacs_comparison", {}).get("rows") if isinstance(results.get("flacs_comparison"), Mapping) else None
    check(
        "dispersion_comparison_coverage",
        isinstance(ffi, Mapping)
        and len(ffi) >= 6
        and isinstance(flacs, list)
        and len(flacs) >= 6
        and results.get("measurements_installed") is True,
        {
            "ffi_case_count": len(ffi) if isinstance(ffi, Mapping) else None,
            "flacs_comparison_row_count": len(flacs) if isinstance(flacs, list) else None,
            "measurements_installed": results.get("measurements_installed"),
            "lfl_in_bracket": results.get("lfl_in_bracket"),
        },
        "SLABx dispersion comparison coverage is missing or not measurement-backed",
    )
    pool_radius = results.get("pool_radius")
    negative_pool = results.get("negative_control_lng_pool")
    check(
        "pool_and_negative_control",
        isinstance(pool_radius, Mapping)
        and isinstance(pool_radius.get("median_ratio"), (int, float))
        and 0.5 <= float(pool_radius["median_ratio"]) <= 1.5
        and isinstance(negative_pool, Mapping)
        and negative_pool.get("max_change_pct") == 0.0,
        {
            "pool_radius_case_count": len(pool_radius) - 1 if isinstance(pool_radius, Mapping) else None,
            "pool_radius_median_ratio": pool_radius.get("median_ratio") if isinstance(pool_radius, Mapping) else None,
            "negative_control_max_change_pct": negative_pool.get("max_change_pct") if isinstance(negative_pool, Mapping) else None,
        },
        "SLABx pool comparison or negative-control closure is missing",
    )
    audit_metrics = audit.get("metrics") if isinstance(audit.get("metrics"), Mapping) else {}
    check(
        "mass_and_runtime_ledger",
        isinstance(audit_metrics, Mapping)
        and isinstance(audit_metrics.get("max_scenario_mass_residual_kg"), (int, float))
        and abs(float(audit_metrics["max_scenario_mass_residual_kg"])) <= 1.0e-8
        and isinstance(audit_metrics.get("runtime_repeat_inventory_difference_kg"), (int, float))
        and abs(float(audit_metrics["runtime_repeat_inventory_difference_kg"])) <= 1.0e-8,
        {
            "max_scenario_mass_residual_kg": audit_metrics.get("max_scenario_mass_residual_kg"),
            "runtime_repeat_inventory_difference_kg": audit_metrics.get("runtime_repeat_inventory_difference_kg"),
            "runtime_three_repeats": audit_checks.get("runtime_three_repeats") if isinstance(audit_checks, Mapping) else None,
        },
        "SLABx mass closure or repeatability ledger is missing",
    )

    source_files, source_blockers = _source_files(
        results_path=results_file,
        audit_path=audit_file,
        source_root=source_root,
        relative_source_paths=relative_source_paths,
    )
    blockers.extend(source_blockers)
    return {
        "schema_version": SLABX_VALIDATION_SCHEMA,
        "status": (
            "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE"
            if not blockers
            else "BLOCKED_SLABX_LH2_CONSEQUENCE_EVIDENCE"
        ),
        "model": {
            "name": "SLABx-LH2",
            "slabx_lh2_version": results.get("slabx_lh2_version"),
            "slabx_version": results.get("slabx_version"),
        },
        "scope": {
            "supports": [
                "cryogenic-hydrogen pool radius and evaporation comparison",
                "outdoor hydrogen dispersion/LFL comparison under declared applicability",
                "inventory mass-closure and repeat-runtime evidence from the external model",
            ],
            "excludes": [
                "equipment accident release or provider qualification",
                "initiating-event frequency or sensor frequency learning",
                "ignition, fire, explosion, blast, IR/F-N, or facility-QRA validation",
                "indoor, detonation/DDT, obstacle/terrain cases outside the declared SLABx applicability",
            ],
        },
        "source_files": source_files,
        "source_results": {
            "path": str(results_file),
            "sha256": _sha256(results_file),
            "generated_utc": results.get("generated_utc"),
        },
        "source_audit": {"path": str(audit_file), "sha256": _sha256(audit_file)},
        "checks": checks,
        "metrics": {
            "ffi_case_count": len(ffi) if isinstance(ffi, Mapping) else 0,
            "flacs_comparison_row_count": len(flacs) if isinstance(flacs, list) else 0,
            "pool_radius_median_ratio": pool_radius.get("median_ratio") if isinstance(pool_radius, Mapping) else None,
            "lfl_in_bracket": results.get("lfl_in_bracket"),
            "max_scenario_mass_residual_kg": audit_metrics.get("max_scenario_mass_residual_kg"),
            "runtime_repeat_inventory_difference_kg": audit_metrics.get("runtime_repeat_inventory_difference_kg"),
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "promotion_policy": {
            "component_evidence_only": True,
            "external_model_is_not_provider_packet": True,
            "frequency_is_not_inferred": True,
            "facility_qra_requires_independent_full_chain_validation": True,
        },
    }


__all__ = [
    "SLABX_VALIDATION_SCHEMA",
    "SlabxValidationAuditError",
    "audit_slabx_lh2_validation_evidence",
]
