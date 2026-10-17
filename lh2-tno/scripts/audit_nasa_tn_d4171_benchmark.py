"""Create a provenance-bound, non-promoting NASA TN D-4171 HEM audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.external_nasa_hem_benchmark import audit_nasa_hem_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--source-markdown", type=Path)
    parser.add_argument("--external-source-commit")
    parser.add_argument("--external-source-tree-digest")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    source_sha = None
    if args.source_markdown is not None:
        source_sha = hashlib.sha256(args.source_markdown.read_bytes()).hexdigest()
    report = audit_nasa_hem_benchmark(
        result,
        result_record=str(args.result),
        source_markdown=str(args.source_markdown) if args.source_markdown else None,
        source_markdown_sha256=source_sha,
        external_source_commit=args.external_source_commit,
        external_source_tree_digest=args.external_source_tree_digest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "point_count": report["point_count"], "blocking_reason_count": len(report["blocking_reasons"])}))
    return 0 if not report["blocking_reasons"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
