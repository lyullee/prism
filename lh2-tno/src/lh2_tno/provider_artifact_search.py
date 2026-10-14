"""Combine current-provider and legacy-output evidence without promotion."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .legacy_artifact_audit import audit_legacy_provider_artifacts
from .provider_evidence import audit_provider_root


SEARCH_SCHEMA = "prism.provider_artifact_search.v1"


def audit_provider_artifact_roots(
    current_root: str | Path,
    legacy_roots: tuple[str | Path, ...] = (),
) -> dict[str, Any]:
    """Audit current provider evidence and legacy outputs as separate classes.

    The current root uses the full provider evidence audit.  Legacy roots use
    the non-promoting schema audit.  No result from either audit is converted
    into a consequence request or facility risk case here.
    """
    current = audit_provider_root(Path(current_root))
    legacy = [audit_legacy_provider_artifacts(Path(root)) for root in legacy_roots]
    contract_valid_current = int(
        current.get("release_evidence", {}).get("accident_release_qualified_file_count", 0)
    ) + int(
        current.get("release_evidence", {}).get("emergency_relief_qualified_file_count", 0)
    )
    contract_valid_legacy = sum(
        int(item.get("qualified_current_schema_count", 0)) for item in legacy
    )
    # A packet can satisfy the serialized release contract while the provider
    # root is still screening-only.  Keep that distinction explicit: contract
    # validity is useful diagnostic evidence, but it is not provider
    # qualification and must not open the facility-QRA gate.
    provider_executable = current.get("status") == "EXECUTABLE_PROVIDER"
    qualified_current = contract_valid_current if provider_executable else 0
    return {
        "schema": SEARCH_SCHEMA,
        "status": "QUALIFIED_PROVIDER_PACKET_FOUND"
        if qualified_current > 0
        else "NO_QUALIFIED_PROVIDER_PACKET_FOUND",
        "contract_valid_diagnostic_packet_status": (
            "CONTRACT_VALID_DIAGNOSTIC_PACKET_FOUND"
            if contract_valid_current > 0
            else "NO_CONTRACT_VALID_DIAGNOSTIC_PACKET_FOUND"
        ),
        "current_provider": current,
        "legacy_outputs": legacy,
        "summary": {
            "current_contract_valid_diagnostic_packet_count": contract_valid_current,
            "current_qualified_packet_count": qualified_current,
            "legacy_contract_valid_packet_count": contract_valid_legacy,
            "legacy_current_schema_count": contract_valid_legacy,
            "legacy_missing_schema_count": sum(
                int(item.get("legacy_missing_schema_count", 0)) for item in legacy
            ),
            "provider_root_executable": provider_executable,
            "facility_ir_fn_allowed": False,
        },
        "promotion_policy": {
            "current_and_legacy_results_remain_separate": True,
            "legacy_schema_is_never_added": True,
            "contract_valid_packet_is_not_provider_qualification": True,
            "screening_only_provider_is_not_qualified": True,
            "facility_ir_fn_requires_exact_provider_and_frequency_evidence": True,
        },
    }
