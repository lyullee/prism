"""Convert exact provider-chain evidence into generic quantitative attachments.

This adapter only reshapes already-produced evidence into the four-block
contract consumed by ``run_generic_facility_hazop_handoff.py``.  It never
creates a release, reweights a frequency, or upgrades a diagnostic result to a
qualified facility QRA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _payloads(attachment: Mapping[str, Any]) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    raw = attachment.get("provider_evidence")
    rows = raw if isinstance(raw, list) else [raw]
    result: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("provider_evidence rows must be objects")
        identity = row.get("exact_identity")
        if not isinstance(identity, Mapping):
            raise ValueError("provider evidence is missing exact_identity")
        key = (
            str(identity.get("component_id") or ""),
            str(identity.get("operating_mode") or ""),
            str(identity.get("hazop_scenario_family") or ""),
        )
        if any(not value for value in key) or key in result:
            raise ValueError("provider evidence identities must be unique and complete")
        result[key] = row
    return result


def _attachment(row: Mapping[str, Any], *, path: str) -> dict[str, Any]:
    identity = row["exact_identity"]
    boundary = row.get("release_boundary") if isinstance(row.get("release_boundary"), Mapping) else {}
    balance = boundary.get("provider_mass_balance") if isinstance(boundary.get("provider_mass_balance"), Mapping) else {}
    frequency = row.get("frequency_binding") if isinstance(row.get("frequency_binding"), Mapping) else {}
    chain = row.get("consequence_chain") if isinstance(row.get("consequence_chain"), Mapping) else {}
    timing = row.get("timing") if isinstance(row.get("timing"), Mapping) else {}
    weather = str(frequency.get("annual_condition_id") or "synthetic-generic-worker-west-3ms")
    annual = frequency.get("initiating_frequency_per_year")
    return {
        "path": path,
        "evidence": {
            "provider_release_packet": {
                "status": "PROVIDER_RELEASE_EVIDENCE_ATTACHED",
                "source_digest": identity.get("provider_source_digest") or row.get("source_sha256"),
                "release_start_s": 0.0,
                "release_end_s": boundary.get("duration_s"),
                "duration_s": boundary.get("duration_s"),
                "termination_basis": boundary.get("termination_basis"),
                "isolation_time_s": balance.get("isolation_time_s", boundary.get("duration_s")),
                "post_isolation_observation_s": balance.get("post_isolation_observation_s", 0.0),
                "inventory_initial_kg": balance.get("initial_mass_kg", boundary.get("available_mass_kg")),
                "inventory_out_kg": boundary.get("cumulative_mass_out_kg"),
                "mass_residual_kg": boundary.get("mass_residual_kg"),
                "inventory_status": boundary.get("inventory_status"),
            },
            "frequency_binding": {
                "status": "LITERATURE_FREQUENCY_BOUND_DIAGNOSTIC",
                "literature_event_id": identity.get("provider_event_id"),
                "annual_frequency": annual,
                "annual_frequency_low": annual,
                "annual_frequency_high": annual,
                "source_provenance": frequency.get("frequency_source"),
                "frequency_inference_performed": False,
            },
            "slabx_lh2_consequence": {
                "status": "SLABX_LH2_CHAIN_EVIDENCE_ATTACHED",
                "result_digest": identity.get("provider_result_digest"),
                "weather_condition_id": weather,
                "ignition_branch_id": "provider-chain-multi-branch",
                "receptor_damage_or_harm_outputs": {
                    "stages": chain.get("stages", []),
                    "full_chain_executed": chain.get("full_chain_executed", False),
                    "physical_validation_claim": chain.get("physical_validation_claim", False),
                },
                "processing_time_ms": timing.get("wall_elapsed_ms"),
            },
            "facility_condition_binding": {
                "status": "CONDITIONAL_FACILITY_CONDITION_BOUND",
                "population_condition_id": weather,
                "weather_condition_id": weather,
                "ignition_branch_id": "provider-chain-multi-branch",
                "facility_port_or_endpoint_id": identity.get("provider_port_id"),
                "facility_ir_fn_available": False,
                "facility_qra_promotion": False,
            },
        },
        "provenance": {
            "source_record": row.get("source_record"),
            "provider_event_id": identity.get("provider_event_id"),
            "component_id": identity.get("component_id"),
            "operating_mode": identity.get("operating_mode"),
            "scenario_family": identity.get("hazop_scenario_family"),
            "diagnostic_only": True,
        },
    }


def build(attachment: Mapping[str, Any]) -> dict[str, Any]:
    matched = attachment.get("matched_requests")
    if not isinstance(matched, list):
        raise ValueError("attachment.matched_requests must be an array")
    payloads = _payloads(attachment)
    current: dict[str, Any] = {}
    forecast: dict[str, Any] = {}
    for match in matched:
        if not isinstance(match, Mapping):
            raise ValueError("matched request rows must be objects")
        key = (str(match.get("component_id") or ""), str(match.get("operating_mode") or ""), str(match.get("scenario_family") or ""))
        if key not in payloads:
            raise ValueError(f"missing provider evidence for matched request: {key}")
        path = str(match.get("path") or "")
        target = current if path == "current" else forecast if path == "forecast" else None
        if target is None:
            raise ValueError(f"unsupported matched request path: {path}")
        request_id = str(match.get("request_id") or "")
        if not request_id or request_id in target:
            raise ValueError("matched request IDs must be unique per path")
        target[request_id] = _attachment(payloads[key], path=path)
    return {
        "schema_version": "prism.generic_quantitative_attachments.v1",
        "current_attachments": current,
        "forecast_attachments": forecast,
        "summary": {
            "current_attachment_count": len(current),
            "forecast_attachment_count": len(forecast),
            "total_attachment_count": len(current) + len(forecast),
        },
        "policy": {
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "missing_cases_assigned_zero": False,
            "provider_qualification_claim": False,
            "physical_validation_claim": False,
            "facility_ir_fn_claim": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attachment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--current-output", type=Path)
    parser.add_argument("--forecast-output", type=Path)
    args = parser.parse_args()
    result = build(_load(args.attachment))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for path, key in ((args.current_output, "current_attachments"), (args.forecast_output, "forecast_attachments")):
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result[key], ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "BUILT", **result["summary"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
