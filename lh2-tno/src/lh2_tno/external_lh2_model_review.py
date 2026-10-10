"""Review an external LH2 digital-twin model root before PRISM promotion.

The external model directory can contain useful topology, component contracts,
and screening results without containing a reviewed accident-release packet.
This module records those facts and keeps provider, frequency, physical-
validation, and facility-QRA promotion fail-closed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .provider_artifact_match_review import audit_external_provider_artifact_matches


SCHEMA = "prism.external_lh2_model_root_review.v1"

_BENCHMARK_FILES = (
    "center_observation_release_packet.json",
    "center_observation_release_plan.json",
    "center_official_independent_validation_20261007.json",
    "center_parameter_release_packet.json",
    "center_readiness_audit.json",
    "center_linkage_contract_audit.json",
    "center_measurement_uncertainty_envelope_20261010.json",
    "center_raw_historian_gate.json",
    "center_raw_workbook_structure_audit.json",
    "center_prediction_workbook_audit.json",
)


def _read_json(path: Path) -> Any:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"unable to decode JSON artifact: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _flag(value: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value:
            return value[key]
    return None


def _benchmark_review(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "file": str(path),
        "sha256": _sha256(path),
        "schema_version": value.get("schema_version"),
        "artifact_id": value.get("artifact_id"),
        "status": value.get("status"),
        "promotion_flags": {
            "release_ready_count": _flag(value, "release_ready_count"),
            "center_promotion_allowed_count": _flag(value, "center_promotion_allowed_count"),
            "forward_comparison_allowed": _flag(value, "forward_comparison_allowed"),
            "parameter_update_allowed": _flag(value, "parameter_update_allowed"),
            "official_score_promotion_allowed": (
                value.get("available_workbook_provenance", {}).get(
                    "official_score_promotion_allowed"
                )
                if isinstance(value.get("available_workbook_provenance"), Mapping)
                else None
            ),
            "ready_for_center_numerical_assembly": _flag(
                value, "ready_for_center_numerical_assembly"
            ),
            "ready_for_numerical_binding": _flag(value, "ready_for_numerical_binding"),
            "promotion_allowed": _flag(value, "promotion_allowed"),
        },
    }
    name = path.name
    if name == "center_observation_release_packet.json":
        item["counts"] = {
            key: value.get(key)
            for key in (
                "binding_count",
                "metadata_confirmed_count",
                "candidate_data_available_count",
                "candidate_diagnostic_available_count",
                "release_ready_count",
            )
        }
    elif name == "center_official_independent_validation_20261007.json":
        summary = value.get("summary") if isinstance(value.get("summary"), Mapping) else {}
        item["counts"] = {
            key: summary.get(key)
            for key in (
                "scenario_count",
                "released_scenario_count",
                "blocked_scenario_count",
                "simulator_invocation_count",
                "official_score",
            )
        }
        item["raw_historian_gate"] = value.get("raw_historian_gate")
    elif name == "center_parameter_release_packet.json":
        item["counts"] = {
            key: value.get(key)
            for key in (
                "asset_count",
                "required_field_count",
                "missing_field_count",
                "screening_candidate_available_count",
                "center_promotion_allowed_count",
                "release_ready_count",
            )
        }
    elif name == "center_readiness_audit.json":
        assets = value.get("asset_models") if isinstance(value.get("asset_models"), Mapping) else {}
        scenarios = value.get("scenarios") if isinstance(value.get("scenarios"), Mapping) else {}
        bindings = value.get("operation_sequence_bindings") if isinstance(value.get("operation_sequence_bindings"), Mapping) else {}
        item["counts"] = {
            "asset_count": assets.get("asset_count"),
            "constructable_count": assets.get("constructable_count"),
            "ready_count": assets.get("ready_count"),
            "scenario_count": scenarios.get("scenario_count"),
            "structurally_ready_scenario_count": scenarios.get("structurally_ready_count"),
            "confirmed_intent_count": bindings.get("confirmed_intent_count"),
        }
    elif name == "center_linkage_contract_audit.json":
        item["counts"] = {
            key: value.get(key)
            for key in (
                "edge_count",
                "edge_ready_count",
                "scenario_count",
                "structurally_ready_scenario_count",
                "model_coverage_ready_scenario_count",
                "scenario_edge_ready_count",
            )
        }
    elif name == "center_raw_historian_gate.json":
        item["counts"] = value.get("summary")
    elif name == "center_raw_workbook_structure_audit.json":
        item["counts"] = value.get("summary")
    elif name == "center_prediction_workbook_audit.json":
        item["counts"] = {"workbook_count": value.get("workbook_count")}
    return item


def review_external_lh2_model_root(
    source_root: str | Path,
    *,
    closure_audit: str | Path | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a provenance review without promoting external model outputs."""

    root = Path(source_root).resolve()
    if not root.is_dir():
        return {
            "schema_version": SCHEMA,
            "status": "MISSING_SOURCE_ROOT",
            "source_root": str(source_root),
            "provider_like_artifacts": {
                "provider_response_count": 0,
                "resolved_release_count": 0,
                "verification_count": 0,
                "exact_generic_identity_match_count": 0,
                "qualification_sidecar_count": 0,
            },
            "promotion": {
                "provider_packet": False,
                "frequency": False,
                "facility_qra": False,
                "physical_validation": False,
            },
            "blocking_reasons": ["external model root does not exist"],
            "conclusion": "MODEL_ROOT_REVIEW_FAILED",
        }

    benchmark_reviews: list[dict[str, Any]] = []
    for name in _BENCHMARK_FILES:
        path = root / "docs" / "benchmarks" / name
        if not path.is_file():
            continue
        value = _read_json(path)
        if isinstance(value, Mapping):
            benchmark_reviews.append(_benchmark_review(path, value))

    provider_responses = sorted(root.rglob("provider_response.json"))
    resolved_releases = sorted(root.rglob("resolved_release.json"))
    verifications = sorted(root.rglob("verification.json"))
    schemas: set[str] = set()
    for path in provider_responses:
        try:
            value = _read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(value, Mapping) and isinstance(value.get("provider_export_schema"), str):
            schemas.add(value["provider_export_schema"])

    match_review: dict[str, Any] | None = None
    if closure_audit is not None:
        match_review = audit_external_provider_artifact_matches(root, closure_audit)

    exact_count = int(match_review.get("exact_match_count", 0)) if match_review else 0
    qualification_count = int(match_review.get("qualification_artifact_count", 0)) if match_review else 0
    physical_count = int(match_review.get("physical_validation_artifact_count", 0)) if match_review else 0
    qra_count = int(match_review.get("complete_facility_qra_artifact_count", 0)) if match_review else 0
    blocking = [
        "External model outputs are diagnostic unless exact event/component/port and source/result digest identity is present.",
    ]
    observation = next(
        (item for item in benchmark_reviews if item["file"].endswith("center_observation_release_packet.json")),
        None,
    )
    if observation and observation.get("counts", {}).get("release_ready_count", 0) == 0:
        blocking.append("observation release packet has zero release-ready bindings")
    official = next(
        (item for item in benchmark_reviews if item["file"].endswith("center_official_independent_validation_20261007.json")),
        None,
    )
    if official and official.get("raw_historian_gate", {}).get("explicit_raw_historian_session_count", 0) == 0:
        blocking.append("no explicit raw historian/DCS/PLC session is available")
    parameter = next(
        (item for item in benchmark_reviews if item["file"].endswith("center_parameter_release_packet.json")),
        None,
    )
    if parameter and parameter.get("counts", {}).get("center_promotion_allowed_count", 0) == 0:
        blocking.append("parameter release packet has zero center-promotion rows")
    if exact_count == 0:
        blocking.append("no exact match to the current generic PRISM packet identities was found")
    if qualification_count == 0:
        blocking.append("no prism.provider_qualification_evidence.v1 sidecar was found")
    if physical_count == 0:
        blocking.append("no independent physical-validation claim was found")
    if qra_count == 0:
        blocking.append("no complete facility-QRA claim was found")

    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "source_root": str(root),
        "benchmark_reviews": benchmark_reviews,
        "provider_like_artifacts": {
            "provider_response_count": len(provider_responses),
            "resolved_release_count": len(resolved_releases),
            "verification_count": len(verifications),
            "provider_export_schemas": sorted(schemas),
            "exact_generic_identity_match_count": exact_count,
            "qualification_sidecar_count": qualification_count,
            "physical_validation_artifact_count": physical_count,
            "complete_facility_qra_artifact_count": qra_count,
        },
        "external_match_review": match_review,
        "promotion": {
            "provider_packet": False,
            "frequency": False,
            "facility_qra": False,
            "physical_validation": False,
        },
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "conclusion": "MODEL_ROOT_REVIEWED_NO_PRISM_PROMOTION",
        "interpretation": (
            "The external model root is retained for topology, component contracts, and screening diagnostics. "
            "Reviewed metadata, exact digest-bound release evidence, and independent validation remain required "
            "before provider, frequency, or facility-QRA promotion."
        ),
    }
    return report


__all__ = ["SCHEMA", "review_external_lh2_model_root"]
