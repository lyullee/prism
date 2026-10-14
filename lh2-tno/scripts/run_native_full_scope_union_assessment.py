"""Merge native general-LH2 diagnostic campaigns into one facility ledger.

The base 24-event campaign, the five-event vertical-handoff campaign and the
five-event inventory-depletion campaign are independent diagnostic ledgers.
This script rebinds the disjoint results into the base facility namespace,
remaps event IDs, merges the facility ledger and accident-family matrix, and
reweights the saved atoms with the same literature-frequency scenarios.  It
never promotes the synthetic campaigns or creates a facility-QRA claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.facility_case_packet_coverage import (  # noqa: E402
    audit_facility_case_packet_coverage,
)
from lh2_tno.facility_evidence_request import build_facility_evidence_request  # noqa: E402
from lh2_tno.facility_ledger import merge_facility_campaign_results  # noqa: E402
from lh2_tno.campaign_namespace import rebind_campaign_result  # noqa: E402
from lh2_tno.native_packet_campaign import (  # noqa: E402
    build_native_packet_campaign_execution_ledger,
)
from lh2_tno.state_snapshot_result_binding import (  # noqa: E402
    bind_campaign_result_state_snapshots,
)
from lh2_tno.facility_scope_matrix import (  # noqa: E402
    build_scope_matrix_from_facility_ledger,
    repair_facility_ledger_scenario_families,
)
from lh2_tno.uncertainty import LiteratureFrequencyScenario  # noqa: E402
from lh2_tno.frequency_scenario_extension import (  # noqa: E402
    extend_frequency_scenarios_for_independent_event_bounds,
)
from lh2_tno.vertical_handoff_campaign import (  # noqa: E402
    rebind_vertical_handoff_campaign_result,
)
from lh2_tno.extension_state_snapshot_coverage import (  # noqa: E402
    build_extension_state_snapshot_coverage,
)
from lh2_tno.scope_ledger_consistency import (  # noqa: E402
    audit_scope_ledger_consistency,
)
from lh2_tno.risk_atom_chain_audit import (  # noqa: E402
    build_risk_atom_chain_audit,
)
from lh2_tno.equipment_state_release_audit import (  # noqa: E402
    build_equipment_state_release_audit,
)
from lh2_tno.facility_aggregate_closure_audit import (  # noqa: E402
    build_facility_aggregate_closure_audit,
)
from lh2_tno.facility_component_contribution_audit import (  # noqa: E402
    build_facility_component_contribution_audit,
)
from lh2_tno.facility_frequency_uncertainty_audit import (  # noqa: E402
    build_facility_frequency_uncertainty_audit,
)
from lh2_tno.hazop_event_selection_audit import (  # noqa: E402
    audit_hazop_selection_event_bindings,
)


MAJOR_ACCIDENT_FAMILIES = (
    "vessel_hole",
    "pipe_hole",
    "valve_hole",
    "vent_hole",
    "pump_hole",
    "vaporizer_hole",
    "reliquefier_hole",
    "liquid_two_phase",
    "inventory_depletion",
    "inventory_over_600s",
    "two_sided_rupture",
    "vertical_handoff",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _is_prebound_extension(
    result: dict[str, Any],
    *,
    facility_id: str,
    namespace: str,
    event_marker: str,
) -> bool:
    """Recognize a result already rebound into the selected facility namespace.

    Rebinding an already rebound result would duplicate the namespace and
    silently break the extension state-snapshot ledger.  Treat a matching
    facility/event namespace as an immutable diagnostic result and only rebind
    stand-alone source campaigns.
    """
    if str(result.get("facility_id", "")).strip() != facility_id:
        return False
    events = result.get("events")
    if not isinstance(events, list) or not events:
        return False
    prefix = f"{namespace.rstrip('/')}/"
    return all(
        isinstance(event, dict)
        and isinstance(event.get("id"), str)
        and event["id"].startswith(prefix)
        and event_marker in event["id"]
        for event in events
    )


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _rebind_vertical_scope_matrix(
    source: dict[str, Any],
    *,
    facility_id: str,
    namespace: str,
) -> dict[str, Any]:
    """Map old vertical event IDs to the exact IDs in the rebound result."""
    output = deepcopy(source)
    for row in output.get("rows", []):
        if not isinstance(row, dict):
            continue
        mapped: list[str] = []
        for event_id in row.get("event_ids", []):
            value = str(event_id)
            if "/terminal-valve/" in value:
                suffix = value.split("/terminal-valve/", 1)[1]
                value = f"{namespace}/terminal-valve/{suffix}"
            mapped.append(value)
        row["event_ids"] = mapped
    output["facility_id"] = facility_id
    output["source_scope_matrix"] = source.get("facility_id")
    output["scope_rebind"] = {
        "schema_version": "prism.vertical_handoff_scope_matrix_rebind.v1",
        "facility_id": facility_id,
        "namespace": namespace,
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }
    return output


def _rebind_inventory_scope_matrix(
    source: dict[str, Any],
    *,
    facility_id: str,
    namespace: str,
) -> dict[str, Any]:
    """Map the legacy inventory-depletion matrix to the rebound event IDs."""
    output = deepcopy(source)
    for row in output.get("rows", []):
        if not isinstance(row, dict):
            continue
        mapped: list[str] = []
        for event_id in row.get("event_ids", []):
            value = str(event_id)
            if "/terminal_pipe_asset/" in value:
                suffix = value.split("/terminal_pipe_asset/", 1)[1]
                value = f"{namespace}/terminal_pipe_asset/{suffix}"
            mapped.append(value)
        row["event_ids"] = mapped
    output["facility_id"] = facility_id
    output["source_scope_matrix"] = source.get("facility_id")
    output["scope_rebind"] = {
        "schema_version": "prism.inventory_depletion_scope_matrix_rebind.v1",
        "facility_id": facility_id,
        "namespace": namespace,
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }
    return output


def _rebind_inventory_conditions(
    result: dict[str, Any],
    *,
    namespace: str,
) -> dict[str, Any]:
    """Namespace source weather/population condition IDs before facility merge."""
    output = deepcopy(result)
    conditions = output.get("annual_conditions", [])
    if not isinstance(conditions, list):
        raise ValueError("inventory campaign annual_conditions must be a list")
    condition_map: dict[str, str] = {}
    for condition in conditions:
        if not isinstance(condition, dict) or not condition.get("id"):
            raise ValueError("inventory campaign annual conditions require IDs")
        old_id = str(condition["id"])
        new_id = f"{namespace}/{old_id}"
        condition_map[old_id] = new_id
        condition["id"] = new_id
    for key in ("cases", "uncomputed_cases", "risk_atoms"):
        rows = output.get(key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("annual_condition_id"):
                old_id = str(row["annual_condition_id"])
                row["annual_condition_id"] = condition_map.get(old_id, old_id)
    rebind = output.get("campaign_namespace_rebind")
    if isinstance(rebind, dict):
        rebind["annual_condition_id_map"] = condition_map
        rebind["condition_rebind_policy"] = "namespaced_condition_ids_preserve_source_weather"
    return output


def _extend_frequency_scenarios(
    source: dict[str, Any],
) -> tuple[LiteratureFrequencyScenario, ...]:
    raw_scenarios = source.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("base frequency scenarios must contain a nonempty scenarios list")
    scenarios: list[LiteratureFrequencyScenario] = []
    for index, raw in enumerate(raw_scenarios):
        if not isinstance(raw, dict):
            raise ValueError(f"frequency scenario {index} must be an object")
        item = deepcopy(raw)
        if isinstance(item.get("asset_quantiles"), dict):
            item["asset_quantiles"]["vertical-handoff-vent"] = "published"
            item["asset_quantiles"]["inventory-depletion-pipe"] = "published"
        elif isinstance(item.get("event_quantiles"), dict):
            for area in ("AREA_0.01%", "AREA_0.1%", "AREA_1%", "AREA_10%", "AREA_100%"):
                item["event_quantiles"][
                    f"generic-lh2-near-receptor-diagnostic/vertical-handoff/terminal-valve/{area}"
                ] = "published"
        else:
            raise ValueError(f"frequency scenario {index} has no quantile map")
        provenance = str(item.get("provenance", "")).strip()
        suffix = "vertical handoff fixed at declared diagnostic rate; no frequency inference"
        suffix += "; inventory depletion fixed at declared diagnostic rate; no frequency inference"
        item["provenance"] = f"{provenance}; {suffix}" if provenance else suffix
        scenarios.append(LiteratureFrequencyScenario.model_validate(item))
    return tuple(scenarios)


def run(args: argparse.Namespace) -> dict[str, Any]:
    base_dir = args.base_dir
    base_campaign = _load(args.base_campaign or (base_dir / "campaign.json"))
    base_result = _load(args.base_campaign_result or (base_dir / "campaign_result.json"))
    base_facility = _load(base_dir / "facility.json")
    base_scope = _load(base_dir / "scope_matrix.json")
    base_frequency_scenarios = _load(base_dir / "frequency_scenarios.json")
    vertical_source = _load(args.vertical_result)
    vertical_scope_source = _load(args.vertical_scope_matrix)
    inventory_source = _load(args.inventory_result)
    inventory_scope_source = _load(args.inventory_scope_matrix)
    state_snapshot_audit = (
        _load(args.state_snapshot_binding_audit)
        if args.state_snapshot_binding_audit is not None
        else None
    )
    extension_state_snapshot_audit = (
        _load(args.extension_state_snapshot_audit)
        if args.extension_state_snapshot_audit is not None
        else None
    )
    hazop_runtime_audit = (
        _load(args.hazop_runtime_audit)
        if args.hazop_runtime_audit is not None
        else None
    )
    hazop_mode_binding = (
        _load(args.hazop_mode_binding)
        if args.hazop_mode_binding is not None
        else None
    )
    base_result_state_binding = None
    if state_snapshot_audit is not None:
        # The result ledger and the state-bound request are separate persisted
        # artifacts.  Join them before the facility merge so a rerun cannot
        # silently drop the canonical state identity from base risk atoms.
        base_result, base_result_state_binding = bind_campaign_result_state_snapshots(
            base_result,
            base_campaign,
            state_snapshot_audit,
        )
    if state_snapshot_audit is not None:
        native_state_snapshot_ledger = build_native_packet_campaign_execution_ledger(
            base_campaign,
            base_result,
            state_snapshot_audit=state_snapshot_audit,
        )
    else:
        native_state_snapshot_ledger = {
            "schema_version": "prism.native_lh2dt_packet_campaign_execution.v1",
            "status": "STATE_SNAPSHOT_CAMPAIGN_AUDIT_NOT_PROVIDED",
            "event_count": len(base_campaign.get("event_routes", [])),
            "case_count": len(base_result.get("cases", [])),
            "diagnostic_only": True,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "interpretation": (
                "The union output was built without a state snapshot audit; native campaign/state "
                "identity reconciliation remains unavailable."
            ),
        }

    facility_id = str(base_result.get("facility_id", "")).strip()
    facility_reference_id = str(base_facility.get("id", "")).strip()
    if facility_reference_id:
        # The facility geometry is already consumed by the consequence solver.
        # Relabelling a result after execution would silently attach harm values
        # calculated for one receptor layout to another layout.  Require the
        # serialized result and selected facility to agree instead of repairing
        # the identity after the fact.
        if facility_id != facility_reference_id:
            raise ValueError(
                "base campaign result facility_id does not match base facility id; "
                "recompute the campaign with the selected facility geometry before union"
            )
    if not facility_id:
        raise ValueError("base campaign result has no facility_id")
    namespace = f"{facility_id}/vertical-handoff"
    vertical_result = (
        deepcopy(vertical_source)
        if _is_prebound_extension(
            vertical_source,
            facility_id=facility_id,
            namespace=namespace,
            event_marker="/terminal-valve/",
        )
        else rebind_vertical_handoff_campaign_result(
            vertical_source,
            facility_id=facility_id,
            namespace=namespace,
            asset_id="vertical-handoff-vent",
            component_id="vertical-handoff-terminal-pipe-01",
            receptor_map={
                "worker-01": "worker-01",
                "near_worker": "worker-01",
                "downwind_worker": "worker-01",
                "side_worker": "worker-01",
                "distant_worker": "worker-01",
            },
        )
    )
    vertical_scope = _rebind_vertical_scope_matrix(
        vertical_scope_source,
        facility_id=facility_id,
        namespace=namespace,
    )
    inventory_namespace = f"{facility_id}/inventory-depletion"
    inventory_prebound = _is_prebound_extension(
        inventory_source,
        facility_id=facility_id,
        namespace=inventory_namespace,
        event_marker="/terminal_pipe_asset/",
    )
    inventory_result = (
        deepcopy(inventory_source)
        if inventory_prebound
        else rebind_campaign_result(
            inventory_source,
            source_facility_id=str(inventory_source.get("facility_id", "")).strip(),
            facility_id=facility_id,
            namespace=inventory_namespace,
            source_asset_id=args.inventory_source_asset_id,
            asset_id="inventory-depletion-pipe",
            source_component_id=args.inventory_source_component_id,
            component_id="inventory-depletion-pipe-01",
            receptor_map={
                "near_worker": "worker-01",
                "downwind_worker": "worker-01",
                "side_worker": "worker-01",
                "distant_worker": "worker-01",
            },
        )
    )
    if not inventory_prebound:
        inventory_result = _rebind_inventory_conditions(
            inventory_result,
            namespace=inventory_namespace,
        )
    inventory_scope = _rebind_inventory_scope_matrix(
        inventory_scope_source,
        facility_id=facility_id,
        namespace=inventory_namespace,
    )

    extension_state_snapshot_coverage = build_extension_state_snapshot_coverage(
        extension_results={
            "vertical_handoff": vertical_result,
            "inventory_depletion": inventory_result,
        },
        state_snapshot_audit=extension_state_snapshot_audit,
    )

    expected_components = tuple(
        str(component["id"]) for component in base_facility.get("components", [])
    ) + ("vertical-handoff-terminal-pipe-01", "inventory-depletion-pipe-01")
    merged = merge_facility_campaign_results(
        [base_result, vertical_result, inventory_result],
        expected_component_ids=expected_components,
        scope_matrices=[base_scope, vertical_scope, inventory_scope],
        required_accident_families=MAJOR_ACCIDENT_FAMILIES,
    )
    # The merged facility ledger is the authority for the final scope view.
    # Source campaign matrices intentionally retain their own family views,
    # but they can disagree with the merged case tags when a physical event
    # carries a cross-cutting family (for example vertical-handoff cases are
    # also pipe-hole cases, while provider gas-exit packets no longer carry
    # the liquid-two-phase overlay).  Rebuilding here keeps the scope matrix
    # and facility ledger on the same event/case identity set without
    # changing any frequency, consequence, or qualification result.
    repaired_merged = repair_facility_ledger_scenario_families(merged)
    merged_scope = build_scope_matrix_from_facility_ledger(
        repaired_merged,
        required_families=MAJOR_ACCIDENT_FAMILIES,
    )
    merged_scope["source_campaign_scope_matrices"] = [
        {
            "facility_id": matrix.get("facility_id"),
            "source": matrix.get("source", matrix.get("schema_version")),
            "digest": canonical_digest(matrix),
        }
        for matrix in (base_scope, vertical_scope, inventory_scope)
    ]
    source_alignment = next(
        (
            matrix.get("provider_worklist_alignment")
            for matrix in (base_scope, vertical_scope, inventory_scope)
            if isinstance(matrix.get("provider_worklist_alignment"), dict)
        ),
        None,
    )
    if source_alignment is not None:
        merged_scope["provider_worklist_alignment"] = dict(source_alignment)
        merged_scope["provider_worklist_alignment"].update(
            {
                "scope": "base source worklist only",
                "facility_merge_additional_campaigns": 2,
                "facility_merge_alignment_claim": False,
                "interpretation": (
                    "The ALIGNED record applies to the 24-event base worklist. "
                    "Namespaced vertical-handoff and inventory-depletion extensions "
                    "remain separate diagnostic campaigns."
                ),
            }
        )
    merged_scope["interpretation"] = (
        "The final scope matrix is regenerated from the merged facility ledger. "
        "Source campaign matrices remain provenance views; overlapping family "
        "rows are not additive and the ledger's exact event/case identities are authoritative."
    )
    hazop_selection_event_audit = None
    if hazop_runtime_audit is not None and hazop_mode_binding is not None:
        families_by_event: dict[str, set[str]] = {}
        for case in repaired_merged.get("cases", []):
            if not isinstance(case, dict):
                continue
            event_id = case.get("event_id")
            families = case.get("scenario_families", [])
            if not isinstance(event_id, str) or not isinstance(families, list):
                continue
            families_by_event.setdefault(event_id, set()).update(
                str(family)
                for family in families
                if isinstance(family, str) and family
            )
        frequency_event_rows = [
            {
                **event,
                "scenario_families": sorted(
                    families_by_event.get(str(event.get("id")), set())
                ),
            }
            for event in repaired_merged.get("events", [])
            if isinstance(event, dict)
        ]
        # Audit the merged event set. Extension events without an explicit
        # operating-mode binding remain unbound; they never inherit a base
        # mode or scenario by inference.
        hazop_selection_event_audit = audit_hazop_selection_event_bindings(
            hazop_runtime_audit,
            hazop_mode_binding,
            frequency_event_rows,
        )
    scenarios = _extend_frequency_scenarios(base_frequency_scenarios)
    independent_extension = extend_frequency_scenarios_for_independent_event_bounds(
        {
            "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
        },
        merged.get("events", []),
    )
    scenarios = tuple(
        LiteratureFrequencyScenario.model_validate(row)
        for row in independent_extension["scenarios"]
    )
    assessment = build_facility_assessment(
        [base_result, vertical_result, inventory_result],
        expected_component_ids=expected_components,
        scope_matrices=[base_scope, vertical_scope, inventory_scope],
        required_accident_families=MAJOR_ACCIDENT_FAMILIES,
        frequency_scenarios=scenarios,
    )
    evidence_request = build_facility_evidence_request(assessment, merged_scope)
    # Every declared facility case must have an explicit provider-evidence
    # disposition.  The union runner has no qualified provider catalog to
    # consume today, so this deliberately produces a fail-closed report with
    # one missing-evidence row per case.  Passing the report back through the
    # assessment builder makes the absence actionable without treating a
    # diagnostic packet as qualified evidence.
    facility_case_packet_coverage = audit_facility_case_packet_coverage(
        evidence_request,
        (),
    )
    facility_case_packet_coverage["_record_path"] = str(
        args.output_dir / "facility_case_packet_coverage.json"
    )
    assessment = build_facility_assessment(
        [base_result, vertical_result, inventory_result],
        expected_component_ids=expected_components,
        scope_matrices=[base_scope, vertical_scope, inventory_scope],
        required_accident_families=MAJOR_ACCIDENT_FAMILIES,
        frequency_scenarios=scenarios,
        facility_case_packet_coverage=facility_case_packet_coverage,
    )
    # Re-run the scope/ledger comparison from the exact artifacts being
    # written. Source campaign matrices are provenance views and may use
    # overlapping family rows; the rebuilt scope matrix and merged ledger
    # must still agree family by family before the union is published.
    assessment_ledger = assessment.get("facility_risk_ledger")
    if not isinstance(assessment_ledger, dict):
        raise ValueError("facility assessment does not contain facility_risk_ledger")
    scope_ledger_consistency = audit_scope_ledger_consistency(
        merged_scope,
        assessment_ledger,
    )
    risk_atom_chain_audit = build_risk_atom_chain_audit(assessment_ledger)
    risk_atom_chain_audit["_record_path"] = str(
        args.output_dir / "risk_atom_chain_audit.json"
    )
    equipment_state_release_audit = build_equipment_state_release_audit(assessment_ledger)
    equipment_state_release_audit["_record_path"] = str(
        args.output_dir / "equipment_state_release_audit.json"
    )
    facility_aggregate_closure_audit = build_facility_aggregate_closure_audit(
        assessment_ledger
    )
    facility_aggregate_closure_audit["_record_path"] = str(
        args.output_dir / "facility_aggregate_closure_audit.json"
    )
    facility_component_contribution_audit = build_facility_component_contribution_audit(
        assessment_ledger
    )
    facility_component_contribution_audit["_record_path"] = str(
        args.output_dir / "facility_component_contribution_audit.json"
    )
    frequency_scenario_source = {
        "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
        "frequency_inference_performed": False,
        "facility_credible_interval": False,
    }
    facility_frequency_uncertainty_audit = build_facility_frequency_uncertainty_audit(
        assessment_ledger,
        frequency_scenario_source,
        assessment["frequency_uncertainty"],
    )
    facility_frequency_uncertainty_audit["_record_path"] = str(
        args.output_dir / "facility_frequency_uncertainty_audit.json"
    )

    vertical_row = next(
        row for row in merged_scope["rows"] if row["family"] == "vertical_handoff"
    )
    inventory_row = next(
        row for row in merged_scope["rows"] if row["family"] == "inventory_depletion"
    )
    verification = {
        "schema_version": "prism.native_full_scope_union_assessment.v1",
        "status": "NATIVE_FULL_SCOPE_UNION_DIAGNOSTIC",
        "facility_id": facility_id,
        "base_event_count": len(base_result.get("events", [])),
        "vertical_event_count": len(vertical_result.get("events", [])),
        "inventory_depletion_event_count": len(inventory_result.get("events", [])),
        "merged_event_count": merged["event_count"],
        "merged_case_count": merged["case_count"],
        "merged_risk_atom_count": len(merged.get("risk_atoms", [])),
        "vertical_handoff_status": vertical_row["status"],
        "vertical_handoff_conditional_status": vertical_row["conditional_status"],
        "vertical_handoff_conditional_executed_case_count": vertical_row[
            "conditional_executed_case_count"
        ],
        "vertical_handoff_operator_limited_case_count": vertical_row[
            "operator_limited_case_count"
        ],
        "inventory_depletion_status": inventory_row["status"],
        "inventory_depletion_conditional_status": inventory_row["conditional_status"],
        "inventory_depletion_conditional_executed_case_count": inventory_row[
            "conditional_executed_case_count"
        ],
        "inventory_depletion_operator_limited_case_count": inventory_row[
            "operator_limited_case_count"
        ],
        "conditional_diagnostic_facility_risk_available": assessment[
            "conditional_diagnostic_facility_risk_available"
        ],
        "population_accounting_status": assessment.get("population_accounting", {}).get(
            "status"
        ),
        "population_accounting_mismatch_count": len(
            assessment.get("population_accounting", {}).get(
                "mismatched_receptor_ids", {}
            )
        ),
        "conditional_diagnostic_facility_annual_ir_low_high": assessment[
            "conditional_diagnostic_facility_annual_ir_low_high"
        ],
        "facility_total_risk_available": assessment["facility_total_risk_available"],
        "complete_facility_qra_claim": assessment["complete_facility_qra_claim"],
        "provider_packet_case_count": merged["provider_packet_case_count"],
        "qualified_provider_packet_case_count": merged[
            "qualified_provider_packet_case_count"
        ],
        "physical_validation_claim": assessment["physical_validation_claim"],
        "frequency_scenario_count": len(assessment["frequency_uncertainty"]["scenarios"]),
        "frequency_correlation_comparison_present": assessment[
            "frequency_uncertainty"
        ]["correlation_comparison_present"],
        "facility_evidence_request_status": evidence_request["status"],
        "facility_evidence_request_family_count": len(evidence_request["family_requests"]),
        "facility_evidence_request_case_count": evidence_request["case_request_count"],
        "facility_evidence_request_promotion_allowed": (
            assessment["complete_facility_qra_claim"] is True
        ),
        "facility_case_packet_coverage_status": facility_case_packet_coverage[
            "status"
        ],
        "facility_case_packet_coverage_case_count": facility_case_packet_coverage[
            "case_request_count"
        ],
        "facility_case_packet_coverage_qualified_case_count": facility_case_packet_coverage[
            "qualified_provider_case_count"
        ],
        "native_state_snapshot_campaign_status": native_state_snapshot_ledger["status"],
        "native_state_snapshot_campaign_event_count": native_state_snapshot_ledger.get("event_count"),
        "native_state_snapshot_campaign_case_count": native_state_snapshot_ledger.get("case_count"),
        "native_state_snapshot_campaign_bound_event_count": native_state_snapshot_ledger.get(
            "state_snapshot_campaign_reconciliation", {}
        ).get("bound_event_count"),
        "native_state_snapshot_campaign_provider_result_digest_mismatch_count": len(
            native_state_snapshot_ledger.get("state_snapshot_campaign_reconciliation", {})
            .get("provider_result_digest_mismatch_event_ids", [])
        ),
        "base_result_state_snapshot_binding_status": (
            base_result_state_binding.get("status")
            if base_result_state_binding is not None
            else "NOT_PROVIDED"
        ),
        "base_result_state_snapshot_binding_event_count": (
            base_result_state_binding.get("event_count")
            if base_result_state_binding is not None
            else 0
        ),
        "base_result_state_snapshot_binding_case_count": (
            base_result_state_binding.get("bound_case_count")
            if base_result_state_binding is not None
            else 0
        ),
        "base_result_state_snapshot_binding_risk_atom_count": (
            base_result_state_binding.get("bound_risk_atom_count")
            if base_result_state_binding is not None
            else 0
        ),
        "extension_state_snapshot_coverage_status": extension_state_snapshot_coverage[
            "status"
        ],
        "extension_state_snapshot_coverage_event_count": extension_state_snapshot_coverage[
            "event_count"
        ],
        "extension_state_snapshot_coverage_bound_event_count": extension_state_snapshot_coverage[
            "bound_event_count"
        ],
        "extension_state_snapshot_coverage_unbound_event_count": extension_state_snapshot_coverage[
            "unbound_event_count"
        ],
        "extension_state_snapshot_missing_event_ids": extension_state_snapshot_coverage[
            "missing_event_ids"
        ],
        "scope_ledger_consistency_status": scope_ledger_consistency["status"],
        "scope_ledger_consistency_blocking_reason_count": len(
            scope_ledger_consistency["blocking_reasons"]
        ),
        "scope_ledger_consistency_scope_event_count": scope_ledger_consistency[
            "scope_matrix_event_count"
        ],
        "scope_ledger_consistency_ledger_event_count": scope_ledger_consistency[
            "facility_ledger_event_count"
        ],
        "risk_atom_chain_audit_status": risk_atom_chain_audit["status"],
        "risk_atom_chain_audit_case_count": risk_atom_chain_audit["case_count"],
        "risk_atom_chain_audit_complete_case_count": risk_atom_chain_audit[
            "complete_case_count"
        ],
        "risk_atom_chain_audit_risk_atom_count": risk_atom_chain_audit[
            "risk_atom_count"
        ],
        "risk_atom_chain_audit_blocking_reason_count": len(
            risk_atom_chain_audit["blocking_reasons"]
        ),
        "equipment_state_release_audit_status": equipment_state_release_audit["status"],
        "equipment_state_release_audit_case_count": equipment_state_release_audit[
            "case_count"
        ],
        "equipment_state_release_audit_complete_case_count": equipment_state_release_audit[
            "complete_case_count"
        ],
        "equipment_state_release_audit_component_count": equipment_state_release_audit[
            "component_count"
        ],
        "equipment_state_release_audit_blocking_reason_count": len(
            equipment_state_release_audit["blocking_reasons"]
        ),
        "facility_aggregate_closure_audit_status": facility_aggregate_closure_audit[
            "status"
        ],
        "facility_aggregate_closure_audit_risk_atom_count": facility_aggregate_closure_audit[
            "risk_atom_count"
        ],
        "facility_aggregate_closure_audit_ir_mismatch_count": facility_aggregate_closure_audit[
            "ir_mismatch_count"
        ],
        "facility_aggregate_closure_audit_fn_mismatch_count": facility_aggregate_closure_audit[
            "fn_mismatch_count"
        ],
        "facility_aggregate_closure_audit_blocking_reason_count": len(
            facility_aggregate_closure_audit["blocking_reasons"]
        ),
        "facility_component_contribution_audit_status": facility_component_contribution_audit[
            "status"
        ],
        "facility_component_contribution_audit_component_count": facility_component_contribution_audit[
            "component_count"
        ],
        "facility_component_contribution_audit_risk_atom_count": facility_component_contribution_audit[
            "risk_atom_count"
        ],
        "facility_component_contribution_audit_mismatch_count": facility_component_contribution_audit[
            "mismatch_count"
        ],
        "facility_component_contribution_audit_blocking_reason_count": len(
            facility_component_contribution_audit["blocking_reasons"]
        ),
        "facility_frequency_uncertainty_audit_status": facility_frequency_uncertainty_audit[
            "status"
        ],
        "facility_frequency_uncertainty_audit_scenario_count": facility_frequency_uncertainty_audit[
            "scenario_count"
        ],
        "facility_frequency_uncertainty_audit_risk_atom_count": facility_frequency_uncertainty_audit[
            "risk_atom_count"
        ],
        "facility_frequency_uncertainty_audit_mismatch_count": facility_frequency_uncertainty_audit[
            "mismatch_count"
        ],
        "facility_frequency_uncertainty_audit_blocking_reason_count": len(
            facility_frequency_uncertainty_audit["blocking_reasons"]
        ),
        "limitations": [
            "vertical handoff is a namespaced diagnostic campaign, not a new qualified provider packet",
            "vertical provider history is synthetic/operator-limited and retains its termination horizon",
            "the merged conditional IR/F-N is diagnostic and facility total IR/F-N remains withheld",
            "frequency scenarios reweight saved atoms and do not infer vertical frequency",
            "independent-event p05/p95 scenarios use fixed declared rates for events without published bounds",
            "inventory depletion is a namespaced diagnostic rebound, not a qualified site packet",
            "inventory depletion population, weather and geometry remain synthetic diagnostics",
            "the native state snapshot reconciliation covers the base 24-event packet campaign; "
            "vertical-handoff and inventory-depletion extension events have separate state snapshot "
            "records and are state-bound for diagnostic accounting, but their synthetic "
            "model-prediction origin does not qualify field evidence",
            "extension state coverage is audited per event; release values and result digests are never "
            "used to reconstruct a missing canonical equipment state snapshot",
        ],
    }
    if hazop_selection_event_audit is not None:
        verification["hazop_selection_event_binding_status"] = hazop_selection_event_audit[
            "status"
        ]
        verification["hazop_selection_event_binding_selected_scenario_count"] = (
            hazop_selection_event_audit["selected_scenario_count"]
        )
        verification["hazop_selection_event_binding_event_count"] = (
            hazop_selection_event_audit["frequency_event_count"]
        )
        verification["hazop_selection_event_binding_bound_event_count"] = (
            hazop_selection_event_audit["bound_event_count"]
        )
        verification["hazop_selection_event_binding_unbound_event_count"] = (
            hazop_selection_event_audit["unbound_event_count"]
        )
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    _save(output / "campaign_result.json", merged)
    _save(output / "vertical_handoff_rebound_result.json", vertical_result)
    _save(output / "inventory_depletion_rebound_result.json", inventory_result)
    _save(output / "scope_matrix.json", merged_scope)
    _save(output / "scope_ledger_consistency_current.json", scope_ledger_consistency)
    _save(output / "risk_atom_chain_audit.json", risk_atom_chain_audit)
    _save(output / "equipment_state_release_audit.json", equipment_state_release_audit)
    _save(
        output / "facility_aggregate_closure_audit.json",
        facility_aggregate_closure_audit,
    )
    _save(
        output / "facility_component_contribution_audit.json",
        facility_component_contribution_audit,
    )
    _save(
        output / "facility_frequency_uncertainty_audit.json",
        facility_frequency_uncertainty_audit,
    )
    _save(
        output / "frequency_scenarios.json",
        {
            "schema_version": "prism.native_full_scope_union_frequency_scenarios.v1",
            "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
            "vertical_handoff_frequency_inference": False,
            "inventory_depletion_frequency_inference": False,
            "independent_event_bound_event_count": independent_extension[
                "independent_event_bound_event_count"
            ],
            "independent_event_bound_fixed_event_count": independent_extension[
                "independent_event_bound_fixed_event_count"
            ],
            "frequency_inference_performed": False,
            "facility_credible_interval": False,
        },
    )
    _save(output / "facility_assessment.json", assessment)
    if hazop_selection_event_audit is not None:
        _save(output / "hazop_selection_event_binding.json", hazop_selection_event_audit)
    _save(output / "facility_evidence_request.json", evidence_request)
    _save(output / "facility_case_packet_coverage.json", facility_case_packet_coverage)
    _save(output / "native_state_snapshot_campaign_ledger.json", native_state_snapshot_ledger)
    if base_result_state_binding is not None:
        _save(output / "base_result_state_snapshot_binding.json", base_result_state_binding)
    _save(
        output / "extension_state_snapshot_coverage.json",
        extension_state_snapshot_coverage,
    )
    if state_snapshot_audit is not None:
        _save(output / "state_snapshot_binding_audit.json", state_snapshot_audit)
    _save(output / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--base-campaign", type=Path, default=None)
    parser.add_argument("--base-campaign-result", type=Path, default=None)
    parser.add_argument("--vertical-result", type=Path, required=True)
    parser.add_argument("--vertical-scope-matrix", type=Path, required=True)
    parser.add_argument("--inventory-result", type=Path, required=True)
    parser.add_argument("--inventory-scope-matrix", type=Path, required=True)
    parser.add_argument(
        "--inventory-source-asset-id",
        default="inventory-depletion-pipe",
        help="asset ID in the inventory source campaign before namespace rebinding",
    )
    parser.add_argument(
        "--inventory-source-component-id",
        default="inventory-depletion-pipe-01",
        help="component ID in the inventory source campaign before namespace rebinding",
    )
    parser.add_argument("--state-snapshot-binding-audit", type=Path, default=None)
    parser.add_argument("--extension-state-snapshot-audit", type=Path, default=None)
    parser.add_argument(
        "--hazop-runtime-audit",
        type=Path,
        default=None,
        help="optional observed HAZOP runtime audit used to audit the merged event set",
    )
    parser.add_argument(
        "--hazop-mode-binding",
        type=Path,
        default=None,
        help="optional explicit HAZOP operating-mode/event binding for the merged event set",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"native full-scope union assessment failed: {error}") from error
    print(
        json.dumps(
            {
                "status": result["status"],
                "facility_id": result["facility_id"],
                "merged_event_count": result["merged_event_count"],
                "merged_case_count": result["merged_case_count"],
                "merged_risk_atom_count": result["merged_risk_atom_count"],
                "vertical_handoff_status": result["vertical_handoff_status"],
                "inventory_depletion_status": result["inventory_depletion_status"],
                "facility_total_risk_available": result["facility_total_risk_available"],
                "output": str(args.output_dir.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
