from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.reconstructed_chain_audit import audit_reconstructed_hazop_chain  # noqa: E402


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the reconstructed HAZOP consequence artifact.")
    parser.add_argument("--runtime-audit", type=Path, required=True)
    parser.add_argument("--provider-binding", type=Path, required=True)
    parser.add_argument("--chain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_reconstructed_hazop_chain(
        _object(args.runtime_audit),
        _object(args.provider_binding),
        _object(args.chain),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "check_count": report["check_count"],
        "passed_count": report["passed_count"],
        "blocked_count": report["blocked_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "RECONSTRUCTED_DIAGNOSTIC_CHAIN_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
