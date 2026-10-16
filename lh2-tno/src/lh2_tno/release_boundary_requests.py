"""Build explicit provider requests for open release-boundary cases.

The release-boundary audit already records the exact event, component, port,
and failure reason.  This module turns only the unresolved rows into a small,
machine-readable request packet.  It never repairs a packet, changes a
termination basis, assigns a frequency, or promotes facility QRA.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.release_boundary_evidence_requests.v1"


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value if str(item).strip()]


def _family_requirements(row: Mapping[str, Any]) -> list[str]:
    basis = row.get("provider_termination_evidence_basis") or (
        (row.get("termination") or {}).get("basis")
        if isinstance(row.get("termination"), Mapping)
        else None
    )
    if basis == "emergency_relief_discharge":
        return [
            "event_kind=emergency_relief",
            "source_operator=equipment_emergency_relief",
            "failure_opening_diameter_m is null (relief is not a random hole)",
            "positive provider relief_setpoint_pa",
            "positive provider relief_capacity_kg_s",
            "discharge_complete=true with the physical stopping event identified",
            "provider time history, initial/final inventory, and mass residual within tolerance",
        ]
    if basis == "inventory_over_600s":
        return [
            "provider history continues beyond 600 s until an explicit physical stopping boundary, or",
            "provider declares a different supported termination basis with its own evidence (isolation, inventory depletion, or pressure equalization)",
            "if a physical stop is claimed while inventory remains, include the stop trigger, source pressure/flow response, and a post-stop observation interval",
            "provider time history, initial/final inventory, and mass residual within tolerance",
        ]
    return [
        "provider-owned termination clock and supported termination basis",
        "provider time history, initial/final inventory, and mass/energy residuals",
    ]


def _is_open(row: Mapping[str, Any]) -> bool:
    status = str(row.get("numerical_closure_status", ""))
    evidence = str(row.get("provider_termination_evidence_status", ""))
    return status in {"NUMERICALLY_OPEN", "OPEN"} or evidence in {"INVALID", "NOT_SUPPLIED"}


def build_release_boundary_evidence_requests(
    audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Return exact, family-specific requests for unresolved audit rows."""

    rows = _rows(audit.get("rows"))
    requests: list[dict[str, Any]] = []
    for row in rows:
        if not _is_open(row):
            continue
        termination = row.get("termination")
        termination = termination if isinstance(termination, Mapping) else {}
        identity = {
            "event_id": row.get("event_id"),
            "case_key": row.get("case_key"),
            "asset_id": row.get("asset_id"),
            "component_id": row.get("model_component_id") or row.get("component_id"),
            "port_ids": _text_list(row.get("frequency_case_port_ids") or row.get("frequency_port_ids")),
            "operating_mode": row.get("operating_mode"),
            "hazop_scenario_id": row.get("hazop_scenario_id"),
        }
        basis = row.get("provider_termination_evidence_basis") or termination.get("basis")
        reasons = _text_list(
            row.get("provider_termination_evidence_blocking_reasons")
            or row.get("release_termination_reasons")
            or row.get("release_boundary_blocking_reasons")
        )
        requests.append(
            {
                "request_id": str(row.get("case_key") or row.get("event_id") or "open-case"),
                "status": "OPEN",
                "termination_basis_observed": basis,
                "identity": identity,
                "current_boundary": {
                    "duration_s": row.get("release_duration_s"),
                    "available_mass_kg": row.get("available_mass_kg"),
                    "cumulative_mass_out_kg": row.get("cumulative_mass_out_kg"),
                    "residual_mass_kg": row.get("residual_mass_kg"),
                    "provider_result_digest": row.get("provider_termination_evidence_digest"),
                    "evidence_status": row.get("provider_termination_evidence_status"),
                },
                "blocking_reasons": reasons,
                "required_provider_evidence": _family_requirements(row),
                "qualification_requirements": [
                    "exact source/result artifact digests and provider evidence identifier",
                    "independent physical validation record or an explicitly reviewed validation gap",
                ],
            }
        )
    requests.sort(key=lambda item: item["request_id"])
    return {
        "schema_version": SCHEMA,
        "status": "OPEN_RELEASE_BOUNDARY_EVIDENCE_REQUESTS" if requests else "NO_OPEN_RELEASE_BOUNDARY_EVIDENCE_REQUESTS",
        "source_schema_version": audit.get("schema_version"),
        "source_status": audit.get("status"),
        "source_case_count": audit.get("case_count"),
        "open_request_count": len(requests),
        "requests": requests,
        "policy": {
            "duration_inference_allowed": False,
            "termination_basis_substitution_allowed": False,
            "frequency_inference_allowed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_promotion_allowed": False,
            "physical_validation_claim": False,
            "diagnostic_only": True,
        },
    }


__all__ = ["SCHEMA", "build_release_boundary_evidence_requests"]
