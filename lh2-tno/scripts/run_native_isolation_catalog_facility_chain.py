"""Run a native LH2 isolation catalog through the facility consequence chain.

The catalog builder creates exact equipment release packets, while this runner
rebounds those packets into a campaign and evaluates the existing outdoor
SLABx-LH2/SLABx, ignition, population, and IR/F-N path.  The output is a
diagnostic facility ledger: synthetic packets, operator-limited boundaries,
missing qualification, and missing independent validation remain explicit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.accident_scope import MAJOR_ACCIDENT_FAMILIES, build_accident_scope_matrix  # noqa: E402
from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.campaign_packet_rebind import (  # noqa: E402
    packet_rebind_provenance,
    rebind_campaign_to_worklist_packets,
)
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402
from lh2_tno.frequency import FrequencyEvent, generate_events  # noqa: E402
from lh2_tno.native_packet_campaign import (  # noqa: E402
    build_native_packet_campaign_execution_ledger,
)
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_worklist import build_provider_release_worklist  # noqa: E402
from lh2_tno.uncertainty import LiteratureFrequencyScenario  # noqa: E402


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _harm_diagnostic(result: dict[str, Any]) -> dict[str, Any]:
    """Summarise receptor harm without treating a zero result as no risk."""
    atoms = result.get("risk_atoms", [])
    positive = 0
    zero = 0
    for atom in atoms if isinstance(atoms, list) else []:
        receptor_harm = atom.get("receptor_harm_low_high") if isinstance(atom, dict) else None
        values: list[float] = []
        if isinstance(receptor_harm, dict):
            for pair in receptor_harm.values():
                if isinstance(pair, list):
                    values.extend(
                        float(value)
                        for value in pair
                        if isinstance(value, (int, float))
                    )
        if any(value > 0.0 for value in values):
            positive += 1
        elif values:
            zero += 1
    cases = result.get("cases", [])
    domain_truncated = 0
    flammability_proven = 0
    for case in cases if isinstance(cases, list) else []:
        domain = case.get("domain_assessment") if isinstance(case, dict) else None
        if not isinstance(domain, dict):
            continue
        if domain.get("domain_truncated") is True:
            domain_truncated += 1
        if domain.get("outside_domain_flammability_proven_at_ignition") is True:
            flammability_proven += 1
    if positive:
        status = "NONZERO_RECEPTOR_HARM_REACHED"
        interpretation = (
            "At least one executed risk atom reached a declared receptor harm endpoint. "
            "This is a conditional diagnostic contribution; it is not a qualified facility total."
        )
    elif domain_truncated:
        status = "ZERO_RECEPTOR_HARM_WITH_DOMAIN_LIMITS"
        interpretation = (
            "All saved receptor harm values are zero, but one or more consequence domains were "
            "truncated. The zero values must not be interpreted as zero facility risk."
        )
    else:
        status = "ZERO_RECEPTOR_HARM_AT_DECLARED_RECEPTORS"
        interpretation = (
            "All saved receptor harm values are zero at the declared receptors for the executed "
            "conditions. This is a conditional model result, not a claim of zero facility risk."
        )
    return {
        "status": status,
        "risk_atom_count": len(atoms) if isinstance(atoms, list) else 0,
        "positive_receptor_harm_atom_count": positive,
        "zero_receptor_harm_atom_count": zero,
        "domain_truncated_case_count": domain_truncated,
        "outside_domain_flammability_proven_case_count": flammability_proven,
        "zero_is_not_zero_facility_risk": True,
        "interpretation": interpretation,
    }


def _backend(path: Path) -> BackendConfig:
    raw = _object(path)
    for package in raw.get("packages", []):
        if not isinstance(package, dict) or not isinstance(package.get("root"), str):
            raise ValueError("backend package roots must be declared")
        root = Path(package["root"])
        if not root.exists():
            raise FileNotFoundError(f"backend package root does not exist: {root}")
        package["sha256"] = tree_digest(root)
    return BackendConfig.model_validate_json(
        json.dumps(raw, ensure_ascii=False, allow_nan=False)
    )


def _asset_quantiles(events: tuple[FrequencyEvent, ...], quantile: str) -> dict[str, str]:
    rows_by_asset: dict[str, list[FrequencyEvent]] = {}
    for event in events:
        rows_by_asset.setdefault(event.asset_id, []).append(event)
    output: dict[str, str] = {}
    for asset, rows in rows_by_asset.items():
        if quantile == "published":
            output[asset] = "published"
        elif quantile == "p05":
            output[asset] = "p05" if all(row.marginal_p05_per_year is not None for row in rows) else "fixed"
        elif quantile == "p95":
            output[asset] = "p95" if all(row.marginal_p95_per_year is not None for row in rows) else "fixed"
        else:
            raise ValueError(f"unsupported frequency quantile: {quantile}")
    return output


def _frequency_scenarios(events: tuple[FrequencyEvent, ...]) -> tuple[LiteratureFrequencyScenario, ...]:
    return tuple(
        LiteratureFrequencyScenario(
            id=f"native-isolation-catalog-literature-{quantile}",
            asset_quantiles=_asset_quantiles(events, quantile),
            provenance=(
                "PRISM literature catalogue rates; native isolation catalog facility-chain "
                "diagnostic only"
            ),
        )
        for quantile in ("published", "p05", "p95")
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = EquipmentManifest.from_json(args.manifest)
    facility = manifest.to_facility()
    source_campaign = _object(args.campaign)
    packet_evidence = _object(args.catalog_dir / "native_scope_packet_evidence.json")
    isolation_audit = _object(args.catalog_dir / "isolation_branch_audit.json")
    state_snapshot_audit = _object(args.catalog_dir / "state_snapshot_binding_audit.json")
    rebound_payload = rebind_campaign_to_worklist_packets(
        source_campaign,
        packet_evidence,
        packet_root=args.catalog_dir,
    )
    campaign = RiskCampaign.model_validate_json(
        json.dumps(rebound_payload, ensure_ascii=False, allow_nan=False)
    )
    backend_config = _backend(args.backend_config)
    events = generate_events(facility, campaign.frequency_plan)
    provider_worklist = build_provider_release_worklist(manifest, campaign.frequency_plan)
    result = ResearchPipeline(facility, IsolatedBackend(backend_config)).facility_risk(campaign)
    harm_diagnostic = _harm_diagnostic(result)
    scope_matrix = build_accident_scope_matrix(
        campaign,
        result,
        manifest,
        required_families=MAJOR_ACCIDENT_FAMILIES,
        provider_worklist=provider_worklist,
    )
    scenarios = _frequency_scenarios(events)
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=tuple(component.id for component in facility.components),
        scope_matrices=(scope_matrix,),
        required_accident_families=MAJOR_ACCIDENT_FAMILIES,
        frequency_scenarios=scenarios,
    )
    provenance = packet_rebind_provenance(
        packet_evidence,
        [route.event_id for route in campaign.event_routes],
    )
    execution_ledger = build_native_packet_campaign_execution_ledger(
        source_campaign,
        result,
        provenance,
        state_snapshot_audit,
    )
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "facility.json", facility.model_dump(mode="json"))
    _write(output / "campaign.json", campaign.model_dump(mode="json"))
    _write(output / "campaign_result.json", result)
    _write(output / "provider_worklist.json", provider_worklist)
    _write(output / "scope_matrix.json", scope_matrix)
    _write(
        output / "frequency_scenarios.json",
        {
            "schema_version": "prism.native_isolation_catalog_frequency_scenarios.v1",
            "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
            "event_catalogue_digest": canonical_digest(
                [event.model_dump(mode="json") for event in events]
            ),
            "frequency_inference_performed": False,
            "facility_credible_interval": False,
        },
    )
    _write(output / "facility_assessment.json", assessment)
    _write(output / "packet_rebind_provenance.json", provenance)
    _write(output / "native_packet_campaign_execution_ledger.json", execution_ledger)
    _write(
        output / "verification.json",
        {
            "schema_version": "prism.native_isolation_catalog_facility_chain.v1",
            "status": "NATIVE_ISOLATION_CATALOG_FACILITY_CHAIN_EXECUTED_DIAGNOSTIC",
            "facility_id": facility.id,
            "catalog_record": str(args.catalog_dir / "isolation_branch_audit.json"),
            "packet_evidence_record": str(args.catalog_dir / "native_scope_packet_evidence.json"),
            "state_snapshot_audit_record": str(args.catalog_dir / "state_snapshot_binding_audit.json"),
            "frequency_event_count": len(events),
            "exact_native_packet_count": packet_evidence.get("exact_event_count"),
            "uncomputed_packet_event_count": len(packet_evidence.get("blocking_event_ids", [])),
            "isolation_success_count": isolation_audit.get("isolation_success_count"),
            "isolation_success_by_component": isolation_audit.get("isolation_success_by_component"),
            "state_snapshot_binding_status": isolation_audit.get("state_snapshot_binding_status"),
            "campaign_case_count": len(result.get("cases", [])),
            "campaign_case_status_counts": execution_ledger.get("status_counts"),
            "risk_atom_count": len(result.get("risk_atoms", [])),
            "conditional_diagnostic_facility_risk_available": assessment.get(
                "conditional_diagnostic_facility_risk_available"
            ),
            "conditional_diagnostic_facility_annual_ir_low_high": assessment.get(
                "conditional_diagnostic_facility_annual_ir_low_high"
            ),
            "conditional_diagnostic_facility_expected_death_fn_low_high": assessment.get(
                "conditional_diagnostic_facility_expected_death_fn_low_high"
            ),
            "conditional_diagnostic_facility_expected_death_fn_diagnostics": assessment.get(
                "conditional_diagnostic_facility_expected_death_fn_diagnostics"
            ),
            "facility_assessment_status": assessment.get("status"),
            "harm_diagnostic": harm_diagnostic,
            "receptor_geometry": {
                "receptor_ids": [receptor.id for receptor in facility.receptors],
                "receptor_positions_enu_m": [
                    list(receptor.position_enu_m) for receptor in facility.receptors
                ],
                "interpretation": "declared diagnostic geometry; not a site survey",
            },
            "conditional_diagnostic_facility_coverage": assessment.get(
                "conditional_diagnostic_facility_coverage"
            ),
            "timing": result.get("timing"),
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "limitations": [
                "catalog packets and facility geometry are synthetic diagnostic inputs",
                "operator-limited or domain-incomplete release boundaries remain withheld from strict QRA",
                "literature rates are inputs; field-frequency and sensor-frequency learning are not used",
                "qualified provider evidence and independent physical validation remain absent",
                "conditional facility IR/F-N is not a qualified facility total",
            ],
        },
    )
    return {
        "status": assessment.get("status"),
        "output_dir": str(output),
        "facility_id": facility.id,
        "frequency_event_count": len(events),
        "campaign_case_count": len(result.get("cases", [])),
        "risk_atom_count": len(result.get("risk_atoms", [])),
        "conditional_diagnostic_facility_risk_available": assessment.get(
            "conditional_diagnostic_facility_risk_available"
        ),
        "harm_diagnostic": harm_diagnostic,
        "facility_total_risk_available": assessment.get("facility_total_risk_available"),
        "provider_packet_promoted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--catalog-dir", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"native isolation catalog facility chain failed: {error}") from error
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
