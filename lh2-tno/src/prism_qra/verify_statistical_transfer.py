"""Read-only integrity verification for the synthetic transfer calculation."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

import set_valued_decision as D
import statistical_pilot as S
import statistical_transfer as T


def verify_decision(value: dict) -> None:
    category = value["category"]
    masks = tuple(value["admissible_top_masks"])
    if category not in D.CATEGORIES or not masks:
        raise AssertionError("invalid decision category or empty mask set")
    possible = 0
    necessary = 15
    for mask in masks:
        if isinstance(mask, bool) or not isinstance(mask, int) or not 0 <= mask <= 15:
            raise AssertionError("invalid priority mask")
        possible |= mask
        necessary &= mask
    if possible != value["possible_top_mask"] or necessary != value["necessary_top_mask"]:
        raise AssertionError("top-mask union/intersection mismatch")
    expected = (
        "ALL_NO_REACH" if masks == (0,) else
        "ROBUST_UNIQUE" if len(masks) == 1 and S.unique_positive(masks[0]) else
        "ROBUST_TIED_SET" if len(masks) == 1 else
        "INDETERMINATE_WITH_NO_REACH" if 0 in masks else
        "INDETERMINATE_ACTIVE"
    )
    if category != expected:
        raise AssertionError("decision category mismatch")
    if value["possible_top_count"] != possible.bit_count():
        raise AssertionError("possible top count mismatch")
    if value["necessary_top_count"] != necessary.bit_count():
        raise AssertionError("necessary top count mismatch")
    if "robust_strict_outranking" in value:
        relation = np.asarray(value["robust_strict_outranking"])
        if relation.shape != (4, 4) or np.diag(relation).any():
            raise AssertionError("invalid robust outranking relation")


def verify(output: Path, pilot: Path) -> dict:
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    if protocol["schema"] != T.SCHEMA:
        raise AssertionError("unexpected transfer schema")
    T.verify_locked_pilot(pilot, protocol)

    hashes = json.loads((output / "artifact_hashes.json").read_text(encoding="utf-8"))
    for name, expected in hashes.items():
        path = output / name
        if not path.is_file() or T.sha256(path) != expected:
            raise AssertionError(f"artifact hash mismatch: {name}")

    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    counts = summary["counts"]
    source_count = 0
    source_status = Counter()
    source_keys = set()
    with (output / "source_states.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["key"] in source_keys:
                raise AssertionError("duplicate source key")
            source_keys.add(row["key"])
            source_status[row["status"]] += 1
            source_count += 1
    if source_count != counts["new_thermodynamic_source_states"]:
        raise AssertionError("source-state count mismatch")
    if source_status.get("FAILED", 0) != counts["new_source_failures"]:
        raise AssertionError("source failure count mismatch")

    design_rows = 0
    layout_relations = 0
    design_status = Counter()
    with (output / "new_design_results.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            design_rows += 1
            design_status[row["status"]] += 1
            if row["status"] != "OK":
                continue
            recalculated = T.layout_outputs(row)
            if recalculated != row["layout_evaluations"]:
                raise AssertionError("stored layout result mismatch")
            layout_relations += len(recalculated) * len(S.CURVES)
    if design_rows != counts["new_pick_freeze_rows"]:
        raise AssertionError("new design-row count mismatch")

    decision_rows = 0
    decisions = 0
    categories = Counter()
    with (output / "decision_results.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            decision_rows += 1
            if set(row["decisions"]) != set(T.ALL_LAYOUTS):
                raise AssertionError("decision layout partition mismatch")
            for layout in row["decisions"].values():
                unknown = layout["retained_cd_curve_uncertainty"]
                known = layout["all_cd_known_curve_uncertainty_retained"]
                verify_decision(unknown)
                verify_decision(known)
                categories[unknown["category"]] += 1
                decisions += 1
    if decision_rows != counts["set_valued_base_rows"]:
        raise AssertionError("decision row count mismatch")
    if decisions != counts["set_valued_layout_evaluations"]:
        raise AssertionError("decision evaluation count mismatch")

    records = json.loads((output / "sensitivity_estimates.json").read_text(encoding="utf-8"))
    expected_metrics = 2 + len(T.ALL_LAYOUTS) * len(S.CURVES)
    expected_records = (len(S.MEASURES) * counts["total_scrambles"] * expected_metrics
                        * len(T.PREFIX_SIZES))
    if len(records) != expected_records:
        raise AssertionError("sensitivity record count mismatch")

    replicates = json.loads((output / "decision_replicates.json").read_text(encoding="utf-8"))
    for item in replicates:
        if not np.isclose(sum(item["category_fraction"].values()), 1., atol=1e-12):
            raise AssertionError("replicate category fractions violate partition")
        if not np.isclose(sum(item["all_cd_known_category_fraction"].values()),
                          1., atol=1e-12):
            raise AssertionError("known-Cd replicate categories violate partition")

    return {
        "status": "VERIFIED_SOFTWARE_AND_DATA_INTEGRITY_ONLY",
        "experimental_validation": False,
        "artifact_hashes_checked": len(hashes),
        "new_source_states_checked": source_count,
        "new_design_rows_checked": design_rows,
        "stored_layout_curve_relations_recomputed": layout_relations,
        "decision_rows_checked": decision_rows,
        "set_valued_layout_decisions_checked": decisions,
        "sensitivity_records_checked": len(records),
        "new_design_status": dict(design_status),
        "retained_uncertainty_categories": dict(categories),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=root / "논문" / "통계전이평가_20260901")
    parser.add_argument("--pilot", type=Path, default=root / "논문" / "통계예비계산_20260901")
    args = parser.parse_args()
    print(json.dumps(verify(args.out, args.pilot), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
