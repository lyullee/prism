"""Review an external LH2 digital-twin model root before PRISM promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.external_lh2_model_review import review_external_lh2_model_root  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--closure-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = review_external_lh2_model_root(
        args.source_root,
        closure_audit=args.closure_audit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["conclusion"],
        "output": str(args.output),
        "benchmark_review_count": len(report.get("benchmark_reviews", [])),
        "provider_response_count": report.get("provider_like_artifacts", {}).get("provider_response_count", 0),
        "exact_generic_identity_match_count": report.get("provider_like_artifacts", {}).get("exact_generic_identity_match_count", 0),
        "qualification_sidecar_count": report.get("provider_like_artifacts", {}).get("qualification_sidecar_count", 0),
    }, ensure_ascii=False))
    return 0 if report["conclusion"] == "MODEL_ROOT_REVIEWED_NO_PRISM_PROMOTION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
