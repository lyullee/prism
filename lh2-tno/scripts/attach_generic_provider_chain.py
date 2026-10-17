"""Attach one exact provider/SLABx diagnostic to a generic facility handoff.

The attachment is intentionally a small evidence join, not a new physics run.
It requires an exact component, operating-mode, and scenario-family match in
both the current and forecast request lists.  All other requests remain
uncomputed and the attached result stays operator-limited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "prism.generic_provider_chain_attachment.v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _requests(handoff: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = handoff.get(key, {}).get("requests") if isinstance(handoff.get(key), Mapping) else None
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"handoff.{key}.requests must be an array of objects")
    return list(value)


def _match(
    requests: list[Mapping[str, Any]],
    *,
    component_id: str,
    operating_mode: str,
    scenario_family: str,
) -> list[Mapping[str, Any]]:
    return [
        row for row in requests
        if row.get("component_id") == component_id
        and row.get("operating_mode") == operating_mode
        and row.get("scenario_family") == scenario_family
    ]


def attach_many(handoff: Mapping[str, Any], evidences: list[Mapping[str, Any]]) -> dict[str, Any]:
    if handoff.get("schema_version") != "prism.generic_outdoor_facility_hazop_handoff.v1":
        raise ValueError("unsupported generic handoff schema")
    if not evidences:
        raise ValueError("at least one provider evidence summary is required")
    current_requests = _requests(handoff, "current_state_handoff")
    forecast_requests = _requests(handoff, "quantitative_handoff")
    matched_rows: list[dict[str, Any]] = []
    evidence_payloads: list[dict[str, Any]] = []
    matched_ids: set[str] = set()
    seen_identities: set[tuple[str, str, str]] = set()
    for evidence in evidences:
        if evidence.get("schema_version") != "prism.generic_provider_chain_evidence_summary.v1":
            raise ValueError("unsupported provider evidence summary schema")
        identity = evidence.get("exact_identity")
        if not isinstance(identity, Mapping):
            raise ValueError("evidence.exact_identity is required")
        component_id = str(identity.get("component_id") or "")
        operating_mode = str(identity.get("operating_mode") or "")
        scenario_family = str(identity.get("hazop_scenario_family") or "")
        if not component_id or not operating_mode or not scenario_family:
            raise ValueError("provider evidence identity is incomplete")
        identity_key = (component_id, operating_mode, scenario_family)
        if identity_key in seen_identities:
            raise ValueError("duplicate provider evidence identity")
        seen_identities.add(identity_key)
        if identity.get("facility_id") not in (None, handoff.get("facility_id")):
            raise ValueError("provider evidence facility_id does not match handoff")
        current_matches = _match(current_requests, component_id=component_id, operating_mode=operating_mode, scenario_family=scenario_family)
        forecast_matches = _match(forecast_requests, component_id=component_id, operating_mode=operating_mode, scenario_family=scenario_family)
        if len(current_matches) != 1 or len(forecast_matches) != 1:
            raise ValueError(
                "provider evidence must match exactly one current and one forecast request; "
                f"current={len(current_matches)}, forecast={len(forecast_matches)}"
            )
        current = current_matches[0]
        forecast = forecast_matches[0]
        matched_rows.extend([
            {"path": "current", "request_id": str(current["request_id"]), "component_id": component_id, "operating_mode": operating_mode, "scenario_family": scenario_family},
            {"path": "forecast", "request_id": str(forecast["request_id"]), "component_id": component_id, "operating_mode": operating_mode, "scenario_family": scenario_family},
        ])
        matched_ids.update((str(current["request_id"]), str(forecast["request_id"])))
        evidence_payloads.append({
            "source_record": str(evidence.get("source_record") or ""),
            "source_sha256": str(evidence.get("source_sha256") or ""),
            "exact_identity": dict(identity),
            "provider_event_id": identity.get("provider_event_id"),
            "provider_port_id": identity.get("provider_port_id"),
            "provider_source_digest": identity.get("provider_source_digest"),
            "provider_result_digest": identity.get("provider_result_digest"),
            "release_boundary": evidence.get("provider_release_boundary"),
            "consequence_chain": evidence.get("consequence_chain"),
            "frequency_binding": evidence.get("frequency_binding"),
            "facility_campaign": evidence.get("facility_campaign"),
            "timing": evidence.get("timing"),
        })
    all_ids = {
        str(row["request_id"])
        for row in current_requests + forecast_requests
    }
    return {
        "schema_version": SCHEMA,
        "status": "PROVIDER_CHAINS_ATTACHED_OPERATOR_LIMITED",
        "facility_id": handoff.get("facility_id"),
        "matched_requests": matched_rows,
        "uncomputed_request_ids": sorted(all_ids - matched_ids),
        "provider_evidence": evidence_payloads[0] if len(evidence_payloads) == 1 else evidence_payloads,
        "summary": {
            "current_request_count": len(current_requests),
            "forecast_request_count": len(forecast_requests),
            "matched_request_count": len(matched_ids),
            "uncomputed_request_count": len(all_ids - matched_ids),
            "provider_chain_count": len(evidence_payloads),
            "provider_chain_stage_count": sum(
                len(item.get("consequence_chain", {}).get("stages", ()))
                for item in evidence_payloads
                if isinstance(item.get("consequence_chain"), Mapping)
            ),
        },
        "policy": {
            "exact_component_mode_family_match_required": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_qualification_claim": False,
            "physical_validation_claim": False,
            "facility_ir_fn_claim": False,
            "facility_qra_promotion": False,
            "uncomputed_cases_assigned_zero": False,
            "diagnostic_only": True,
        },
    }


def attach(handoff: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible single-evidence adapter."""
    result = attach_many(handoff, [evidence])
    result["status"] = "PROVIDER_CHAIN_ATTACHED_OPERATOR_LIMITED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = attach_many(_load(args.handoff), [_load(path) for path in args.evidence])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "matched_request_count": result["summary"]["matched_request_count"],
        "uncomputed_request_count": result["summary"]["uncomputed_request_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
