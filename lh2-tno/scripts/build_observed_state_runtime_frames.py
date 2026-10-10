"""Export latest state-only frames for an explicit realtime model handoff."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames  # noqa: E402

from audit_observed_equipment_state import _load, _source_from_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = _load(args.manifest)
    if manifest.get("schema_version") != "prism.observed_state_input_manifest.v1":
        raise SystemExit("manifest schema_version must be prism.observed_state_input_manifest.v1")
    specs = manifest.get("sources")
    if not isinstance(specs, list) or not specs:
        raise SystemExit("manifest requires a non-empty sources list")
    source_root = args.source_root
    manifest_source_root = manifest.get("source_root")
    if source_root is None and isinstance(manifest_source_root, str) and manifest_source_root:
        source_root = Path(manifest_source_root)
    try:
        sources = [_source_from_manifest(spec, source_root=source_root) for spec in specs]
        report = build_observed_state_runtime_frames(sources)
    except (OSError, UnicodeDecodeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise SystemExit(f"observed state runtime frame export failed: {error}") from error
    report["manifest"] = {
        "path": str(args.manifest),
        "schema_version": manifest.get("schema_version"),
        "source_root": str(source_root) if source_root else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "source_count": report["source_count"],
        "frame_count": report["frame_count"],
        "evidence_sample_count": report["evidence_sample_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
