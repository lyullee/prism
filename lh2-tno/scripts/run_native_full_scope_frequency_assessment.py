"""Run the declared native LH2 equipment scope with literature frequencies.

The input campaign already contains exact provider-resolved release packets for
the generic outdoor LH2 scope.  PRISM binds the generated literature event to
each request at execution, evaluates the full weather/population/consequence
chain, and writes one facility assessment with equipment, accident-family,
frequency-sensitivity, and timing ledgers.

This is an auditable diagnostic run.  It does not turn synthetic equipment or
operator-limited provider histories into qualified facility evidence.  Cases
with a numerical consequence result but an open/constant-state provider
boundary stay visible as ``EXECUTED_OPERATOR_LIMITED``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.accident_scope import MAJOR_ACCIDENT_FAMILIES, build_accident_scope_matrix  # noqa: E402
from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402
from lh2_tno.frequency import FrequencyEvent, FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.uncertainty import LiteratureFrequencyScenario  # noqa: E402


def _load_object(path: Path) -> dict[str, Any]:
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


def _load_backend(path: Path) -> BackendConfig:
    raw = _load_object(path)
    for package in raw.get("packages", []):
        if not isinstance(package, dict) or not isinstance(package.get("root"), str):
            raise ValueError("backend package roots must be declared")
        root = Path(package["root"])
        if not root.exists():
            raise FileNotFoundError(f"backend package root does not exist: {root}")
        # The source digest is recomputed at run time.  A changed external
        # model is therefore captured in this run's provenance or rejected by
        # IsolatedBackend before any result is accepted.
        package["sha256"] = tree_digest(root)
    return BackendConfig.model_validate_json(
        json.dumps(raw, ensure_ascii=False, allow_nan=False)
    )


def _asset_quantiles(
    events: tuple[FrequencyEvent, ...],
    quantile: str,
) -> dict[str, str]:
    assets = sorted({event.asset_id for event in events})
    rows_by_asset: dict[str, list[FrequencyEvent]] = {asset: [] for asset in assets}
    for event in events:
        rows_by_asset[event.asset_id].append(event)
    output: dict[str, str] = {}
    for asset, rows in rows_by_asset.items():
        if quantile == "published":
            output[asset] = "published"
        elif quantile == "p05":
            output[asset] = "p05" if all(
                event.marginal_p05_per_year is not None for event in rows
            ) else "fixed"
        elif quantile == "p95":
            output[asset] = "p95" if all(
                event.marginal_p95_per_year is not None for event in rows
            ) else "fixed"
        else:
            raise ValueError(f"unsupported literature quantile: {quantile}")
    return output


def _frequency_scenarios(events: tuple[FrequencyEvent, ...]) -> tuple[LiteratureFrequencyScenario, ...]:
    return tuple(
        LiteratureFrequencyScenario(
            id=identifier,
            asset_quantiles=_asset_quantiles(events, quantile),
            provenance=provenance,
        )
        for identifier, quantile, provenance in (
            (
                "native-full-scope-literature-central",
                "published",
                "published catalogue rates; conditional diagnostic only",
            ),
            (
                "native-full-scope-literature-low",
                "p05",
                "published marginal p05 bounds where available; fixed catalogue rates otherwise",
            ),
            (
                "native-full-scope-literature-high",
                "p95",
                "published marginal p95 bounds where available; fixed catalogue rates otherwise",
            ),
        )
    )


def _event_frequency_checks(result: dict[str, Any]) -> dict[str, Any]:
    events = {
        str(row["id"]): row
        for row in result.get("events", [])
        if isinstance(row, dict) and row.get("id")
    }
    atoms = [row for row in result.get("risk_atoms", []) if isinstance(row, dict)]
    mismatches = []
    for atom in atoms:
        event = events.get(str(atom.get("event_id")))
        if event is None or atom.get("initiating_frequency_per_year") != event.get(
            "annual_frequency_per_year"
        ):
            mismatches.append(str(atom.get("event_id")))
    return {
        "event_count": len(events),
        "risk_atom_count": len(atoms),
        "risk_atom_frequency_match_count": len(atoms) - len(mismatches),
        "risk_atom_frequency_mismatch_count": len(mismatches),
        "risk_atom_frequency_mismatch_event_ids": sorted(set(mismatches)),
        "frequency_is_taken_from_catalogue_event": not mismatches,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = EquipmentManifest.from_json(args.manifest)
    facility = manifest.to_facility()
    campaign = RiskCampaign.model_validate_json(
        args.campaign.read_text(encoding="utf-8")
    )
    backend_config = _load_backend(args.backend_config)
    events = generate_events(facility, campaign.frequency_plan)
    if len(events) != len(campaign.event_routes):
        raise ValueError("campaign route count does not match generated frequency events")

    started = time.perf_counter()
    result = ResearchPipeline(
        facility, IsolatedBackend(backend_config)
    ).facility_risk(campaign)
    runner_elapsed_ms = (time.perf_counter() - started) * 1000.0

    scope_matrix = build_accident_scope_matrix(
        campaign,
        result,
        manifest,
        required_families=MAJOR_ACCIDENT_FAMILIES,
    )
    scenarios = _frequency_scenarios(events)
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=tuple(component.id for component in facility.components),
        scope_matrices=(scope_matrix,),
        required_accident_families=MAJOR_ACCIDENT_FAMILIES,
        frequency_scenarios=scenarios,
    )

    statuses = [str(case.get("status", "UNKNOWN")) for case in result.get("cases", [])]
    executed_case_count = sum(status.startswith("EXECUTED") for status in statuses)
    fully_validated_case_count = sum(status == "EXECUTED" for status in statuses)
    operator_limited_case_count = sum(
        status == "EXECUTED_OPERATOR_LIMITED" for status in statuses
    )
    verification = {
        "schema_version": "prism.native_full_scope_frequency_assessment.v1",
        "status": "NATIVE_FULL_SCOPE_FREQUENCY_CAMPAIGN_EXECUTED_DIAGNOSTIC",
        "facility_id": facility.id,
        "configuration_origin": manifest.configuration_origin,
        "equipment_component_count": len(facility.components),
        "frequency_asset_count": len({event.asset_id for event in events}),
        "frequency_event_count": len(events),
        "campaign_case_count": len(result.get("cases", [])),
        "executed_case_count": executed_case_count,
        "fully_validated_case_count": fully_validated_case_count,
        "operator_limited_case_count": operator_limited_case_count,
        "strict_uncomputed_case_count": len(result.get("uncomputed_cases", [])),
        "risk_atom_count": len(result.get("risk_atoms", [])),
        "frequency_checks": _event_frequency_checks(result),
        "frequency_scenario_count": len(assessment.get("frequency_uncertainty", {}).get("scenarios", [])),
        "conditional_diagnostic_facility_risk_available": assessment.get(
            "conditional_diagnostic_facility_risk_available"
        ),
        "conditional_diagnostic_facility_annual_ir_low_high": assessment.get(
            "conditional_diagnostic_facility_annual_ir_low_high"
        ),
        "conditional_diagnostic_facility_expected_death_fn_low_high": assessment.get(
            "conditional_diagnostic_facility_expected_death_fn_low_high"
        ),
        "facility_total_risk_available": assessment.get("facility_total_risk_available"),
        "scope_matrix_status": scope_matrix.get("campaign_status"),
        "scope_matrix_complete": scope_matrix.get("matrix_complete"),
        "scope_matrix_blocking_reasons": scope_matrix.get("blocking_reasons", []),
        "timing": {
            "runner_elapsed_ms": runner_elapsed_ms,
            "campaign": result.get("timing"),
            "assessment": assessment.get("timing"),
        },
        "backend_config_digest": backend_config.digest(),
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "limitations": [
            "manifest and annual conditions are synthetic generic outdoor inputs",
            "literature rates are applied to generated events; no field-frequency or sensor-frequency learning is used",
            "19 cases have numerical outputs but remain EXECUTED_OPERATOR_LIMITED because the provider boundary is constant-state or otherwise open",
            "vertical handoff is retained as an explicit accident-family scope row and remains uncomputed in this campaign",
            "conditional IR/F-N is the sum of evaluated atoms and is not a qualified facility total or credible interval",
            "provider qualification and independent physical validation remain closed",
        ],
    }
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    _save(output / "facility.json", facility.model_dump(mode="json"))
    _save(output / "frequency_plan.json", campaign.frequency_plan.model_dump(mode="json"))
    _save(output / "campaign.json", campaign.model_dump(mode="json"))
    _save(output / "campaign_result.json", result)
    _save(output / "scope_matrix.json", scope_matrix)
    _save(
        output / "frequency_scenarios.json",
        {
            "schema_version": "prism.native_full_scope_frequency_scenarios.v1",
            "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
            "event_catalogue_digest": canonical_digest(
                [event.model_dump(mode="json") for event in events]
            ),
            "frequency_is_not_inferred": True,
            "facility_credible_interval": False,
        },
    )
    _save(output / "facility_assessment.json", assessment)
    _save(
        output / "binding_provenance.json",
        {
            "schema_version": "prism.native_full_scope_frequency_binding.v1",
            "campaign_id": campaign.id,
            "campaign_digest": campaign.digest(),
            "facility_digest": facility.digest(),
            "generated_event_count": len(events),
            "event_ids": [event.id for event in events],
            "frequency_plan_digest": campaign.frequency_plan.digest(),
            "backend_config_digest": backend_config.digest(),
            "frequency_source": "PRISM literature catalogue; bind_event during campaign execution",
            "frequency_from_provider_packet": False,
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "interpretation": (
                "Each native provider request is consumed by the same event route used by the "
                "frequency plan. The catalogue event supplies the initiating rate, while the "
                "provider packet supplies the release history; neither evidence class is silently substituted."
            ),
        },
    )
    _save(output / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ImportError, TypeError, ValueError) as error:
        raise SystemExit(f"native full-scope frequency assessment failed: {error}") from error
    print(
        json.dumps(
            {
                "status": result["status"],
                "facility_id": result["facility_id"],
                "frequency_event_count": result["frequency_event_count"],
                "campaign_case_count": result["campaign_case_count"],
                "executed_case_count": result["executed_case_count"],
                "operator_limited_case_count": result["operator_limited_case_count"],
                "risk_atom_count": result["risk_atom_count"],
                "conditional_diagnostic_facility_risk_available": result[
                    "conditional_diagnostic_facility_risk_available"
                ],
                "facility_total_risk_available": result["facility_total_risk_available"],
                "output": str(args.output_dir.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
