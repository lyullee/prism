"""Attach the exact provider-response reconciliation to the current IJHE audit.

The main audit builder accepts this record for newly generated audits.  This
small refresh command is for a saved authoritative audit produced before that
input existed: it applies the same fail-closed validation to the saved audit,
adds or replaces one diagnostic check, and preserves every existing check and
blocking gate.  It never changes facility-QRA or physical-validation claims.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


CHECK_NAME = "diagnostic_external_provider_response_facility_reconciliation"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _check(record: Mapping[str, Any], record_path: Path) -> dict[str, Any]:
    promotion = record.get("promotion")
    promotion = promotion if isinstance(promotion, Mapping) else {}
    policy = record.get("policy")
    policy = policy if isinstance(policy, Mapping) else {}
    response_count = record.get("response_count")
    facility_case_count = record.get("facility_case_count")
    exact_match_count = record.get("exact_case_match_count")
    qualified_match_count = record.get("qualified_exact_case_match_count")
    no_match_count = record.get("no_exact_case_match_count")
    valid = (
        record.get("schema_version") == "prism.provider_response_facility_reconciliation.v1"
        and record.get("status") in {
            "DIAGNOSTIC_RESPONSE_CASE_RECONCILIATION",
            "QUALIFIED_RESPONSE_CASE_COVERAGE",
        }
        and isinstance(response_count, int)
        and response_count >= 0
        and isinstance(facility_case_count, int)
        and facility_case_count >= 0
        and isinstance(exact_match_count, int)
        and 0 <= exact_match_count <= response_count
        and isinstance(qualified_match_count, int)
        and 0 <= qualified_match_count <= exact_match_count
        and isinstance(no_match_count, int)
        and no_match_count + exact_match_count == response_count
        and isinstance(record.get("rows"), list)
        and len(record["rows"]) == response_count
        and promotion.get("provider_packet_promoted") is False
        and promotion.get("frequency_inference_performed") is False
        and promotion.get("physical_validation_claim") is False
        and promotion.get("facility_qra_claim") is False
        and policy.get("exact_event_component_port_identity_required") is True
        and policy.get("qualification_sidecar_required") is True
        and policy.get("missing_identity_is_not_inferred") is True
        and policy.get("facility_ir_fn_remains_withheld") is True
    )
    return {
        "name": CHECK_NAME,
        "status": "PASS" if valid else "BLOCKED",
        "diagnostic_only": True,
        "blocking_reason": (
            None
            if valid
            else "external provider response reconciliation is missing, malformed, or carries an unsafe promotion claim"
        ),
        "evidence": {
            "record": str(record_path),
            "schema_version": record.get("schema_version"),
            "status": record.get("status"),
            "response_count": response_count,
            "facility_case_count": facility_case_count,
            "exact_case_match_count": exact_match_count,
            "qualified_exact_case_match_count": qualified_match_count,
            "component_candidate_response_count": record.get(
                "component_candidate_response_count"
            ),
            "no_exact_case_match_count": no_match_count,
            "promotion": dict(promotion),
            "policy": dict(policy),
        },
        "interpretation": (
            "External provider responses are compared with exact facility event, component, and "
            "port identities. No-match or unqualified rows remain evidence gaps; component-name "
            "similarity never repairs identity, and no frequency, physical validation, or facility "
            "IR/F-N result is promoted."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = _load(args.audit)
    reconciliation = _load(args.reconciliation)
    checks = audit.get("checks")
    if not isinstance(checks, list):
        raise SystemExit("audit checks must be an array")
    new_check = _check(reconciliation, args.reconciliation)
    checks = [
        row for row in checks
        if not isinstance(row, Mapping) or row.get("name") != CHECK_NAME
    ]
    checks.append(new_check)
    audit["checks"] = checks
    audit["blocking_reasons"] = [
        row.get("blocking_reason")
        for row in checks
        if isinstance(row, Mapping)
        and row.get("status") == "BLOCKED"
        and isinstance(row.get("blocking_reason"), str)
    ]
    # Preserve the authoritative state claims.  This refresh only adds a
    # diagnostic evidence check; it cannot turn an incomplete audit into a
    # complete facility QRA.
    audit["complete_facility_qra_claim"] = False
    audit["physical_validation_claim"] = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": audit.get("status"),
        "check_count": len(checks),
        "blocking_reason_count": len(audit["blocking_reasons"]),
        "reconciliation_check_status": new_check["status"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0 if new_check["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
