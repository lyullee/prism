"""Audit explicit engineering-unit claims written in XLSX headers."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.workbook_header_units import (  # noqa: E402
    extract_header_unit_claims,
    summarize_header_claims,
)


SCHEMA = "prism.workbook_header_unit_evidence.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_root(root: Path) -> dict[str, Any]:
    try:
        import openpyxl
    except ImportError as error:  # pragma: no cover - environment-specific
        raise RuntimeError("XLSX header audit requires openpyxl") from error
    files: list[dict[str, Any]] = []
    all_claims: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        record: dict[str, Any] = {
            "relative_path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
            "status": "READ",
            "claims": [],
        }
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
        try:
            for worksheet in workbook.worksheets:
                # Unit-bearing headers are expected at the top of a source
                # sheet. Restricting this scan avoids treating arbitrary
                # narrative cells as signal headers.
                for row_index, row in enumerate(
                    worksheet.iter_rows(min_row=1, max_row=4, values_only=True),
                    start=1,
                ):
                    for column_index, value in enumerate(row, start=1):
                        for claim in extract_header_unit_claims([value]):
                            enriched = {
                                **claim,
                                "sheet": worksheet.title,
                                "row": row_index,
                                "column": column_index,
                            }
                            record["claims"].append(enriched)
                            all_claims.append({"file": record["relative_path"], **enriched})
        finally:
            workbook.close()
        files.append(record)
    summary = summarize_header_claims(all_claims)
    status = "EXPLICIT_HEADER_UNITS_FOUND" if all_claims else "NO_EXPLICIT_HEADER_UNITS"
    if summary["conflict_tags"]:
        status = "EXPLICIT_HEADER_UNIT_CONFLICT"
    return {
        "schema_version": SCHEMA,
        "status": status,
        "source_root": str(root.resolve()),
        "source_file_count": len(files),
        "explicit_claim_count": len(all_claims),
        "summary": summary,
        "files": files,
        "policy": {
            "numeric_range_unit_inference": False,
            "procedure_setpoint_repurposed_as_raw_unit": False,
            "state_snapshot_binding_allowed": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_created": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_root(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "source_file_count": report["source_file_count"],
        "explicit_claim_count": report["explicit_claim_count"],
        "conflict_tags": report["summary"]["conflict_tags"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
