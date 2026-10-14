"""Audit external PDF equipment evidence without promoting QRA claims."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.external_document_evidence import (  # noqa: E402
    ExternalDocumentEvidenceError,
    audit_external_document_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_external_document_evidence(args.document)
    except (ExternalDocumentEvidenceError, OSError, ValueError) as error:
        raise SystemExit(f"external document audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "document_count": report["document_count"],
        "physical_validation_claim": report["physical_validation_claim"],
        "provider_release_packet_claim": report["provider_release_packet_claim"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
