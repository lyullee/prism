"""Fail-closed audit for the external NASA TN D-4171 HEM benchmark.

The benchmark is useful negative evidence: a spatially homogeneous
equilibrium model under-predicts the reported pressure-rise rates.  It must
therefore remain a diagnostic model-limit record and never become a facility
release, frequency, or physical-validation claim.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCHEMA = "prism.external_nasa_tn_d4171_hem_benchmark.v1"
STATUS = "NEGATIVE_BASELINE_VALIDATION_EVIDENCE"


def audit_nasa_hem_benchmark(
    result: Mapping[str, Any],
    *,
    result_record: str | None = None,
    source_markdown: str | None = None,
    source_markdown_sha256: str | None = None,
    external_source_commit: str | None = None,
    external_source_tree_digest: str | None = None,
) -> dict[str, Any]:
    """Validate the provenance-bound benchmark summary without promotion."""
    points = result.get("points")
    overall = result.get("overall")
    by_mode = result.get("by_heating_mode")
    if not isinstance(points, list) or not isinstance(overall, Mapping) or not isinstance(by_mode, Mapping):
        raise ValueError("NASA HEM benchmark must contain points, overall, and by_heating_mode")
    ratios = [point.get("predicted_over_observed") for point in points if isinstance(point, Mapping)]
    required_modes = {"lower", "uniform", "upper"}
    mode_rows = {
        mode: by_mode.get(mode) for mode in required_modes
    }
    blockers: list[str] = []
    if result.get("source_report") != "NASA TN D-4171":
        blockers.append("source report is not NASA TN D-4171")
    if len(points) != 21 or {point.get("test_number") for point in points if isinstance(point, Mapping)} != set(range(1, 22)):
        blockers.append("benchmark does not contain exactly test numbers 1 through 21")
    if not ratios or not all(isinstance(value, (int, float)) and value == value and value < 1.0 for value in ratios):
        blockers.append("all reported HEM ratios are not finite and below one")
    if set(mode_rows) != required_modes or any(not isinstance(row, Mapping) for row in mode_rows.values()):
        blockers.append("lower/uniform/upper mode summaries are incomplete")
    if overall.get("count") != 21:
        blockers.append("overall count is not 21")
    if not (isinstance(overall.get("mean_absolute_percentage_error_percent"), (int, float)) and overall.get("mean_absolute_percentage_error_percent", 0) > 50.0):
        blockers.append("overall MAPE does not preserve the recorded negative-evidence threshold")
    if not (isinstance(overall.get("normalized_rmse"), (int, float)) and overall.get("normalized_rmse", 0) > 0.35):
        blockers.append("overall normalized RMSE does not preserve the recorded negative-evidence threshold")
    report = {
        "schema_version": SCHEMA,
        "status": STATUS,
        "diagnostic_only": True,
        "result_record": result_record,
        "source_report": result.get("source_report"),
        "source_url": result.get("source_url"),
        "model": result.get("model"),
        "point_count": len(points),
        "heating_modes": sorted(required_modes & set(mode_rows)),
        "overall": {
            "count": overall.get("count"),
            "mean_predicted_over_observed": overall.get("mean_predicted_over_observed"),
            "mean_absolute_percentage_error_percent": overall.get("mean_absolute_percentage_error_percent"),
            "normalized_rmse": overall.get("normalized_rmse"),
        },
        "source_markdown": source_markdown,
        "source_markdown_sha256": source_markdown_sha256,
        "external_source_commit": external_source_commit,
        "external_source_tree_digest": external_source_tree_digest,
        "blocking_reasons": blockers,
        "physical_validation_claim": False,
        "provider_release_packet_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_allowed": False,
        "interpretation": (
            "The unfitted homogeneous-equilibrium baseline under-predicts the NASA TN D-4171 "
            "pressure-rise data, especially for upper heating. This is negative model-limit "
            "evidence for storage/vent pressure dynamics; it does not qualify a provider release "
            "or promote physical validation, frequency, or facility QRA."
        ),
    }
    return report
