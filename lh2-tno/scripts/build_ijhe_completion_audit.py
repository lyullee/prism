"""Build a fail-closed IJHE readiness audit from saved PRISM ledgers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.completion_audit import build_ijhe_completion_audit  # noqa: E402


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit evidence required for an IJHE PRISM scope claim.")
    parser.add_argument("--current-status", type=Path, required=True)
    parser.add_argument("--scope-matrix", type=Path, required=True)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--uncertainty-result", type=Path)
    parser.add_argument("--provider-worklist", type=Path)
    parser.add_argument("--diagnostic-adapter-registry", type=Path)
    parser.add_argument("--diagnostic-adapter-execution", type=Path)
    parser.add_argument("--diagnostic-worklist-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        status = _object(args.current_status)
        matrix = _object(args.scope_matrix)
        campaign = _object(args.campaign_result)
        uncertainty = _object(args.uncertainty_result) if args.uncertainty_result else None
        worklist = _object(args.provider_worklist) if args.provider_worklist else None
        registry = _object(args.diagnostic_adapter_registry) if args.diagnostic_adapter_registry else None
        diagnostic_execution = (
            _object(args.diagnostic_adapter_execution)
            if args.diagnostic_adapter_execution
            else None
        )
        if diagnostic_execution is not None:
            diagnostic_execution["_record_path"] = str(args.diagnostic_adapter_execution)
        worklist_evidence = (
            _object(args.diagnostic_worklist_evidence)
            if args.diagnostic_worklist_evidence
            else None
        )
        if worklist_evidence is not None:
            worklist_evidence["_record_path"] = str(args.diagnostic_worklist_evidence)
        report = build_ijhe_completion_audit(
            status,
            matrix,
            campaign,
            uncertainty,
            worklist,
            registry,
            diagnostic_execution,
            worklist_evidence,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"IJHE completion audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "check_count": len(report["checks"]),
        "blocking_reason_count": len(report["blocking_reasons"]),
    }, ensure_ascii=False))
    return 0 if report["status"] == "READY_FOR_IJHE_SCOPE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
