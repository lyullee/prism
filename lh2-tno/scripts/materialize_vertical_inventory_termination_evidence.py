"""Materialize vertical inventory-handoff results as termination evidence packets.

The vertical consequence run already carries provider result digests and a
finite inventory ledger.  This command writes the small storage-catalog shape
consumed by the release-boundary auditor, preserving the source provider
response and explicitly marking the handoff as synthetic and unvalidated.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _safe_name(event_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", event_id).strip("_") or "event"


def _source_id(event_id: str) -> str:
    marker = "/terminal-valve/"
    if marker not in event_id:
        raise ValueError(f"vertical event has no terminal-valve suffix: {event_id}")
    suffix = event_id.split(marker, 1)[1]
    return f"equipment-inventory-campaign/terminal_pipe_asset/{suffix}"


def _first_case_by_event(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for case in result.get("cases", []):
        if not isinstance(case, dict):
            continue
        event_id = case.get("event_id")
        if isinstance(event_id, str) and event_id and event_id not in output:
            output[event_id] = case
    return output


def materialize(
    *,
    rebound_result_path: Path,
    provider_responses_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    result = _load(rebound_result_path)
    provider_responses = _load(provider_responses_path)
    by_event = _first_case_by_event(result)
    events = result.get("events", [])
    if not isinstance(events, list) or not events:
        raise ValueError("rebound result has no events")
    written: list[str] = []
    errors: list[str] = []
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("id"), str):
            errors.append("event row has no string id")
            continue
        event_id = event["id"]
        case = by_event.get(event_id)
        if case is None:
            errors.append(f"{event_id}: no case row")
            continue
        identity = case.get("provider_packet_identity")
        if not isinstance(identity, dict):
            errors.append(f"{event_id}: provider packet identity is missing")
            continue
        source_id = _source_id(event_id)
        source_response = provider_responses.get(source_id)
        if not isinstance(source_response, dict):
            errors.append(f"{event_id}: source provider response {source_id} is missing")
            continue
        data = source_response.get("data")
        if not isinstance(data, dict):
            errors.append(f"{event_id}: source provider response has no data object")
            continue
        provider_digest = identity.get("provider_result_digests", [None])[0]
        if not isinstance(provider_digest, str) or not provider_digest:
            errors.append(f"{event_id}: provider result digest is missing")
            continue
        event_dir = output_dir / "events" / _safe_name(event_id)
        event_dir.mkdir(parents=True, exist_ok=True)
        packet = {
            "provider_export_schema": "prism.resolved_release.v1",
            "event_id": event_id,
            "component_id": identity.get("component_id"),
            "port_id": (identity.get("port_ids") or [None])[0],
            "provider_source_digest": (identity.get("provider_source_digests") or [None])[0],
            "provider_result_digest": provider_digest,
            "termination_basis": "inventory_depletion_positive_threshold",
            "termination_provenance": identity.get("termination_provenances", [None])[0],
            "available_mass_kg": data.get("available_mass_kg"),
            "cumulative_mass_out_kg": data.get("cumulative_mass_out_kg"),
            "duration_s": (identity.get("duration_s") or [None])[0],
            "provider_mass_balance": {
                "initial_mass_kg": data.get("available_mass_kg"),
                "cumulative_mass_out_kg": data.get("cumulative_mass_out_kg"),
                "final_mass_kg": data.get("remaining_inventory_kg"),
                "max_abs_mass_residual_kg": data.get("max_total_mass_residual_kg"),
            },
            "input_origin": "synthetic",
            "vertical_handoff_provenance": (
                "provider inventory-depletion packet rebound to a vertical outlet; "
                "handoff is synthetic and not independently validated"
            ),
        }
        provider_meta = {
            "provider_result_digest": provider_digest,
            "termination_basis": "inventory_depletion_positive_threshold",
            "available_mass_kg": data.get("available_mass_kg"),
            "cumulative_mass_out_kg": data.get("cumulative_mass_out_kg"),
            "threshold_mass_kg": data.get("depletion_threshold_kg"),
            "remaining_mass_kg": data.get("remaining_inventory_kg"),
            "max_abs_mass_residual_kg": data.get("max_total_mass_residual_kg"),
            "mass_residual_max_kg": data.get("max_total_mass_residual_kg"),
            "duration_s": (identity.get("duration_s") or [None])[0],
            "operator_limited": True,
            "physical_validation_claim": False,
            "status": case.get("status"),
            "source_provider_event_id": source_id,
            "source_provider_termination_basis": data.get("termination_basis"),
            "vertical_handoff_validation": "NOT_SUPPLIED",
        }
        verification = {
            "schema_version": "prism.vertical_inventory_termination_evidence.v1",
            "provider_result_digest": provider_digest,
            "provider_run_meta": provider_meta,
            "physical_validation_claim": False,
            "provider_qualification_claim": False,
            "facility_qra_claim": False,
            "source_provider_response": str(provider_responses_path),
            "source_provider_event_id": source_id,
        }
        (event_dir / "resolved_release.json").write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (event_dir / "provider_response.json").write_text(
            json.dumps(source_response, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (event_dir / "verification.json").write_text(
            json.dumps(verification, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        written.append(event_id)
    report = {
        "schema_version": "prism.vertical_inventory_termination_evidence_materialization.v1",
        "status": "MATERIALIZED" if written and not errors else "PARTIAL",
        "event_count": len(written),
        "event_ids": written,
        "errors": errors,
        "source_rebound_result": str(rebound_result_path),
        "source_provider_responses": str(provider_responses_path),
        "output_dir": str(output_dir),
        "provider_qualification_claim": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "policy": (
            "termination evidence is provider-owned finite inventory accounting; "
            "positive threshold is not interpreted as zero inventory and the "
            "vertical handoff remains unvalidated"
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "materialization.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebound-result", type=Path, required=True)
    parser.add_argument("--provider-responses", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = materialize(
            rebound_result_path=args.rebound_result,
            provider_responses_path=args.provider_responses,
            output_dir=args.output_dir,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"vertical termination evidence materialization failed: {error}") from error
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "MATERIALIZED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
