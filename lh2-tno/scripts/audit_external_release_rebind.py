"""Rebind external provider responses to strict PRISM releases diagnostically."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.external_release_normalization import (  # noqa: E402
    ExternalReleaseNormalizationError,
    build_diagnostic_release_rebind,
)
from lh2_tno.provider_release import load_provider_release  # noqa: E402


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
            release = load_provider_release(rebound["release"])
            row.update({
                "status": rebound["status"],
                "structural_release_contract_valid": True,
                "mass_balance_attached": rebound["mass_balance_attached"],
                "termination_basis": release.termination_basis,
                "event_id": release.event_id,
                "provider_source_digest": release.provider_source_digest,
                "provider_result_digest": release.provider_result_digest,
                "blocking_reasons": list(rebound["audit"].get("blocking_reasons", [])),
            })
        except (ExternalReleaseNormalizationError, ValueError, TypeError) as error:
            row["status"] = "BLOCKED_REBIND"
            row["blocking_reasons"] = [f"{type(error).__name__}: {error}"]
        rows.append(row)

    strict_bases = {
        "reviewed_isolation_success",
        "inventory_depletion",
        "emergency_relief_discharge",
        "two_sided_rupture",
        "pressure_equalization",
    }
    return {
        "schema_version": "prism.external_release_rebind_audit.v1",
        "status": "DIAGNOSTIC_RELEASE_REBIND_ONLY",
        "root": str(root),
        "resolved_release_count": len(rows),
        "provider_response_pair_count": sum(row["provider_response"] is not None for row in rows),
        "structural_release_contract_valid_count": sum(
            row["structural_release_contract_valid"] for row in rows
        ),
        "mass_balance_attached_count": sum(row["mass_balance_attached"] for row in rows),
        "strict_termination_candidate_count": sum(
            row["termination_basis"] in strict_bases for row in rows
        ),
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
