"""Inventory external LH2 release artifacts without promoting QRA evidence.

External digital-twin workspaces contain useful release-shaped JSON files, but
those files are not automatically qualified provider packets.  This module
records the exact file digest, release identity and termination metadata while
requiring a separate ``prism.provider_qualification_evidence.v1`` sidecar
before any packet can be considered for PRISM promotion.  It never assigns a
frequency, infers an accident, or marks facility QRA as available.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .provider_release_closure import audit_provider_release_closure


SCHEMA = "prism.external_release_artifact_intake.v1"
RELEASE_SCHEMA = "prism.resolved_release.v1"
RELEASE_SET_SCHEMA = "prism.resolved_release_set.v1"
QUALIFICATION_SCHEMA = "prism.provider_qualification_evidence.v1"


class ExternalReleaseArtifactIntakeError(ValueError):
    """Raised when an intake request cannot be evaluated safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ExternalReleaseArtifactIntakeError(f"cannot read artifact: {path}") from error
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    raw = path.read_bytes()
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            last_error = error
    raise ExternalReleaseArtifactIntakeError(f"invalid JSON artifact: {path}") from last_error


def _contains_qualification(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("schema_version") == QUALIFICATION_SCHEMA:
            return True
        return any(_contains_qualification(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_qualification(item) for item in value)
    return False


def _release_like(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if value.get("provider_export_schema") in {RELEASE_SCHEMA, RELEASE_SET_SCHEMA}:
        return True
    required = {"event_id", "component_id", "port_id", "duration_s", "steps"}
    return required.issubset(value) and isinstance(value.get("steps"), list)


def _walk_releases(value: Any, pointer: str = "") -> list[tuple[str, Mapping[str, Any]]]:
    rows: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(value, Mapping):
        if _release_like(value):
            rows.append((pointer or "$", value))
            # A resolved-release row is a leaf for intake purposes.
            return rows
        for key, child in value.items():
            child_pointer = f"{pointer}.{key}" if pointer else f"$.{key}"
            rows.extend(_walk_releases(child, child_pointer))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_walk_releases(child, f"{pointer}[{index}]"))
    return rows


def _candidate_files(paths: Iterable[str | Path], roots: Iterable[str | Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for value in paths:
        path = Path(value).resolve()
        if path.is_file():
            found[str(path).casefold()] = path
    for value in roots:
        root = Path(value).resolve()
        if root.is_file():
            found[str(root).casefold()] = root
        elif root.is_dir():
            for path in root.rglob("*.json"):
                if "resolved_release" in path.name.casefold():
                    found[str(path).casefold()] = path
    return sorted(found.values(), key=lambda item: str(item).casefold())


def _digest_ok(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _nearby_qualification(
    path: Path,
    release: Mapping[str, Any],
) -> tuple[bool, list[str], bool, list[str]]:
    matches: list[str] = []
    exact_matches: list[str] = []
    mismatch_reasons: list[str] = []
    # Sidecars are deliberately searched only in the artifact directory and
    # one explicit parent.  A qualification record elsewhere must be supplied
    # and digest-bound by the provider packet audit instead of being guessed.
    candidates = set(path.parent.glob("*.json"))
    candidates.update(path.parent.parent.glob("*.json"))
    for candidate in sorted(candidates):
        if candidate == path:
            continue
        try:
            payload = _read_json(candidate)
            records: list[Mapping[str, Any]] = []
            def _collect(value: Any) -> None:
                if isinstance(value, Mapping):
                    if value.get("schema_version") == QUALIFICATION_SCHEMA:
                        records.append(value)
                    for child in value.values():
                        _collect(child)
                elif isinstance(value, list):
                    for child in value:
                        _collect(child)
            _collect(payload)
            if records:
                matches.append(str(candidate))
            for record in records:
                origins = record.get("provider_origin")
                if isinstance(origins, str):
                    origins = [origins]
                declared_ports = record.get("port_ids")
                if declared_ports is None and "port_id" in record:
                    declared_ports = [record.get("port_id")]
                declared_sources = record.get("provider_source_digests")
                if declared_sources is None and "provider_source_digest" in record:
                    declared_sources = [record.get("provider_source_digest")]
                declared_results = record.get("provider_result_digests")
                if declared_results is None and "provider_result_digest" in record:
                    declared_results = [record.get("provider_result_digest")]
                exact = (
                    record.get("status") == "qualified_actual"
                    and isinstance(origins, list)
                    and bool(origins)
                    and set(str(item) for item in origins).issubset(
                        {"native_provider", "reviewed_actual"}
                    )
                    and isinstance(record.get("evidence_id"), str)
                    and bool(record.get("evidence_id").strip())
                    and record.get("exact_digest_binding") is True
                    and record.get("event_id") == release.get("event_id")
                    and record.get("component_id") == release.get("component_id")
                    and declared_ports == [release.get("port_id")]
                    and _digest_ok(release.get("provider_source_digest"))
                    and _digest_ok(release.get("provider_result_digest"))
                    and declared_sources == [release.get("provider_source_digest")]
                    and declared_results == [release.get("provider_result_digest")]
                )
                if exact:
                    exact_matches.append(str(candidate))
                else:
                    mismatch_reasons.append(
                        f"qualification sidecar does not exactly match {candidate}"
                    )
        except ExternalReleaseArtifactIntakeError:
            continue
    return bool(matches), matches, bool(exact_matches), list(dict.fromkeys(mismatch_reasons))


def _closure_summary(release: Mapping[str, Any]) -> dict[str, Any]:
    """Run the strict closure audit without changing the provider payload."""

    if release.get("provider_export_schema") != RELEASE_SCHEMA:
        return {
            "status": "SCHEMA_UNQUALIFIED",
            "closure_ready": False,
            "blocking_reasons": [
                "provider_export_schema is not prism.resolved_release.v1"
            ],
            "facility_qra_allowed": False,
        }
    try:
        report = audit_provider_release_closure(dict(release))
    except (TypeError, ValueError) as error:
        return {
            "status": "CLOSURE_AUDIT_ERROR",
            "closure_ready": False,
            "blocking_reasons": [str(error)],
            "facility_qra_allowed": False,
        }
    gates = report.get("promotion_gates")
    gates = gates if isinstance(gates, Mapping) else {}
    reasons = report.get("blocking_reasons")
    return {
        "status": report.get("status"),
        "closure_ready": gates.get("closure_ready") is True,
        "closure_status_counts": dict(report.get("closure_status_counts", {})),
        "blocking_reasons": list(reasons) if isinstance(reasons, list) else [],
        "facility_qra_allowed": gates.get("facility_qra_allowed") is True,
    }


def audit_external_release_artifacts(
    paths: Iterable[str | Path] = (),
    roots: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Return a digest-bound inventory of release-shaped external JSON files."""

    files = _candidate_files(paths, roots)
    if not files:
        raise ExternalReleaseArtifactIntakeError(
            "at least one release artifact file or directory is required"
        )

    artifacts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            payload = _read_json(path)
            digest = _sha256(path)
        except ExternalReleaseArtifactIntakeError as error:
            errors.append({"path": str(path), "error": str(error)})
            continue
        releases = _walk_releases(payload)
        # The sidecar is checked against each release row, not merely detected
        # by filename.  Presence and exact digest-bound qualification are kept
        # separate so an invalid or unrelated sidecar cannot open promotion.
        if not releases:
            artifacts.append({
                "path": str(path),
                "sha256": digest,
                "release_count": 0,
                "qualification_sidecar_present": False,
                "qualification_sidecar_paths": [],
                "diagnostic_only": True,
                "blocking_reasons": ["no release-shaped record found"],
            })
            continue
        for pointer, release in releases:
            schema = release.get("provider_export_schema")
            shape_valid = all(
                isinstance(release.get(key), expected)
                for key, expected in (
                    ("event_id", str),
                    ("component_id", str),
                    ("port_id", str),
                    ("duration_s", (int, float)),
                    ("steps", list),
                )
            )
            origin = release.get("input_origin")
            (
                qualification_present,
                qualification_paths,
                qualification_bound,
                qualification_mismatch_reasons,
            ) = _nearby_qualification(path, release)
            qualification_bound = qualification_bound and schema == RELEASE_SCHEMA
            reasons: list[str] = []
            if not shape_valid:
                reasons.append("release identity or time-series fields are incomplete")
            if schema != RELEASE_SCHEMA:
                reasons.append("provider export schema is missing or not prism.resolved_release.v1")
            if origin in {"synthetic", "model_prediction", None}:
                reasons.append("input_origin is not a qualified observed/provider export")
            if not qualification_present:
                reasons.append("no nearby prism.provider_qualification_evidence.v1 sidecar")
            elif not qualification_bound:
                reasons.extend(qualification_mismatch_reasons)
            closure = _closure_summary(release)
            if closure.get("closure_ready") is not True:
                reasons.extend(str(item) for item in closure.get("blocking_reasons", []))
            artifacts.append({
                "path": str(path),
                "sha256": digest,
                "item_pointer": pointer,
                "provider_export_schema": schema,
                "event_id": release.get("event_id"),
                "component_id": release.get("component_id"),
                "port_id": release.get("port_id"),
                "input_origin": origin,
                "termination_basis": release.get("termination_basis"),
                "duration_s": release.get("duration_s"),
                "available_mass_kg": release.get("available_mass_kg"),
                "provider_source_digest": release.get("provider_source_digest"),
                "provider_result_digest": release.get("provider_result_digest"),
                "release_shape_valid": shape_valid,
                "qualification_sidecar_present": qualification_present,
                "qualification_sidecar_paths": qualification_paths,
                "qualification_bound": qualification_bound,
                "qualification_mismatch_reasons": qualification_mismatch_reasons,
                "closure_audit": closure,
                "diagnostic_only": True,
                "blocking_reasons": reasons,
            })

    release_rows = [row for row in artifacts if row.get("release_count", 1) > 0]
    qualified_rows = [row for row in release_rows if row.get("qualification_bound") is True]
    closure_ready_rows = [
        row for row in release_rows
        if isinstance(row.get("closure_audit"), Mapping)
        and row["closure_audit"].get("closure_ready") is True
    ]
    closure_status_counts: dict[str, int] = {}
    for row in release_rows:
        closure = row.get("closure_audit")
        status = closure.get("status") if isinstance(closure, Mapping) else "UNKNOWN"
        closure_status_counts[str(status)] = closure_status_counts.get(str(status), 0) + 1
    actual_origin_rows = [
        row for row in release_rows
        if row.get("input_origin") in {"observed", "measured", "qualified_actual", "provider_actual"}
    ]
    return {
        "schema_version": SCHEMA,
        "status": (
            "EXTERNAL_RELEASE_ARTIFACTS_REQUIRE_QUALIFICATION"
            if release_rows
            else "NO_RELEASE_SHAPED_EXTERNAL_ARTIFACTS"
        ),
        "diagnostic_only": True,
        "artifact_file_count": len(files),
        "release_row_count": len(release_rows),
        "qualified_sidecar_row_count": len(qualified_rows),
        "closure_ready_row_count": len(closure_ready_rows),
        "closure_status_counts": closure_status_counts,
        "actual_origin_row_count": len(actual_origin_rows),
        "synthetic_or_model_prediction_row_count": sum(
            1 for row in release_rows if row.get("input_origin") in {"synthetic", "model_prediction"}
        ),
        "error_count": len(errors),
        "artifacts": artifacts,
        "errors": errors,
        "promotion_policy": {
            "frequency_assigned": False,
            "provider_release_packet_promoted": False,
            "physical_validation_promoted": False,
            "facility_qra_promoted": False,
            "qualification_requires_exact_digest_bound_sidecar": True,
            "provider_ports_never_substituted_for_frequency_ports": True,
        },
        "blocking_reasons": [
            "external release artifacts are inventory evidence only until exact provider qualification is bound",
            "synthetic or model-prediction releases cannot establish field/actual accident coverage",
            "facility IR/F-N remains withheld while qualified provider packet coverage is incomplete",
        ] if release_rows else ["no release-shaped external artifact was found"],
    }


__all__ = ["SCHEMA", "ExternalReleaseArtifactIntakeError", "audit_external_release_artifacts"]
