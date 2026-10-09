"""Merge the native general-LH2 campaign with the vertical-handoff diagnostic.

The base 24-event campaign and the five-event vertical-handoff campaign are
independent diagnostic ledgers.  This script rebinds the vertical result into
the base facility namespace, remaps its event IDs, merges the facility ledger
and accident-family matrix, and reweights the saved atoms with the same
literature-frequency scenarios.  It never promotes the synthetic handoff or
creates a facility-QRA claim.
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
from lh2_tno.facility_evidence_request import build_facility_evidence_request  # noqa: E402
from lh2_tno.facility_ledger import merge_facility_campaign_results  # noqa: E402
from lh2_tno.scope_matrix_merge import merge_scope_matrices  # noqa: E402
from lh2_tno.uncertainty import LiteratureFrequencyScenario  # noqa: E402
from lh2_tno.vertical_handoff_campaign import (  # noqa: E402
    rebind_vertical_handoff_campaign_result,
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
        elif isinstance(item.get("event_quantiles"), dict):
            for area in ("AREA_0.01%", "AREA_0.1%", "AREA_1%", "AREA_10%", "AREA_100%"):
                item["event_quantiles"][
                    f"generic-lh2-near-receptor-diagnostic/vertical-handoff/terminal-valve/{area}"
                ] = "published"
        else:
            raise ValueError(f"frequency scenario {index} has no quantile map")
        provenance = str(item.get("provenance", "")).strip()
        suffix = "vertical handoff fixed at declared diagnostic rate; no frequency inference"
        item["provenance"] = f"{provenance}; {suffix}" if provenance else suffix
        scenarios.append(LiteratureFrequencyScenario.model_validate(item))
    return tuple(scenarios)


def run(args: argparse.Namespace) -> dict[str, Any]:
    base_dir = args.base_dir
    base_result = _load(base_dir / "campaign_result.json")
    base_facility = _load(base_dir / "facility.json")
    base_scope = _load(base_dir / "scope_matrix.json")
    base_frequency_scenarios = _load(base_dir / "frequency_scenarios.json")
    vertical_source = _load(args.vertical_result)
    vertical_scope_source = _load(args.vertical_scope_matrix)

    facility_id = str(base_result.get("facility_id", "")).strip()
    if not facility_id:
        raise ValueError("base campaign result has no facility_id")
    namespace = f"{facility_id}/vertical-handoff"
    vertical_result = rebind_vertical_handoff_campaign_result(
        vertical_source,
        facility_id=facility_id,
        namespace=namespace,
        asset_id="vertical-handoff-vent",
        component_id="vertical-handoff-terminal-pipe-01",
        receptor_map={"worker-01": "worker-01"},
    )
    vertical_scope = _rebind_vertical_scope_matrix(
        vertical_scope_source,
        facility_id=facility_id,
        namespace=namespace,
    )

    expected_components = tuple(
        str(component["id"]) for component in base_facility.get("components", [])
    ) + ("vertical-handoff-terminal-pipe-01",)
    merged = merge_facility_campaign_results(
        [base_result, vertical_result],
        expected_component_ids=expected_components,
        scope_matrices=[base_scope, vertical_scope],
        required_accident_families=MAJOR_ACCIDENT_FAMILIES,
    )
    merged_scope = merge_scope_matrices(
        [base_scope, vertical_scope],
        facility_id=facility_id,
        required_families=MAJOR_ACCIDENT_FAMILIES,
    )
    scenarios = _extend_frequency_scenarios(base_frequency_scenarios)
    assessment = build_facility_assessment(
        [base_result, vertical_result],
        expected_component_ids=expected_components,
        scope_matrices=[base_scope, vertical_scope],
        required_accident_families=MAJOR_ACCIDENT_FAMILIES,
        frequency_scenarios=scenarios,
    )
    evidence_request = build_facility_evidence_request(assessment, merged_scope)

    vertical_row = next(
        row for row in merged_scope["rows"] if row["family"] == "vertical_handoff"
    )
    verification = {
        "schema_version": "prism.native_full_scope_union_assessment.v1",
        "status": "NATIVE_FULL_SCOPE_UNION_DIAGNOSTIC",
        "facility_id": facility_id,
        "base_event_count": len(base_result.get("events", [])),
        "vertical_event_count": len(vertical_result.get("events", [])),
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
        "conditional_diagnostic_facility_risk_available": assessment[
            "conditional_diagnostic_facility_risk_available"
        ],
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
        "facility_evidence_request_status": evidence_request["status"],
        "facility_evidence_request_family_count": len(evidence_request["family_requests"]),
        "facility_evidence_request_case_count": evidence_request["case_request_count"],
        "facility_evidence_request_promotion_allowed": (
            assessment["complete_facility_qra_claim"] is True
        ),
        "limitations": [
            "vertical handoff is a namespaced diagnostic campaign, not a new qualified provider packet",
            "vertical provider history is synthetic/operator-limited and retains its termination horizon",
            "the merged conditional IR/F-N is diagnostic and facility total IR/F-N remains withheld",
            "frequency scenarios reweight saved atoms and do not infer vertical frequency",
        ],
    }
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    _save(output / "campaign_result.json", merged)
    _save(output / "vertical_handoff_rebound_result.json", vertical_result)
    _save(output / "scope_matrix.json", merged_scope)
    _save(
        output / "frequency_scenarios.json",
        {
            "schema_version": "prism.native_full_scope_union_frequency_scenarios.v1",
            "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
            "vertical_handoff_frequency_inference": False,
            "facility_credible_interval": False,
        },
    )
    _save(output / "facility_assessment.json", assessment)
    _save(output / "facility_evidence_request.json", evidence_request)
    _save(output / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--vertical-result", type=Path, required=True)
    parser.add_argument("--vertical-scope-matrix", type=Path, required=True)
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
                "facility_total_risk_available": result["facility_total_risk_available"],
                "output": str(args.output_dir.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
