"""Rebind external provider responses to strict PRISM releases diagnostically."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.external_release_normalization import (  # noqa: E402
    ExternalReleaseNormalizationError,
    audit_external_release_set_response,
    build_diagnostic_release_rebind,
)
from lh2_tno.provider_release import (  # noqa: E402
    load_provider_emergency_relief,
    load_provider_release,
    load_provider_release_set,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def audit_root(root: Path) -> dict:
    rows: list[dict] = []
    for release_path in sorted(root.rglob("resolved_release.json")):
        response_path = release_path.parent / "provider_response.json"
        row = {
            "resolved_release": str(release_path.relative_to(root)),
            "provider_response": (
                str(response_path.relative_to(root)) if response_path.is_file() else None
            ),
            "resolved_release_sha256": _sha256(release_path),
            "status": "BLOCKED_MISSING_PROVIDER_RESPONSE",
            "structural_release_contract_valid": False,
            "mass_balance_attached": False,
            "provider_mass_balance_fields": [],
            "isolation_evidence_attached": False,
            "pressure_equalization_evidence_attached": False,
            "dynamic_state_closure_status": "BLOCKED_RELEASE_CONTRACT",
            "termination_basis": None,
            "event_id": None,
            "blocking_reasons": [],
        }
        if not response_path.is_file():
            row["blocking_reasons"] = ["paired provider_response.json is missing"]
            rows.append(row)
            continue
        try:
            rebound = build_diagnostic_release_rebind(release_path, response_path)
            release_payload = rebound["release"]
            release = (
                load_provider_emergency_relief(release_payload)
                if release_payload.get("event_kind") == "emergency_relief"
                else load_provider_release(release_payload)
            )
            mass_balance = getattr(release, "provider_mass_balance", None)
            mass_balance_payload = (
                mass_balance.model_dump(mode="json", exclude_none=True)
                if mass_balance is not None
                else {}
            )
            row.update({
                "status": rebound["status"],
                "structural_release_contract_valid": True,
                "mass_balance_attached": rebound["mass_balance_attached"],
                "provider_mass_balance_fields": sorted(mass_balance_payload),
                "isolation_evidence_attached": all(
                    key in mass_balance_payload
                    for key in ("isolation_time_s", "isolation_success")
                ),
                "pressure_equalization_evidence_attached": all(
                    key in mass_balance_payload
                    for key in (
                        "pressure_equalization_time_s",
                        "pressure_equalization_success",
                        "terminal_source_pressure_pa_abs",
                        "ambient_pressure_pa_abs",
                        "max_post_pressure_equalization_flow_kg_s",
                    )
                ),
                "termination_basis": release.termination_basis,
                "event_id": release.event_id,
                "provider_source_digest": release.provider_source_digest,
                "provider_result_digest": release.provider_result_digest,
                "blocking_reasons": list(rebound["audit"].get("blocking_reasons", [])),
            })
            dynamic_closure = mass_balance_payload.get("dynamic_state_closure")
            if isinstance(dynamic_closure, dict):
                row["dynamic_state_closure_status"] = (
                    dynamic_closure.get("status")
                    or (
                        "READY"
                        if dynamic_closure.get("inventory_feedback_closed") is True
                        and dynamic_closure.get("pressure_feedback_closed") is True
                        else "BLOCKED"
                    )
                )
            elif release.termination_basis == "inventory_depletion" and not rebound["mass_balance_attached"]:
                row["dynamic_state_closure_status"] = "BLOCKED_RELEASE_CONTRACT"
            else:
                row["dynamic_state_closure_status"] = "BLOCKED"
        except (ExternalReleaseNormalizationError, ValueError, TypeError) as error:
            row["status"] = "BLOCKED_REBIND"
            row["blocking_reasons"] = [f"{type(error).__name__}: {error}"]
        rows.append(row)

    set_rows: list[dict] = []
    for release_set_path in sorted(root.rglob("resolved_release_set.json")):
        response_path = release_set_path.parent / "provider_response_endpoints.json"
        row = {
            "artifact_kind": "release_set",
            "resolved_release_set": str(release_set_path.relative_to(root)),
            "provider_response_endpoints": (
                str(response_path.relative_to(root)) if response_path.is_file() else None
            ),
            "resolved_release_set_sha256": _sha256(release_set_path),
            "status": "BLOCKED_MISSING_PROVIDER_ENDPOINT_RESPONSES",
            "structural_release_set_contract_valid": False,
            "endpoint_contracts_valid": False,
            "endpoint_count": 0,
            "endpoint_result_digest_bound_count": 0,
            "shared_inventory_evidence_attached": False,
            "termination_basis": None,
            "event_id": None,
            "blocking_reasons": [],
            "dynamic_state_closure_status": "NOT_APPLICABLE_TWO_SIDED_SHARED_LEDGER",
        }
        if not response_path.is_file():
            row["blocking_reasons"] = [
                "paired provider_response_endpoints.json is missing"
            ]
            set_rows.append(row)
            continue
        try:
            release_set = load_provider_release_set(release_set_path)
            audit = audit_external_release_set_response(
                release_set_path, response_path
            )
            endpoint_audits = audit.get("endpoint_audits", [])
            row.update({
                "status": audit["status"],
                "structural_release_set_contract_valid": True,
                "endpoint_contracts_valid": audit["endpoint_contracts_valid"],
                "endpoint_count": len(endpoint_audits),
                "endpoint_result_digest_bound_count": sum(
                    endpoint.get("checks", {}).get("result_digest_rebound") is True
                    for endpoint in endpoint_audits
                ),
                "shared_inventory_evidence_attached": audit[
                    "shared_inventory_evidence_attached"
                ],
                "termination_basis": (
                    "two_sided_rupture"
                    if all(
                        release.termination_basis == "two_sided_rupture"
                        for release in release_set.releases
                    )
                    else None
                ),
                "event_id": release_set.event_id,
                "provider_source_digest": release_set.provider_source_digest,
                "provider_result_digest": release_set.provider_result_digest,
                "blocking_reasons": list(audit["blocking_reasons"]),
            })
        except (ExternalReleaseNormalizationError, ValueError, TypeError) as error:
            row["status"] = "BLOCKED_RELEASE_SET_REBIND"
            row["blocking_reasons"] = [f"{type(error).__name__}: {error}"]
        set_rows.append(row)

    rows.extend(set_rows)

    strict_bases = {
        "reviewed_isolation_success",
        "inventory_depletion",
        "emergency_relief_discharge",
        "two_sided_rupture",
        "pressure_equalization",
    }
    flat_rows = [row for row in rows if row.get("artifact_kind") != "release_set"]
    release_set_rows = [row for row in rows if row.get("artifact_kind") == "release_set"]
    dynamic_state_counts = Counter(
        row.get("dynamic_state_closure_status")
        for row in flat_rows
        if row.get("dynamic_state_closure_status")
    )
    return {
        "schema_version": "prism.external_release_rebind_audit.v1",
        "status": "DIAGNOSTIC_RELEASE_REBIND_ONLY",
        "root": str(root),
        "resolved_release_count": len(rows),
        "resolved_release_file_count": len(flat_rows),
        "resolved_release_set_count": len(release_set_rows),
        "provider_response_pair_count": sum(
            row["provider_response"] is not None for row in flat_rows
        ),
        "provider_response_endpoint_pair_count": sum(
            row["provider_response_endpoints"] is not None
            for row in release_set_rows
        ),
        "structural_release_contract_valid_count": sum(
            row["structural_release_contract_valid"] for row in flat_rows
        ),
        "structural_release_set_contract_valid_count": sum(
            row["structural_release_set_contract_valid"] for row in release_set_rows
        ),
        "mass_balance_attached_count": sum(
            row.get("mass_balance_attached", False) for row in flat_rows
        ),
        "shared_inventory_evidence_attached_count": sum(
            row["shared_inventory_evidence_attached"] for row in release_set_rows
        ),
        "isolation_evidence_attached_count": sum(
            row.get("isolation_evidence_attached", False) for row in flat_rows
        ),
        "pressure_equalization_evidence_attached_count": sum(
            row.get("pressure_equalization_evidence_attached", False)
            for row in flat_rows
        ),
        "strict_termination_candidate_count": sum(
            row["termination_basis"] in strict_bases for row in rows
        ),
        "flat_strict_termination_candidate_count": sum(
            row["termination_basis"] in strict_bases for row in flat_rows
        ),
        "release_set_strict_termination_candidate_count": sum(
            row["termination_basis"] in strict_bases for row in release_set_rows
        ),
        "dynamic_state_closure_status_counts": dict(dynamic_state_counts),
        "provider_packet_promoted": False,
        "frequency_inference_performed": False,
        "physical_validation_claim": False,
        "facility_qra_allowed": False,
        "rows": rows,
        "policy": {
            "release_mapping_is_a_copy": True,
            "residual_inventory_is_not_replaced_with_zero": True,
            "missing_provider_ledger_is_not_inferred": True,
            "slabx_lh2_is_not_modified": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_root(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        key: report[key]
        for key in (
            "status",
            "resolved_release_count",
            "provider_response_pair_count",
            "structural_release_contract_valid_count",
            "mass_balance_attached_count",
            "strict_termination_candidate_count",
            "provider_packet_promoted",
            "facility_qra_allowed",
        )
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
