"""Audit several external JSON workspaces without promotion.

Usage:
    python scripts/audit_provider_artifact_workspace_roots.py
      --root prism-dev=C:/path/to/prism
      --root equipment=C:/path/to/equipment
      --output results/provider_workspace_roots_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.provider_artifact_audit import (  # noqa: E402
    audit_provider_artifact_roots,
)


def _parse_root(value: str) -> tuple[str, Path]:
    label, separator, path = value.partition("=")
    if not separator or not label.strip() or not path.strip():
        raise argparse.ArgumentTypeError(
            "--root must use the form label=path"
        )
    return label.strip(), Path(path.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        action="append",
        type=_parse_root,
        required=True,
        help="external workspace label and path (repeatable)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots: dict[str, Path] = {}
    for label, path in args.root:
        if label in roots:
            parser.error(f"duplicate root label: {label}")
        roots[label] = path
    report = audit_provider_artifact_roots(roots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "root_count": report["root_count"],
        "artifact_count": report["summary"]["artifact_count"],
        "qualification_artifact_count": report["summary"][
            "qualification_artifact_count"
        ],
        "facility_ir_fn_allowed": report["summary"]["facility_ir_fn_allowed"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
