"""Read-only verification of the sequential N=512 Sobol extension."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

import statistical_convergence_extension as E
import statistical_pilot as S
import statistical_transfer as T


def compare_records(stored: list[dict], recomputed: list[dict]) -> tuple[int, float]:
    if len(stored) != len(recomputed):
        raise AssertionError("sensitivity record count mismatch")
    maximum = 0.
    scalars = 0
    for left, right in zip(stored, recomputed):
        identity = ("measure", "seed", "metric", "n", "status")
        if any(left[name] != right[name] for name in identity):
            raise AssertionError("sensitivity record identity mismatch")
        for field in ("first", "total"):
            a, b = np.asarray(left[field], dtype=float), np.asarray(right[field], dtype=float)
            maximum = max(maximum, float(np.max(np.abs(a - b))))
            scalars += a.size
    if maximum != 0.:
        raise AssertionError(f"sensitivity vector mismatch: {maximum}")
    return scalars, maximum


def verify(output: Path, pilot: Path, transfer: Path) -> dict:
    declared = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    if declared.get("schema") != E.SCHEMA:
        raise AssertionError("unexpected N=512 schema")
    E.verify_upstream(pilot, transfer, declared)

    manifest = json.loads((output / "artifact_hashes.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        path = output / name
        if not path.is_file() or E.sha256(path) != expected:
            raise AssertionError(f"N=512 artifact hash mismatch: {name}")

    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    counts = summary["counts"]
    source_keys = set()
    source_status = Counter()
    with (output / "source_states.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["key"] in source_keys:
                raise AssertionError("duplicate N=512 source key")
            source_keys.add(row["key"])
            source_status[row["status"]] += 1
    if len(source_keys) != counts["new_thermodynamic_source_states"]:
        raise AssertionError("N=512 source-state count mismatch")
    if source_status.get("FAILED", 0) != counts["new_source_failures"]:
        raise AssertionError("N=512 source failure count mismatch")

    store, prefix_counts = E.load_prefix_rows(pilot, transfer)
    tail_rows = 0
    layout_curve_relations = 0
    tail_status = Counter()
    expected_index = {}
    with (output / "tail_design_results.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["measure"], int(row["seed"]), row["block"])
            next_index = expected_index.get(key, E.PRIOR_N)
            if row["index"] != next_index:
                raise AssertionError(f"non-contiguous N=512 tail index: {key}")
            expected_index[key] = next_index + 1
            tail_rows += 1
            tail_status[row["status"]] += 1
            layouts = row.get("layout_evaluations", {})
            if row["status"] == "OK":
                if layouts != T.layout_outputs(row):
                    raise AssertionError("stored N=512 tail layout result mismatch")
                layout_curve_relations += len(layouts) * len(S.CURVES)
            E.metric_store_row(store, row, layouts)
    if tail_rows != counts["new_tail_rows"]:
        raise AssertionError("N=512 tail-row count mismatch")
    if layout_curve_relations != counts["new_tail_layout_curve_relations"]:
        raise AssertionError("N=512 layout-curve relation count mismatch")
    expected_blocks = len(S.MEASURES) * len(E.SEEDS) * (S.K + 2)
    if len(expected_index) != expected_blocks or any(index != E.FINAL_N
                                                       for index in expected_index.values()):
        raise AssertionError("incomplete N=512 tail block")
    if any(len(values) != E.FINAL_N for metrics in store.values()
           for values in metrics.values()):
        raise AssertionError("reconstructed N=512 metric array length mismatch")

    recomputed = E.calculate_sensitivity(store)
    stored = json.loads((output / "sensitivity_estimates.json").read_text(encoding="utf-8"))
    sensitivity_scalars, sensitivity_error = compare_records(stored, recomputed)
    locked = E.compare_locked_n256(recomputed, transfer)
    if locked != summary["locked_n256_exact_match"]:
        raise AssertionError("locked N=256 comparison summary mismatch")
    recomputed_metrics = E.summarize(recomputed)
    if recomputed_metrics != summary["metrics"]:
        raise AssertionError("N=512 convergence summary mismatch")
    eligible = sum(item["status"] == "PRIMARY_ELIGIBLE"
                   for item in recomputed_metrics.values())
    if eligible != counts["primary_eligible_metrics"]:
        raise AssertionError("N=512 eligible count mismatch")
    required = counts["family_required_metrics"]
    decision = "PRIMARY_ELIGIBLE" if eligible >= required else "EXPLORATORY_APPENDIX"
    if decision != summary["family_decision"]:
        raise AssertionError("N=512 family decision mismatch")

    return {
        "status": "VERIFIED_SOFTWARE_AND_DATA_INTEGRITY_ONLY",
        "experimental_validation": False,
        "artifact_hashes_checked": len(manifest),
        "locked_prefix_rows_reconstructed": sum(prefix_counts.values()),
        "new_source_states_checked": len(source_keys),
        "new_tail_rows_checked": tail_rows,
        "stored_tail_layout_curve_relations_recomputed": layout_curve_relations,
        "sensitivity_records_recomputed": len(recomputed),
        "sensitivity_scalars_compared": sensitivity_scalars,
        "sensitivity_max_absolute_error": sensitivity_error,
        "locked_n256_max_absolute_error": locked["max_absolute_error"],
        "tail_status": dict(tail_status),
        "primary_eligible_metrics": eligible,
        "family_required_metrics": required,
        "family_decision": decision,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=root / "논문" / "불연속Sobol_N512_20260901")
    parser.add_argument("--pilot", type=Path,
                        default=root / "논문" / "통계예비계산_20260901")
    parser.add_argument("--transfer", type=Path,
                        default=root / "논문" / "통계전이평가_20260901")
    args = parser.parse_args()
    print(json.dumps(verify(args.out, args.pilot, args.transfer),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
