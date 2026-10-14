"""Run a facility campaign after rebinding one event to a compressible handoff.

The campaign owns initiating frequencies and annual weather conditions.  The
provider handoff owns the release history and near-field carrier section.  This
runner joins those contracts, executes the existing facility risk engine, and
writes a diagnostic native-packet ledger without promoting provider, physical,
or complete-facility-QRA claims.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.campaign_packet_rebind import (  # noqa: E402
    rebind_campaign_to_compressible_handoff,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.native_packet_campaign import (  # noqa: E402
    build_native_packet_campaign_execution_ledger,
)
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.uncertainty import (  # noqa: E402
    LiteratureFrequencyScenario,
    literature_frequency_uncertainty,
)


class CompressiblePlaneFacilityCampaignError(ValueError):
    """Raised when campaign and handoff contracts cannot be joined safely."""


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompressiblePlaneFacilityCampaignError(f"cannot read JSON {path}: {error}") from error


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _load_frequency_scenarios(path: Path) -> tuple[LiteratureFrequencyScenario, ...]:
    raw = _load(path)
    rows = raw.get("scenarios") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise CompressiblePlaneFacilityCampaignError(
            "frequency scenario input must contain a non-empty scenarios array"
        )
    try:
        return tuple(LiteratureFrequencyScenario.model_validate(row) for row in rows)
    except (TypeError, ValueError) as error:
        raise CompressiblePlaneFacilityCampaignError(
            f"frequency scenario input failed strict validation: {error}"
        ) from error


def load_backend(path: Path, *, refresh_pins: bool) -> tuple[BackendConfig, list[dict[str, str]]]:
    raw = _load(path)
    if not isinstance(raw, dict):
        raise CompressiblePlaneFacilityCampaignError("backend config must be an object")
    refreshed: list[dict[str, str]] = []
    for package in raw.get("packages", []):
        if not isinstance(package, dict):
            raise CompressiblePlaneFacilityCampaignError("backend package pins must be objects")
        root = Path(str(package.get("root", "")))
        if not root.exists():
            raise CompressiblePlaneFacilityCampaignError(f"backend package root does not exist: {root}")
        if refresh_pins:
            old = str(package.get("sha256"))
            new = tree_digest(root)
            package["sha256"] = new
            if old != new:
                refreshed.append({"name": str(package.get("name", "")), "old": old, "new": new})
    try:
        config = BackendConfig.model_validate_json(json.dumps(raw, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise CompressiblePlaneFacilityCampaignError(f"backend config failed validation: {error}") from error
    return config, refreshed


def run(
    manifest_path: Path,
    campaign_path: Path,
    handoff_path: Path,
    event_id: str,
    backend_config_path: Path,
    output_path: Path,
    provenance_path: Path,
    ledger_path: Path,
    *,
    refresh_pins: bool = False,
    frequency_scenarios_path: Path | None = None,
    frequency_output_path: Path | None = None,
) -> dict[str, Any]:
    try:
        manifest = EquipmentManifest.from_json(manifest_path)
        campaign_raw = _load(campaign_path)
        if not isinstance(campaign_raw, dict):
            raise CompressiblePlaneFacilityCampaignError("campaign must be an object")
        handoff = _load(handoff_path)
        if not isinstance(handoff, dict):
            raise CompressiblePlaneFacilityCampaignError("handoff packet must be an object")
        rebound_campaign, provenance = rebind_campaign_to_compressible_handoff(
            campaign_raw, handoff, event_id=event_id
        )
        campaign = RiskCampaign.model_validate_json(
            json.dumps(rebound_campaign, ensure_ascii=False, allow_nan=False)
        )
        config, refreshed_pins = load_backend(backend_config_path, refresh_pins=refresh_pins)
    except (TypeError, ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompressiblePlaneFacilityCampaignError(f"campaign binding failed: {error}") from error

    facility = manifest.to_facility()
    result = ResearchPipeline(facility, IsolatedBackend(config)).facility_risk(campaign)
    ledger = build_native_packet_campaign_execution_ledger(
        rebound_campaign,
        result,
        provenance=provenance,
    )
    handoff_summary = ledger.get("compressible_handoff_rebind")
    if not isinstance(handoff_summary, dict) or handoff_summary.get("consumed") is not True:
        raise CompressiblePlaneFacilityCampaignError(
            "facility campaign result did not preserve the compressible handoff ledger"
        )
    frequency_report = None
    if frequency_scenarios_path is not None:
        scenarios = _load_frequency_scenarios(frequency_scenarios_path)
        try:
            frequency_report = literature_frequency_uncertainty(result, scenarios)
        except (TypeError, ValueError, KeyError) as error:
            raise CompressiblePlaneFacilityCampaignError(
                f"frequency uncertainty could not be bound to this campaign: {error}"
            ) from error
        if frequency_output_path is None:
            frequency_output_path = output_path.with_name(
                f"{output_path.stem}.frequency_uncertainty.json"
            )
        _save(frequency_output_path, frequency_report)
    output_summary = {
        "status": "COMPRESSIBLE_PLANE_FACILITY_CAMPAIGN_EXECUTED_DIAGNOSTIC",
        "facility_result_status": result.get("status"),
        "facility_id": result.get("facility_id"),
        "campaign_id": rebound_campaign.get("id"),
        "handoff_event_id": event_id,
        "handoff_consumed": True,
        "event_count": len(result.get("events", [])) if isinstance(result.get("events"), list) else None,
        "case_count": len(result.get("cases", [])) if isinstance(result.get("cases"), list) else None,
        "uncomputed_case_count": len(result.get("uncomputed_cases", [])) if isinstance(result.get("uncomputed_cases"), list) else None,
        "case_statuses": dict(Counter(
            str(case.get("status", "UNKNOWN"))
            for case in result.get("cases", [])
            if isinstance(case, dict)
        )),
        "known_contribution_annual_ir_low_high": result.get("known_contribution_annual_ir_low_high"),
        "total_facility_annual_ir_low_high": result.get("total_facility_annual_ir_low_high"),
        "total_facility_expected_death_fn_low_high": result.get("total_facility_expected_death_fn_low_high"),
        "timing": result.get("timing"),
        "backend_pin_refresh": refreshed_pins,
        "provider_packet_promoted": False,
        "frequency_inference": False,
        "physical_validation_claim": False,
        "facility_qra_claim": result.get("complete_facility_qra_claim") is True,
        "complete_facility_qra_claim": result.get("complete_facility_qra_claim") is True,
        "operator_limited": ledger.get("operator_limited_case_count", 0) > 0,
        "frequency_uncertainty": (
            {
                "scenario_count": len(frequency_report.get("scenarios", [])),
                "output": str(frequency_output_path),
                "fresh_physics_executed": frequency_report.get("fresh_physics_executed"),
                "facility_credible_interval": frequency_report.get("facility_credible_interval"),
                "correlation_comparison_present": frequency_report.get("correlation_comparison_present"),
                "frequency_inference_performed": frequency_report.get("frequency_inference_performed", False),
            }
            if frequency_report is not None
            else None
        ),
        "limitations": [
            "campaign frequencies remain explicit literature/synthetic inputs; the provider packet supplies no rate",
            "the handoff is diagnostic and not independently physically validated",
            "facility totals remain withheld when provider qualification or scope gates are open",
        ],
    }
    _save(output_path, result)
    _save(provenance_path, provenance)
    _save(ledger_path, ledger)
    return output_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--handoff-packet", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance-output", type=Path, required=True)
    parser.add_argument("--ledger-output", type=Path, required=True)
    parser.add_argument(
        "--frequency-scenarios",
        type=Path,
        help="optional exact campaign-scoped literature-frequency scenario catalog",
    )
    parser.add_argument(
        "--frequency-uncertainty-output",
        type=Path,
        help="optional output path for the no-fresh-physics frequency reweighting report",
    )
    parser.add_argument("--refresh-pins", action="store_true")
    args = parser.parse_args()
    try:
        summary = run(
            args.manifest,
            args.campaign,
            args.handoff_packet,
            args.event_id,
            args.backend_config,
            args.output,
            args.provenance_output,
            args.ledger_output,
            refresh_pins=args.refresh_pins,
            frequency_scenarios_path=args.frequency_scenarios,
            frequency_output_path=args.frequency_uncertainty_output,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CompressiblePlaneFacilityCampaignError) as error:
        print(json.dumps({"status": "COMPRESSIBLE_PLANE_FACILITY_CAMPAIGN_BLOCKED", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
