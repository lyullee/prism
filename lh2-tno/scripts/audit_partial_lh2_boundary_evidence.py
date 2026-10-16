"""Audit operational LH2 procedure evidence without creating a release packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.partial_boundary_evidence import audit_partial_boundary_evidence  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must contain an object")
    return value


def _pdf_pages(path: Path) -> list[str]:
    from pypdf import PdfReader

    return [(page.extract_text() or "") for page in PdfReader(str(path)).pages]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = _load(args.manifest)
    raw_documents = manifest.get("documents")
    if not isinstance(raw_documents, list):
        raise SystemExit("manifest.documents must be an array")
    documents: list[dict[str, Any]] = []
    for raw in raw_documents:
        if not isinstance(raw, dict):
            raise SystemExit("manifest document rows must be objects")
        row = dict(raw)
        row["path"] = Path(str(row.get("path", "")))
        documents.append(row)
    result = audit_partial_boundary_evidence(documents, page_loader=_pdf_pages)
    result["source_manifest"] = str(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "document_count": result["document_count"],
        "found_anchor_count": result["found_anchor_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
