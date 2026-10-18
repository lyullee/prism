#!/usr/bin/env python3
"""Validate geometry, raw discharge data and optional capacity evidence."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

import source_evidence as S


def _read_certificate(path: Path | None):
    if path is None:
        return None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise ValueError("capacity certificate CSV must contain exactly one row")
    row = {
        key: (None if value.strip() == "" else value)
        for key, value in rows[0].items()
    }
    return S.CapacityCertificate.model_validate(row)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--timeseries", type=Path)
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    geometry_rows = S.read_geometry_csv(args.geometry)
    if len(geometry_rows) != 1:
        raise ValueError("geometry CSV must contain exactly one row")
    metadata = None
    samples = None
    if args.metadata is not None:
        metadata = S.DischargeTestMetadata.model_validate_json(
            args.metadata.read_text(encoding="utf-8")
        )
    if args.timeseries is not None:
        samples = S.read_samples_csv(args.timeseries)
    if metadata is not None:
        raw_path = args.timeseries
        if raw_path is None:
            raw_path = args.metadata.parent / metadata.raw_data_file
        actual_hash = S.sha256_file(raw_path)
        if actual_hash != metadata.raw_data_sha256:
            raise ValueError("raw time-series SHA-256 does not match metadata")
    assessment = S.assess_source_evidence(
        geometry_rows[0], metadata, samples, _read_certificate(args.certificate)
    )
    payload = json.dumps(asdict(assessment), indent=2, ensure_ascii=False) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0 if assessment.claim_level != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
