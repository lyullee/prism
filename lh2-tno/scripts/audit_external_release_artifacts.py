"""Inventory external LH2 release JSON artifacts without QRA promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.external_release_artifact_intake import (  # noqa: E402
    ExternalReleaseArtifactIntakeError,
    audit_external_release_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", action="append", default=[], type=Path)
    parser.add_argument("--root", action="append", default=[], type=Path)
    parser.add_argument("--qualification-path", action="append", default=[], type=Path)
    parser.add_argument("--qualification-root", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = audit_external_release_artifacts(
            args.path,
            args.root,
            args.qualification_path,
            args.qualification_root,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SystemExit(f"external release artifact intake error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "artifact_file_count": report["artifact_file_count"],
        "qualification_file_count": report["qualification_file_count"],
        "release_row_count": report["release_row_count"],
        "qualified_sidecar_row_count": report["qualified_sidecar_row_count"],
        "actual_origin_row_count": report["actual_origin_row_count"],
        "synthetic_or_model_prediction_row_count": report["synthetic_or_model_prediction_row_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
