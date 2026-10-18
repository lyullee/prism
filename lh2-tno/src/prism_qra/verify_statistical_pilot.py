"""Read-only integrity and raw-row consistency check for the GH2 pilot.

No simulation or publication files are rewritten. A successful check is
software/data integrity evidence, not experimental validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np

import statistical_pilot as S


def verify(output: Path) -> dict:
    hashes = json.loads((output / "artifact_hashes.json").read_text(encoding="utf-8"))
    for name, expected in hashes.items():
        path = (output / name).resolve()
        if path.parent != output.resolve():
            raise ValueError("artifact path escapes the result directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"artifact checksum mismatch: {name}")
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    if protocol["source_hashes"] != S.fingerprints():
        raise ValueError("current calculation code differs from the result fingerprint")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    source = {}
    for line in (output / "source_states.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["key"] in source:
            raise ValueError("duplicate source state")
        source[row["key"]] = row
    rows_seen, statuses = set(), Counter()
    base = {measure: [] for measure in S.MEASURES}
    metric_values = {}
    direct_reach_checks = 0
    source_scaling_checks = 0
    with (output / "design_results.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["measure"], row["seed"], row["block"], row["index"])
            if key in rows_seen:
                raise ValueError("duplicate parameter row")
            rows_seen.add(key)
            statuses[row["status"]] += 1
            if row["block"] in ("A", "B"):
                base[row["measure"]].append(row)
            metric_values.setdefault(key[:3], []).append(S.scalar_metrics(row))
            x = np.array(row["inputs"])
            S.validate_physical(x)
            if row["status"] != "OK":
                assert "scores" not in row and "rates_kg_s" not in row
                continue
            for i, ratio in enumerate(S.PRESSURE_MULTIPLIERS):
                state = source[S.source_key(x[0] * ratio * 1e6, x[1])]
                expected = state["flux_kg_m2s"] * np.pi * (x[2 + i] * .001) ** 2 / 4. * x[6 + i]
                np.testing.assert_allclose(row["rates_kg_s"][i], expected, rtol=1e-12, atol=0)
                source_scaling_checks += 1
            # Independent vectorized geometric reconstruction from stored lengths.
            for li, layout in enumerate(S.LAYOUTS):
                xy = np.array(protocol["layouts"][layout]) * x[-1]
                distance = np.sqrt(np.sum((xy[:, None] - xy[None, :]) ** 2, axis=2))
                for ci in range(2):
                    reached = distance <= np.array(row["flame_lengths_m"][ci])[:, None]
                    np.fill_diagonal(reached, False)
                    counts = reached.sum(axis=0)
                    np.testing.assert_array_equal(counts, row["scores"][li][ci])
                    assert int(counts.sum()) == row["edge_counts"][li][ci]
                    mask = sum(1 << j for j, value in enumerate(counts) if value == counts.max()) if counts.max() > 0 else 0
                    assert mask == row["priority_masks"][li][ci]
                    direct_reach_checks += 1
    n, seeds = protocol["base_n"], protocol["seeds"]
    expected_keys = {(m, s, b, i) for m in S.MEASURES for s in seeds
                     for b in ("A", "B", *(f"AB_{j}" for j in range(S.K))) for i in range(n)}
    assert rows_seen == expected_keys
    assert len(rows_seen) == summary["counts"]["pick_freeze_parameter_rows"]
    assert len(source) == summary["counts"]["unique_thermodynamic_source_states"]
    assert dict(statuses) == summary["counts"]["status_counts"]
    assert sum(r["status"] != "OK" for r in source.values()) == summary["counts"]["source_failures"]
    assert direct_reach_checks == summary["counts"]["layout_curve_evaluations"]
    assert summary["counts"]["independent_physical_experiments_added"] == 0
    for measure, rows in base.items():
        assert S.rank_summary(rows) == summary["rank"][measure]
    estimates = json.loads((output / "sensitivity_estimates.json").read_text(encoding="utf-8"))
    for estimate in estimates:
        m, seed, size, metric = (estimate[k] for k in ("measure", "seed", "n", "metric"))
        a = [r[metric] for r in metric_values[m, seed, "A"][:size]]
        b = [r[metric] for r in metric_values[m, seed, "B"][:size]]
        c = [[r[metric] for r in metric_values[m, seed, f"AB_{j}"][:size]] for j in range(S.K)]
        recalculated = S.jansen_indices(a, b, c)
        assert recalculated["status"] == estimate["status"]
        for key in ("first", "total"):
            if recalculated[key] is None:
                assert estimate[key] is None
            else:
                np.testing.assert_allclose(recalculated[key], estimate[key], rtol=1e-12, atol=1e-12)
    return {"status": "VERIFIED_SOFTWARE_AND_DATA_INTEGRITY_ONLY", "hashed_artifacts": len(hashes),
            "parameter_rows": len(rows_seen), "source_scaling_checks": source_scaling_checks,
            "geometric_relation_checks": direct_reach_checks, "sensitivity_vectors_recomputed": len(estimates),
            "experimental_validation_added": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), ensure_ascii=False, indent=2))
