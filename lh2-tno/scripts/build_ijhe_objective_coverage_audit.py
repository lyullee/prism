#!/usr/bin/env python3
"""Build the explanatory IJHE objective coverage ledger."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.ijhe_objective_audit import (  # noqa: E402
    build_ijhe_objective_coverage_audit,
)


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    value["_record_path"] = str(path)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--union-verification", type=Path, required=True)
    parser.add_argument("--completion-audit", type=Path, required=True)
    parser.add_argument("--scope-matrix", type=Path, required=True)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument("--native-catalog-verification", type=Path, required=True)
    parser.add_argument("--state-snapshot-audit", type=Path, required=True)
    parser.add_argument("--native-packet-evidence", type=Path, required=True)
    parser.add_argument("--native-packet-campaign-ledger", type=Path, required=True)
    parser.add_argument("--slabx-validation-evidence", type=Path)
    parser.add_argument("--validation-evidence-matrix", type=Path)
    parser.add_argument("--realtime-cache-benchmark", type=Path)
    parser.add_argument("--native-state-snapshot-campaign-ledger", type=Path)
    parser.add_argument("--extension-state-snapshot-coverage", type=Path)
    parser.add_argument("--observed-state-replay-audit", type=Path)
    parser.add_argument("--observed-state-runtime-frames", type=Path)
    parser.add_argument("--external-field-evidence", type=Path)
    parser.add_argument("--external-field-model-comparison", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_ijhe_objective_coverage_audit(
            union_verification=_object(args.union_verification),
            completion_audit=_object(args.completion_audit),
            scope_matrix=_object(args.scope_matrix),
            facility_assessment=_object(args.facility_assessment),
            native_catalog_verification=_object(args.native_catalog_verification),
            state_snapshot_audit=_object(args.state_snapshot_audit),
            native_packet_evidence=_object(args.native_packet_evidence),
            native_packet_campaign_ledger=_object(args.native_packet_campaign_ledger),
            slabx_validation_evidence=(
                _object(args.slabx_validation_evidence)
                if args.slabx_validation_evidence
                else None
            ),
            validation_evidence_matrix=(
                _object(args.validation_evidence_matrix)
                if args.validation_evidence_matrix
                else None
            ),
            realtime_cache_benchmark=(
                _object(args.realtime_cache_benchmark)
                if args.realtime_cache_benchmark
                else None
            ),
            native_state_snapshot_campaign_ledger=(
                _object(args.native_state_snapshot_campaign_ledger)
                if args.native_state_snapshot_campaign_ledger
                else None
            ),
            extension_state_snapshot_coverage=(
                _object(args.extension_state_snapshot_coverage)
                if args.extension_state_snapshot_coverage
                else None
            ),
            observed_state_replay_audit=(
                _object(args.observed_state_replay_audit)
                if args.observed_state_replay_audit
                else None
            ),
            observed_state_runtime_frames=(
                _object(args.observed_state_runtime_frames)
                if args.observed_state_runtime_frames
                else None
            ),
            external_field_evidence=(
                _object(args.external_field_evidence)
                if args.external_field_evidence
                else None
            ),
            external_field_model_comparison=(
                _object(args.external_field_model_comparison)
                if args.external_field_model_comparison
                else None
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"IJHE objective coverage input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "core_blocked_count": len(report["core_blocking_check_ids"]),
        "strict_blocked_count": len(report["strict_blocking_check_ids"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] in {
        "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN",
        "IJHE_OBJECTIVE_COMPLETE",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
