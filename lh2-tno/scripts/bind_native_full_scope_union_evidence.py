#!/usr/bin/env python3
"""Bind validation and realtime evidence to a native LH2 union assessment.

This command is an evidence-bookkeeping step after
``run_native_full_scope_union_assessment.py``.  It deliberately does not run a
new provider solver or promote a synthetic packet.  Instead it builds the
fail-closed validation matrix, reruns the IJHE readiness audit with the
measured cache benchmark, and records the resulting gate state beside the
union assessment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.completion_audit import build_ijhe_completion_audit  # noqa: E402
from lh2_tno.validation_evidence_matrix import (  # noqa: E402
    build_validation_evidence_matrix,
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


def _with_record(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = _load(path)
    value["_record_path"] = str(path)
    return value


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.union_dir
    scope = _load(output_dir / "scope_matrix.json")
    campaign = _load(output_dir / "campaign_result.json")
    facility = _load(output_dir / "facility_assessment.json")
    current_status = _load(args.current_status)

    source_audit = _load(args.ijhe_audit_source)
    matrix = build_validation_evidence_matrix(
        args.pool_record,
        args.equipment_audit,
        output_dir / "facility_assessment.json",
        native_contract_path=args.native_contract,
        ijhe_audit_path=args.ijhe_audit_source,
        external_sweep_path=args.external_sweep,
    )
    matrix["_record_path"] = str(output_dir / "validation_evidence_matrix.json")

    provider_worklist = _with_record(args.provider_worklist)
    registry = _with_record(args.diagnostic_adapter_registry)
    facility_record = dict(facility)
    facility_record["_record_path"] = str(output_dir / "facility_assessment.json")
    vertical = _with_record(args.vertical_handoff_result)
    realtime = _with_record(args.realtime_cache_benchmark)
    native_full_bore = _with_record(args.native_full_bore_result)
    state_snapshot_binding = _with_record(args.state_snapshot_binding_audit)
    native_state_snapshot_campaign = _with_record(args.native_state_snapshot_campaign_ledger)
    native_scope_packet_catalog = _with_record(args.native_scope_packet_catalog_verification)
    slabx_validation = _with_record(args.slabx_validation_evidence)

    audit = build_ijhe_completion_audit(
        current_status,
        scope,
        campaign,
        facility,
        provider_worklist,
        registry,
        facility_assessment=facility_record,
        vertical_handoff_result=vertical,
        validation_evidence_matrix=matrix,
        realtime_cache_benchmark=realtime,
        native_full_bore_result=native_full_bore,
        state_snapshot_binding_audit=state_snapshot_binding,
        native_scope_packet_catalog_verification=native_scope_packet_catalog,
        slabx_validation_evidence=slabx_validation,
    )

    verification_path = output_dir / "verification.json"
    verification = _load(verification_path)
    verification.update(
        {
            "validation_evidence_matrix_status": matrix["status"],
            "validation_evidence_matrix_decision": matrix["decision"],
            "validation_evidence_matrix_domain_count": len(matrix["evidence_domains"]),
            "validation_evidence_matrix_physical_validation_claim": matrix[
                "physical_validation_claim"
            ],
            "validation_evidence_matrix_facility_qra_claim": matrix["facility_qra_claim"],
            "realtime_cache_benchmark_cache_hits": realtime.get("cache_hits") if realtime else None,
            "realtime_cache_benchmark_cache_p95_ms": realtime.get("cache_p95_ms") if realtime else None,
            "realtime_cache_benchmark_fresh_physics_elapsed_ms": (
                realtime.get("fresh_physics_elapsed_ms") if realtime else None
            ),
            "realtime_cache_benchmark_fresh_physics_meets_one_hz": (
                realtime.get("fresh_physics_meets_one_hz") if realtime else None
            ),
            "ijhe_audit_status": audit["status"],
            "ijhe_audit_check_count": len(audit["checks"]),
            "ijhe_audit_pass_count": sum(row["status"] == "PASS" for row in audit["checks"]),
            "ijhe_audit_blocked_count": sum(
                row["status"] == "BLOCKED" for row in audit["checks"]
            ),
            "state_snapshot_binding_status": (
                state_snapshot_binding.get("status") if state_snapshot_binding else None
            ),
            "state_snapshot_binding_record_count": (
                state_snapshot_binding.get("record_count") if state_snapshot_binding else None
            ),
            "state_snapshot_binding_bound_count": (
                state_snapshot_binding.get("bound_count") if state_snapshot_binding else None
            ),
            "state_snapshot_binding_unbound_count": (
                state_snapshot_binding.get("unbound_count") if state_snapshot_binding else None
            ),
            "native_state_snapshot_campaign_status": (
                native_state_snapshot_campaign.get("status")
                if native_state_snapshot_campaign else None
            ),
            "native_state_snapshot_campaign_event_count": (
                native_state_snapshot_campaign.get("event_count")
                if native_state_snapshot_campaign else None
            ),
            "native_state_snapshot_campaign_bound_event_count": (
                native_state_snapshot_campaign.get("state_snapshot_campaign_reconciliation", {}).get(
                    "bound_event_count"
                )
                if native_state_snapshot_campaign else None
            ),
            "native_state_snapshot_campaign_provider_result_digest_mismatch_count": (
                len(
                    native_state_snapshot_campaign.get(
                        "state_snapshot_campaign_reconciliation", {}
                    ).get("provider_result_digest_mismatch_event_ids", [])
                )
                if native_state_snapshot_campaign else None
            ),
            "native_scope_packet_catalog_status": (
                native_scope_packet_catalog.get("status") if native_scope_packet_catalog else None
            ),
            "native_scope_packet_catalog_event_count": (
                native_scope_packet_catalog.get("frequency_event_count")
                if native_scope_packet_catalog else None
            ),
            "native_scope_packet_catalog_exact_packet_count": (
                native_scope_packet_catalog.get("exact_native_packet_count")
                if native_scope_packet_catalog else None
            ),
            "slabx_validation_evidence_status": (
                slabx_validation.get("status") if slabx_validation else None
            ),
            "slabx_validation_evidence_check_count": (
                len(slabx_validation.get("checks", []))
                if slabx_validation and isinstance(slabx_validation.get("checks"), list)
                else None
            ),
            "slabx_validation_evidence_physical_validation_claim": (
                slabx_validation.get("physical_validation_claim") if slabx_validation else None
            ),
        }
    )
    _save(output_dir / "validation_evidence_matrix.json", matrix)
    _save(output_dir / "ijhe_completion_audit.json", audit)
    _save(verification_path, verification)
    return {
        "status": audit["status"],
        "audit_check_count": len(audit["checks"]),
        "audit_pass_count": sum(row["status"] == "PASS" for row in audit["checks"]),
        "audit_blocked_count": sum(row["status"] == "BLOCKED" for row in audit["checks"]),
        "validation_matrix_status": matrix["status"],
        "validation_matrix_decision": matrix["decision"],
        "cache_hits": realtime.get("cache_hits") if realtime else None,
        "fresh_physics_meets_one_hz": realtime.get("fresh_physics_meets_one_hz") if realtime else None,
        "output": str(output_dir.resolve()),
        "source_audit_status": source_audit.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--union-dir", type=Path, required=True)
    parser.add_argument("--current-status", type=Path, required=True)
    parser.add_argument("--pool-record", type=Path, required=True)
    parser.add_argument("--equipment-audit", type=Path, required=True)
    parser.add_argument("--native-contract", type=Path, required=True)
    parser.add_argument("--external-sweep", type=Path, required=True)
    parser.add_argument("--ijhe-audit-source", type=Path, required=True)
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--diagnostic-adapter-registry", type=Path, required=True)
    parser.add_argument("--vertical-handoff-result", type=Path, required=True)
    parser.add_argument("--realtime-cache-benchmark", type=Path, required=True)
    parser.add_argument(
        "--native-full-bore-result",
        type=Path,
        default=None,
        help="Optional native finite full-bore diagnostic record; remains diagnostic-only.",
    )
    parser.add_argument(
        "--state-snapshot-binding-audit",
        type=Path,
        default=None,
        help="Optional canonical equipment-state handoff audit; remains diagnostic-only.",
    )
    parser.add_argument(
        "--native-state-snapshot-campaign-ledger",
        type=Path,
        default=None,
        help="Optional base native-campaign reconciliation of state and provider result digests.",
    )
    parser.add_argument(
        "--native-scope-packet-catalog-verification",
        type=Path,
        default=None,
        help="Optional exact native generic-scope packet catalog verification.",
    )
    parser.add_argument(
        "--slabx-validation-evidence",
        type=Path,
        default=None,
        help="Optional restricted SLABx-LH2 consequence-component validation record.",
    )
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"native union evidence binding failed: {error}") from error
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
