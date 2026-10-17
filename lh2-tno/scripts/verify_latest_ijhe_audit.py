from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.latest_ijhe_audit_verification import verify_latest_ijhe_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the latest PRISM IJHE audit pointer and fail-closed handoff metadata.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--current-status", type=Path, default=Path("CURRENT_STATUS.json"))
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--handoff", type=Path)
    parser.add_argument("--receptor-geometry-interpretation", type=Path)
    parser.add_argument("--scope-matrix", type=Path)
    parser.add_argument("--release-boundary", type=Path)
    parser.add_argument("--native-external-multi-equipment-recheck", type=Path)
    parser.add_argument("--native-external-clean-full-scope-replay", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    status_path = args.current_status if args.current_status.is_absolute() else root / args.current_status
    audit_path = args.audit.resolve() if args.audit else None
    handoff_path = args.handoff.resolve() if args.handoff else None
    geometry_path = args.receptor_geometry_interpretation.resolve() if args.receptor_geometry_interpretation else None
    scope_path = args.scope_matrix.resolve() if args.scope_matrix else None
    release_path = args.release_boundary.resolve() if args.release_boundary else None
    native_recheck_path = (
        args.native_external_multi_equipment_recheck.resolve()
        if args.native_external_multi_equipment_recheck
        else None
    )
    clean_scope_path = (
        args.native_external_clean_full_scope_replay.resolve()
        if args.native_external_clean_full_scope_replay
        else None
    )
    report = verify_latest_ijhe_audit(
        status_path,
        root=root,
        audit=audit_path,
        handoff=handoff_path,
        receptor_geometry=geometry_path,
        scope_matrix=scope_path,
        release_boundary=release_path,
        native_external_multi_equipment_recheck=native_recheck_path,
        native_external_clean_full_scope_replay=clean_scope_path,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output), "blocking_reason_count": len(report["blocking_reasons"])}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
