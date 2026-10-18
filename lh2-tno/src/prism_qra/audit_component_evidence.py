"""Read-only audit of the saved FFI Test 4 matched-sensor evidence chain.

Recomputes statistics, not dispersion. Does not distribute sensor records or
authorize current PRISM physics. Run a separately fingerprinted model replay next.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


SUPPORT = ("radius_m", "height_m", "sensor_bearing_deg", "model_axis_bearing_deg",
           "x_downwind_m", "y_crosswind_m", "averaging_time_s")


def sensor_rows(rows: list[dict]) -> dict[str, dict]:
    if not rows:
        raise ValueError("no prediction rows")
    normalized = {}
    for row in rows:
        key = str(row["sensor"])
        if not key.strip() or key in normalized:
            raise ValueError("missing/duplicate sensor identity")
        if int(row["test"]) != 4:
            raise ValueError("wrong experiment")
        values = {k: float(row[k]) for k in (*SUPPORT, "observed_time_mean_vol_pct",
                                           "SLABx_time_mean_vol_pct", "residual_vol_pct")}
        if not all(math.isfinite(x) for x in values.values()):
            raise ValueError("nonfinite input/prediction")
        observed = values["observed_time_mean_vol_pct"]
        predicted = values["SLABx_time_mean_vol_pct"]
        if not (0 <= observed <= 100 and 0 <= predicted <= 100):
            raise ValueError("invalid vol-percent concentration")
        if not math.isclose(predicted-observed, values["residual_vol_pct"], abs_tol=1e-10):
            raise ValueError("stored residual inconsistent")
        if (int(row["observed_LFL"]) != int(observed >= 4)
                or int(row["SLABx_LFL"]) != int(predicted >= 4)):
            raise ValueError("stored LFL flag inconsistent")
        normalized[key] = values
    return normalized


def metrics(rows: dict[str, dict]) -> dict:
    if not rows:
        raise ValueError("no sensor rows")
    residuals = [r["SLABx_time_mean_vol_pct"]-r["observed_time_mean_vol_pct"]
                 for r in rows.values()]
    observed = [r["observed_time_mean_vol_pct"] >= 4 for r in rows.values()]
    predicted = [r["SLABx_time_mean_vol_pct"] >= 4 for r in rows.values()]
    n = len(rows)
    return {"n_sensor_height_pairs": n, "bias_vol_pct": math.fsum(residuals)/n,
            "MAE_vol_pct": math.fsum(abs(x) for x in residuals)/n,
            "RMSE_vol_pct": math.sqrt(math.fsum(x*x for x in residuals)/n),
            "observed_LFL_pairs": sum(observed), "predicted_LFL_pairs": sum(predicted),
            "TP": sum(o and p for o, p in zip(observed, predicted)),
            "FN": sum(o and not p for o, p in zip(observed, predicted)),
            "FP": sum(not o and p for o, p in zip(observed, predicted)),
            "TN": sum(not o and not p for o, p in zip(observed, predicted))}


def audit_levels(prior_rows: list[dict], final_rows: list[dict],
                 summaries: list[dict], observations: list[dict]) -> dict:
    prior, final = sensor_rows(prior_rows), sensor_rows(final_rows)
    if set(prior) != set(final) or len(final) != 30:
        raise ValueError("matched 30-sensor support required")
    for key in final:
        for field in (*SUPPORT, "observed_time_mean_vol_pct"):
            if prior[key][field] != final[key][field]:
                raise ValueError("refinement changed observation/support")
    obs = [x for x in observations if int(x["test"]) == 4]
    if len(obs) != 30 or len({x["sensor"] for x in obs}) != 30:
        raise ValueError("source observations must contain 30 unique sensor pairs")
    if {x["sensor"] for x in obs} != set(final):
        raise ValueError("observations and predictions have different sensor identities")
    for row in obs:
        actual = final[row["sensor"]]
        for source_key, key in (("R_m", "radius_m"), ("z_m", "height_m"),
                                ("bearing_deg", "sensor_bearing_deg"),
                                ("averaging_time_s", "averaging_time_s"),
                                ("observed_mean_vol_pct", "observed_time_mean_vol_pct")):
            if float(row[source_key]) != actual[key]:
                raise ValueError("saved observation or support differs from original reduction")
    if len(summaries) != 2 or [int(x["n_field_steps"]) for x in summaries] != [320, 640]:
        raise ValueError("expected 320/640 refinement summaries")
    calculated = [metrics(prior), metrics(final)]
    for summary, calc in zip(summaries, calculated):
        for key, value in calc.items():
            if key == "TN":
                continue  # original summary does not store TN
            if not math.isclose(float(summary[key]), value, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"saved summary mismatch: {key}")
    changes = {k: abs(calculated[1][k]-calculated[0][k]) /
               max(abs(calculated[0][k]), abs(calculated[1][k]), 1e-12)
               for k in ("bias_vol_pct", "MAE_vol_pct", "RMSE_vol_pct")}
    swapped = [key for key in final if (prior[key]["SLABx_time_mean_vol_pct"] >= 4)
               != (final[key]["SLABx_time_mean_vol_pct"] >= 4)]
    return {"saved_metrics_verified": True, "sensor_support_verified": True,
            "metric_relative_changes": changes, "sensor_LFL_change_count": len(swapped),
            "stored_refinement_gate_passed": not swapped and all(v < .02 for v in changes.values()),
            "metrics": calculated[1], "model_replayed": False,
            "physical_validation_claim": False,
            "qualification": "saved-prediction audit only; not current PRISM model authorization"}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def fingerprint(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = {"prior_predictions": args.evidence_dir / "sensor_predictions_n320.csv",
             "final_predictions": args.evidence_dir / "sensor_predictions_n640.csv",
             "refinement_summary": args.evidence_dir / "refinement_summary.csv",
             "observations": args.observations}
    before = {k: fingerprint(p) for k, p in paths.items()}
    report = audit_levels(*(read_csv(paths[k]) for k in paths))
    after = {k: fingerprint(p) for k, p in paths.items()}
    if before != after:
        raise RuntimeError("evidence changed during audit")
    report["artifacts"] = before
    report["audit_code"] = fingerprint(Path(__file__))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise FileExistsError("audit outputs are immutable; choose a new output path")
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("artifacts", "audit_code")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
