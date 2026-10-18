"""Post-pilot synthetic-layout transfer and scramble-convergence assessment.

This calculation extends the locked pilot with six new randomized Sobol
scrambles and three post-pilot, pre-evaluation synthetic layouts.  It is an
internal numerical transfer assessment, not external physical validation,
QRA, facility acceptance, or operational digital-twin validation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import time

import numpy as np

import set_valued_decision as D
import statistical_pilot as S


SCHEMA = "gh2-set-valued-synthetic-transfer-v1"
PILOT_SEEDS = (20260901, 20260902)
NEW_SEEDS = (20260911, 20260912, 20260913, 20260914, 20260915, 20260916)
HOLDOUT_LAYOUTS = {
    "triangle_tail": ((0., 0.), (1., 0.), (.5, .866), (2.8, .35)),
    "cluster_remote": ((0., 0.), (.42, .12), (.18, .58), (2.65, 1.45)),
    "asymmetric_zigzag": ((0., 0.), (.62, .78), (1.68, .16), (2.55, 1.22)),
}
ALL_LAYOUTS = {**S.LAYOUTS, **HOLDOUT_LAYOUTS}
PREFIX_SIZES = (8, 16, 32, 64, 128, 256)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict[str, str]:
    code = Path(__file__).resolve().parent
    names = ("statistical_transfer.py", "set_valued_decision.py",
             "statistical_pilot.py", "source_term.py", "fire.py")
    return {name: sha256(code / name) for name in names}


def pilot_hashes(pilot: Path) -> dict[str, str]:
    names = ("protocol.json", "design_results.jsonl", "sensitivity_estimates.json",
             "summary.json", "artifact_hashes.json")
    missing = [name for name in names if not (pilot / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing locked pilot artifacts: {missing}")
    return {name: sha256(pilot / name) for name in names}


def validate_layout_partition() -> None:
    if set(S.LAYOUTS) & set(HOLDOUT_LAYOUTS):
        raise AssertionError("analysis and transfer layout names overlap")
    spectra = {}
    for name, points in ALL_LAYOUTS.items():
        distances = D.distance_matrix(points, 1.)
        spectrum = tuple(np.round(np.sort(distances[np.isfinite(distances)]), 10))
        if spectrum in spectra:
            raise ValueError(f"layout distance spectrum duplicates {spectra[spectrum]}: {name}")
        spectra[spectrum] = name


def protocol(base_n: int, pilot: Path) -> dict:
    S.validate_n(base_n)
    validate_layout_partition()
    pilot_protocol = json.loads((pilot / "protocol.json").read_text(encoding="utf-8"))
    if pilot_protocol.get("schema") != S.SCHEMA:
        raise ValueError("unexpected pilot schema")
    if pilot_protocol.get("base_n") != base_n or tuple(pilot_protocol.get("seeds", ())) != PILOT_SEEDS:
        raise ValueError("locked pilot sampling design does not match transfer protocol")
    return {
        "schema": SCHEMA,
        "claim_level": "CONDITIONAL_SYNTHETIC_TRANSFER_ONLY",
        "base_n": base_n,
        "locked_pilot_scrambles": list(PILOT_SEEDS),
        "new_independent_scrambles": list(NEW_SEEDS),
        "total_scrambles": len(PILOT_SEEDS) + len(NEW_SEEDS),
        "design_measures": list(S.MEASURES),
        "parameters": [p.__dict__ for p in S.PARAMETERS],
        "analysis_layouts": S.LAYOUTS,
        "post_pilot_pre_evaluation_layouts": HOLDOUT_LAYOUTS,
        "layout_selection_note": (
            "The three transfer layouts were chosen after inspecting pilot results but are "
            "locked before their outputs or the six new scrambles are evaluated. They are "
            "synthetic internal transfer cases, not an external validation set."
        ),
        "set_valued_decision": {
            "uncertain_cd_interval": [0.5, 1.0],
            "curve_handling": "fit or development_upper selected globally; no source-wise mixing",
            "state_preservation": "exact correlated score-vector enumeration across reach thresholds",
            "categories": list(D.CATEGORIES),
            "possible_top": "union of non-empty admissible maximum-score sets",
            "necessary_top": "intersection across every admissible maximum-score set; zero if any no-reach state",
            "score_meaning": "inbound count of separately possible axial reach relations; not probability or risk",
        },
        "sensitivity": {
            "method": "Jansen pick-freeze first/total effects, estimators left unclipped",
            "prefix_n": list(PREFIX_SIZES),
            "replicate_summary": "median, IQR, min-max across eight independent Sobol scrambles",
            "exploratory_support_rule": (
                "max total-effect N=128-to-256 change <=0.1, max across-variable "
                "scramble IQR <=0.1, and no final estimate outside [-0.05,1.05]"
            ),
            "uncertainty_boundary": (
                "scramble variation is numerical randomization uncertainty only; it is not "
                "physical, model-form, operational, or prediction uncertainty"
            ),
        },
        "transfer_questions": [
            "How often is the management output robust unique, robust tied, all-no-reach, or indeterminate?",
            "Which equipment can or must belong to the top set under retained Cd/curve uncertainty?",
            "Do curve-sensitive top-set changes and dominant edge-count inputs persist in unused synthetic geometries?",
            "Do six additional scrambles reduce the unresolved convergence flags for discontinuous edge counts?",
        ],
        "excluded": [
            "notional nozzle M01", "dispersion and LFL", "radiation factor 22.7", "LH2 and M02",
            "time-varying releases", "ignition/leak/failure frequencies", "weather, buoyancy and obstacles",
            "equipment fragility", "full QRA", "facility acceptance", "operational digital-twin validation",
        ],
        "claims_withheld": [
            "independent physical validation", "actual facility safety", "failure probability",
            "universal upper safety bound", "empirical operating probability", "external validation",
        ],
        "locked_pilot_hashes": pilot_hashes(pilot),
        "code_hashes": code_hashes(),
    }


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def prepare_output(output: Path, base_n: int, pilot: Path) -> dict:
    declared = protocol(base_n, pilot)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "protocol.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != json.loads(json.dumps(declared)):
            raise ValueError("locked transfer protocol or code fingerprint changed; use a new output directory")
    elif any(output.iterdir()):
        raise ValueError("output directory must be empty before protocol lock")
    else:
        write_json(path, declared)
    return declared


def verify_locked_pilot(pilot: Path, declared: dict) -> None:
    actual = pilot_hashes(pilot)
    if actual != declared["locked_pilot_hashes"]:
        raise ValueError("locked pilot artifacts changed after transfer protocol registration")
    artifact_hashes = json.loads((pilot / "artifact_hashes.json").read_text(encoding="utf-8"))
    for name, expected in artifact_hashes.items():
        path = pilot / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"pilot artifact integrity failure: {name}")


def layout_outputs(result: dict) -> dict[str, dict]:
    if result.get("status") != "OK":
        raise ValueError("cannot evaluate layouts for a failed row")
    lengths = np.asarray(result["flame_lengths_m"], dtype=float)
    spacing = float(result["inputs"][-1])
    if lengths.shape != (2, 4) or not np.isfinite(lengths).all():
        raise ValueError("invalid flame lengths")
    out = {}
    for name, points in ALL_LAYOUTS.items():
        distances = D.distance_matrix(points, spacing)
        by_curve = [S.reach_scores(row, distances) for row in lengths]
        out[name] = {
            "scores": [scores.tolist() for scores, _ in by_curve],
            "priority_masks": [int(mask) for _, mask in by_curve],
            "edge_counts": [int(scores.sum()) for scores, _ in by_curve],
        }
    return out


def scalar_metrics(result: dict, layouts: dict[str, dict]) -> dict[str, float]:
    names = ["total_rate_kg_s", "max_flame_fit_m"]
    names += [f"edges:{layout}:{curve}" for layout in ALL_LAYOUTS for curve in S.CURVES]
    if result.get("status") != "OK":
        return dict.fromkeys(names, float("nan"))
    values = [float(result[name]) for name in names[:2]]
    values += [float(layouts[layout]["edge_counts"][curve_i])
               for layout in ALL_LAYOUTS for curve_i in range(len(S.CURVES))]
    return dict(zip(names, values))


def add_metric_row(store: dict, row: dict, metrics: dict[str, float]) -> None:
    key = (row["measure"], int(row["seed"]), row["block"])
    if key not in store:
        store[key] = defaultdict(list)
    for name, value in metrics.items():
        store[key][name].append(float(value))


def load_pilot_rows(pilot: Path, metric_store: dict, base_rows: list[dict]) -> int:
    count = 0
    with (pilot / "design_results.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            layouts = layout_outputs(row) if row.get("status") == "OK" else {}
            add_metric_row(metric_store, row, scalar_metrics(row, layouts))
            if row["block"] in ("A", "B"):
                base_rows.append(row)
            count += 1
    return count


def calculate_new_rows(
    output: Path,
    base_n: int,
    workers: int,
    metric_store: dict,
    base_rows: list[dict],
) -> tuple[int, dict]:
    designs = {seed: S.sampling_design(base_n, seed) for seed in NEW_SEEDS}
    cache = S.acquire_sources(S.source_jobs(designs), output, workers)
    path = output / "new_design_results.jsonl"
    row_count = 0
    with path.open("w", encoding="utf-8") as stream:
        for measure in S.MEASURES:
            for seed, blocks in designs.items():
                for block, unit in blocks.items():
                    for index, x in enumerate(S.transform(unit, measure)):
                        row = S.evaluate(x, cache)
                        row.update({"measure": measure, "seed": seed,
                                    "block": block, "index": index})
                        layouts = layout_outputs(row) if row.get("status") == "OK" else {}
                        stored = {**row, "layout_evaluations": layouts}
                        stream.write(json.dumps(stored, ensure_ascii=False, allow_nan=False) + "\n")
                        add_metric_row(metric_store, row, scalar_metrics(row, layouts))
                        if block in ("A", "B"):
                            base_rows.append(row)
                        row_count += 1
                print(f"New rows evaluated: {measure}, scramble {seed}", flush=True)
    return row_count, cache


def sensitivity_records(metric_store: dict, base_n: int) -> list[dict]:
    records = []
    for measure in S.MEASURES:
        for seed in (*PILOT_SEEDS, *NEW_SEEDS):
            a = metric_store[(measure, seed, "A")]
            b = metric_store[(measure, seed, "B")]
            for metric in a:
                hybrids = [metric_store[(measure, seed, f"AB_{j}")][metric]
                           for j in range(S.K)]
                for size in PREFIX_SIZES:
                    if size > base_n:
                        continue
                    estimate = S.jansen_indices(
                        np.asarray(a[metric])[:size], np.asarray(b[metric])[:size],
                        [np.asarray(values)[:size] for values in hybrids],
                    )
                    records.append({"measure": measure, "seed": seed,
                                    "metric": metric, "n": size, **estimate})
    return records


def summarize_sensitivity(records: list[dict], base_n: int) -> dict:
    out = {}
    groups = sorted({(r["measure"], r["metric"]) for r in records})
    for measure, metric in groups:
        final = [r for r in records if r["measure"] == measure and r["metric"] == metric
                 and r["n"] == base_n and r["status"] == "ESTIMATED"]
        previous = {r["seed"]: r for r in records
                    if r["measure"] == measure and r["metric"] == metric
                    and r["n"] == base_n // 2 and r["status"] == "ESTIMATED"}
        if len(final) != len(PILOT_SEEDS) + len(NEW_SEEDS):
            out[f"{measure}|{metric}"] = {"status": "WITHHELD_INCOMPLETE_SCRAMBLES"}
            continue
        totals = np.asarray([r["total"] for r in final], dtype=float)
        first = np.asarray([r["first"] for r in final], dtype=float)
        prefix_change = np.asarray([
            np.abs(np.asarray(r["total"]) - np.asarray(previous[r["seed"]]["total"]))
            for r in final
        ])
        q25, q75 = np.quantile(totals, [.25, .75], axis=0)
        max_iqr = float(np.max(q75 - q25))
        max_prefix = float(np.max(prefix_change))
        excursion = bool((totals < -.05).any() or (totals > 1.05).any())
        dominant = np.argmax(totals, axis=1)
        counts = Counter(S.PARAMETERS[int(i)].name for i in dominant)
        supported = max_iqr <= .1 and max_prefix <= .1 and not excursion
        out[f"{measure}|{metric}"] = {
            "status": "RANDOMIZED_QMC_REPLICATE_SUMMARY_NOT_PHYSICAL_CI",
            "scrambles": len(final),
            "total_mean": totals.mean(axis=0).tolist(),
            "total_median": np.median(totals, axis=0).tolist(),
            "total_q25": q25.tolist(),
            "total_q75": q75.tolist(),
            "total_min": totals.min(axis=0).tolist(),
            "total_max": totals.max(axis=0).tolist(),
            "first_median": np.median(first, axis=0).tolist(),
            "max_total_iqr": max_iqr,
            "max_total_seed_range": float(np.ptp(totals, axis=0).max()),
            "max_total_prefix_change_128_to_256": max_prefix,
            "estimator_excursion_outside_exploratory_bounds": excursion,
            "exploratory_convergence_supported": supported,
            "dominant_total_effect_by_scramble": dict(sorted(counts.items())),
            "dominant_total_effect_consensus": max(counts, key=counts.get),
            "dominant_total_effect_consensus_fraction": max(counts.values()) / len(final),
        }
    return out


def compact_decision(value: dict, include_relations: bool = True) -> dict:
    names = ("category", "admissible_score_state_count", "admissible_top_masks",
             "possible_top_mask", "necessary_top_mask", "possible_top_count",
             "necessary_top_count", "score_min", "score_max")
    out = {name: value[name] for name in names}
    if include_relations:
        out["robust_strict_outranking"] = value["robust_strict_outranking"]
    return out


def set_valued_analysis(base_rows: list[dict], output: Path) -> tuple[list[dict], int]:
    aggregates: dict[tuple[str, int, str], dict] = {}
    row_count = 0
    with (output / "decision_results.jsonl").open("w", encoding="utf-8") as stream:
        for row in base_rows:
            if row.get("status") != "OK":
                continue
            decisions = {}
            for layout, points in ALL_LAYOUTS.items():
                unknown = D.classify_result(row, points)
                known_all = D.classify_result(row, points, range(4))
                decisions[layout] = {
                    "retained_cd_curve_uncertainty": compact_decision(unknown),
                    "all_cd_known_curve_uncertainty_retained": compact_decision(
                        known_all, include_relations=False),
                }
                key = (row["measure"], int(row["seed"]), layout)
                if key not in aggregates:
                    aggregates[key] = {
                        "rows": 0, "categories": Counter(), "known_categories": Counter(),
                        "possible": np.zeros(4), "necessary": np.zeros(4),
                        "possible_count": 0., "necessary_count": 0., "state_count": 0.,
                        "robust_out": np.zeros((4, 4)),
                    }
                a = aggregates[key]
                a["rows"] += 1
                a["categories"][unknown["category"]] += 1
                a["known_categories"][known_all["category"]] += 1
                a["possible"] += [(unknown["possible_top_mask"] & (1 << i)) > 0 for i in range(4)]
                a["necessary"] += [(unknown["necessary_top_mask"] & (1 << i)) > 0 for i in range(4)]
                a["possible_count"] += unknown["possible_top_count"]
                a["necessary_count"] += unknown["necessary_top_count"]
                a["state_count"] += unknown["admissible_score_state_count"]
                a["robust_out"] += np.asarray(unknown["robust_strict_outranking"])
            stream.write(json.dumps({
                "measure": row["measure"], "seed": row["seed"], "block": row["block"],
                "index": row["index"], "inputs": row["inputs"], "decisions": decisions,
            }, ensure_ascii=False, allow_nan=False) + "\n")
            row_count += 1

    replicates = []
    for (measure, seed, layout), a in sorted(aggregates.items()):
        n = a["rows"]
        replicates.append({
            "measure": measure, "seed": seed, "layout": layout, "rows": n,
            "category_fraction": {category: a["categories"][category] / n for category in D.CATEGORIES},
            "all_cd_known_category_fraction": {
                category: a["known_categories"][category] / n for category in D.CATEGORIES
            },
            "possible_top_membership_fraction": (a["possible"] / n).tolist(),
            "necessary_top_membership_fraction": (a["necessary"] / n).tolist(),
            "mean_possible_top_count": a["possible_count"] / n,
            "mean_necessary_top_count": a["necessary_count"] / n,
            "mean_admissible_score_state_count": a["state_count"] / n,
            "robust_strict_outranking_fraction": (a["robust_out"] / n).tolist(),
        })
    return replicates, row_count


def summarize_replicates(replicates: list[dict]) -> dict:
    out = {}
    for measure in S.MEASURES:
        out[measure] = {}
        for layout in ALL_LAYOUTS:
            selected = [r for r in replicates if r["measure"] == measure and r["layout"] == layout]
            if len(selected) != len(PILOT_SEEDS) + len(NEW_SEEDS):
                raise AssertionError("incomplete set-valued scramble aggregation")
            category = {name: np.asarray([r["category_fraction"][name] for r in selected])
                        for name in D.CATEGORIES}
            known_category = {
                name: np.asarray([r["all_cd_known_category_fraction"][name] for r in selected])
                for name in D.CATEGORIES
            }
            out[measure][layout] = {
                "scrambles": len(selected), "rows_per_scramble": selected[0]["rows"],
                "category_fraction_median": {name: float(np.median(values))
                                             for name, values in category.items()},
                "category_fraction_q25": {name: float(np.quantile(values, .25))
                                          for name, values in category.items()},
                "category_fraction_q75": {name: float(np.quantile(values, .75))
                                          for name, values in category.items()},
                "category_fraction_min": {name: float(values.min()) for name, values in category.items()},
                "category_fraction_max": {name: float(values.max()) for name, values in category.items()},
                "all_cd_known_category_fraction_median": {
                    name: float(np.median(values)) for name, values in known_category.items()
                },
                "possible_top_membership_fraction_median": np.median(
                    [r["possible_top_membership_fraction"] for r in selected], axis=0).tolist(),
                "necessary_top_membership_fraction_median": np.median(
                    [r["necessary_top_membership_fraction"] for r in selected], axis=0).tolist(),
                "mean_possible_top_count_median": float(np.median(
                    [r["mean_possible_top_count"] for r in selected])),
                "mean_necessary_top_count_median": float(np.median(
                    [r["mean_necessary_top_count"] for r in selected])),
                "mean_admissible_score_state_count_median": float(np.median(
                    [r["mean_admissible_score_state_count"] for r in selected])),
                "robust_strict_outranking_fraction_median": np.median(
                    [r["robust_strict_outranking_fraction"] for r in selected], axis=0).tolist(),
            }
    return out


def rank_replicates(base_rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in base_rows:
        if row.get("status") == "OK":
            grouped[(row["measure"], int(row["seed"]))].append(layout_outputs(row))
    records = []
    for (measure, seed), evaluated_rows in sorted(grouped.items()):
        for layout in ALL_LAYOUTS:
            values = [row[layout] for row in evaluated_rows]
            masks = np.asarray([v["priority_masks"] for v in values])
            scores = np.asarray([v["scores"] for v in values])
            changed = masks[:, 0] != masks[:, 1]
            active = (masks > 0).all(axis=1)
            records.append({
                "measure": measure, "seed": seed, "layout": layout, "rows": len(evaluated_rows),
                "score_vector_change_fraction": float(np.mean(np.any(scores[:, 0] != scores[:, 1], axis=1))),
                "priority_set_change_fraction": float(np.mean(changed)),
                "priority_set_change_active_both_fraction": (
                    float(np.mean(changed[active])) if active.any() else None),
                "active_both_fraction": float(np.mean(active)),
                "fit_empty_fraction": float(np.mean(masks[:, 0] == 0)),
                "development_upper_empty_fraction": float(np.mean(masks[:, 1] == 0)),
            })
    return records


def summarize_rank(replicates: list[dict]) -> dict:
    out = {}
    fields = ("score_vector_change_fraction", "priority_set_change_fraction",
              "priority_set_change_active_both_fraction", "active_both_fraction",
              "fit_empty_fraction", "development_upper_empty_fraction")
    for measure in S.MEASURES:
        out[measure] = {}
        for layout in ALL_LAYOUTS:
            selected = [r for r in replicates if r["measure"] == measure and r["layout"] == layout]
            item = {"scrambles": len(selected), "rows_per_scramble": selected[0]["rows"]}
            for field in fields:
                values = np.asarray([r[field] for r in selected if r[field] is not None])
                item[field] = {
                    "median": float(np.median(values)), "q25": float(np.quantile(values, .25)),
                    "q75": float(np.quantile(values, .75)), "min": float(values.min()),
                    "max": float(values.max()), "replicates": len(values),
                } if len(values) else None
            out[measure][layout] = item
    return out


def render_figures(output: Path, summary: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    colors = ["#1b6f8a", "#68a9a5", "#d6b44c", "#d77a36", "#8c4f77"]

    fig, axes = plt.subplots(2, 3, figsize=(11.5, 7.2), constrained_layout=True)
    for ax, (name, points) in zip(axes.ravel(), ALL_LAYOUTS.items()):
        xy = np.asarray(points)
        ax.scatter(xy[:, 0], xy[:, 1], s=45, color="#145a70")
        for i, (x, y) in enumerate(xy):
            ax.annotate(S.TAGS[i], (x, y), xytext=(5, 5), textcoords="offset points")
        ax.set(title=f"{name} ({'analysis' if name in S.LAYOUTS else 'transfer'})",
               xlabel="normalized x", ylabel="normalized y", aspect="equal")
    fig.suptitle("Synthetic layouts — geometry transfer cases, not facility drawings")
    fig.savefig(output / "01_layout_partition.png", dpi=190)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(11.5, 7.5), sharex=True, constrained_layout=True)
    for ax, measure in zip(axes, S.MEASURES):
        bottom = np.zeros(len(ALL_LAYOUTS))
        for category, color in zip(D.CATEGORIES, colors):
            values = np.asarray([
                summary["set_valued"][measure][layout]["category_fraction_median"][category]
                for layout in ALL_LAYOUTS
            ])
            ax.bar(range(len(ALL_LAYOUTS)), values, bottom=bottom, color=color,
                   label=category.replace("_", " ").title())
            bottom += values
        ax.axvline(2.5, color="black", lw=.8, ls="--")
        ax.set(ylabel="Median conditional fraction", ylim=(0, 1), title=measure)
    axes[-1].set_xticks(range(len(ALL_LAYOUTS)), list(ALL_LAYOUTS), rotation=20)
    axes[0].legend(ncol=3, fontsize=7, loc="upper center")
    fig.suptitle("Exact set-valued management output across eight QMC scrambles")
    fig.savefig(output / "02_set_valued_categories.png", dpi=190)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True, constrained_layout=True)
    edge_metrics = [f"edges:{layout}:{curve}" for layout in ALL_LAYOUTS for curve in S.CURVES]
    for ax, measure in zip(axes, S.MEASURES):
        values, lower, upper, markers = [], [], [], []
        for metric in edge_metrics:
            item = summary["sensitivity"][f"{measure}|{metric}"]
            spacing_i = S.K - 1
            values.append(item["total_median"][spacing_i])
            lower.append(item["total_q25"][spacing_i])
            upper.append(item["total_q75"][spacing_i])
            markers.append(item["exploratory_convergence_supported"])
        values, lower, upper = map(np.asarray, (values, lower, upper))
        x = np.arange(len(values))
        ax.errorbar(x, values, yerr=np.vstack((values - lower, upper - values)),
                    fmt="none", ecolor="#496b78", capsize=3)
        ax.scatter(x, values, c=["#277da1" if ok else "#d1495b" for ok in markers], s=35)
        ax.axvline(5.5, color="black", lw=.8, ls="--")
        ax.set(ylabel="Spacing total effect\nmedian [IQR]", title=measure)
    labels = [f"{layout}\n{curve.replace('development_upper', 'upper')}"
              for layout in ALL_LAYOUTS for curve in S.CURVES]
    axes[-1].set_xticks(range(len(labels)), labels, rotation=35, ha="right")
    fig.suptitle("Discontinuous edge-count sensitivity; blue meets predeclared exploratory rule")
    fig.savefig(output / "03_scramble_convergence.png", dpi=190)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for ax, measure in zip(axes, S.MEASURES):
        medians = [summary["rank"][measure][layout]["priority_set_change_fraction"]["median"]
                   for layout in ALL_LAYOUTS]
        q25 = [summary["rank"][measure][layout]["priority_set_change_fraction"]["q25"]
               for layout in ALL_LAYOUTS]
        q75 = [summary["rank"][measure][layout]["priority_set_change_fraction"]["q75"]
               for layout in ALL_LAYOUTS]
        medians, q25, q75 = map(np.asarray, (medians, q25, q75))
        x = np.arange(len(ALL_LAYOUTS))
        ax.bar(x, medians, color=["#557f8c"] * 3 + ["#c7783c"] * 3)
        ax.errorbar(x, medians, yerr=np.vstack((medians - q25, q75 - medians)),
                    fmt="none", ecolor="black", capsize=3)
        ax.axvline(2.5, color="black", lw=.8, ls="--")
        ax.set_xticks(x, list(ALL_LAYOUTS), rotation=25, ha="right")
        ax.set(ylabel="Top-set change fraction\nmedian [IQR]", ylim=(0, 1), title=measure)
    fig.suptitle("Related fit/upper curves: paired top-set changes across layout partition")
    fig.savefig(output / "04_layout_transfer.png", dpi=190)
    plt.close(fig)


def render_report(output: Path, summary: dict) -> None:
    counts = summary["counts"]
    lines = [
        "# 집합형 관리판단·가상배치 전이평가", "", "## 결론부터", "",
        "이번 계산은 최고 점수 설비 하나를 강제로 고르지 않는다. Cd 구간과 두 관련 화염곡선을 유지한 채 가능한 점수벡터를 정확히 열거하여 `무도달`, `항상 유일 최고`, `항상 같은 동률집합`, `무도달 포함 판단 불가`, `활성 상태 판단 불가`로 구분했다.", "",
        "기존 3개 분석 배치에 더해, 예비결과를 본 뒤 선택했지만 계산 전에 고정한 3개 새 가상 배치와 6개 새 Sobol scramble을 평가했다. 이는 내부 수치 전이평가이지 외부 실험검증이 아니다.", "",
        "## 계산 규모", "", "| 항목 | 값 |", "|---|---:|",
        f"| 전체 scramble | {counts['total_scrambles']} |",
        f"| 새 scramble | {counts['new_scrambles']} |",
        f"| 새 열역학 상태 | {counts['new_thermodynamic_source_states']} |",
        f"| 새 pick-freeze 행 | {counts['new_pick_freeze_rows']} |",
        f"| 집합형 판단 기본행 | {counts['set_valued_base_rows']} |",
        f"| 분석/전이 가상배치 | {counts['analysis_layouts']} / {counts['transfer_layouts']} |",
        "| 추가 독립 물리실험 | 0 |", "",
        "## 집합형 판단 결과", "",
        "아래 값은 8개 scramble별 조건부 비율의 중앙값이다. 실제 사고확률이나 설비 고장확률이 아니다.", "",
        "| 표본화 | 배치 | 무도달 | 항상 유일 최고 | 항상 동률집합 | 무도달 포함 불명확 | 활성 상태 불명확 |", "|---|---|---:|---:|---:|---:|---:|",
    ]
    for measure in S.MEASURES:
        for layout in ALL_LAYOUTS:
            c = summary["set_valued"][measure][layout]["category_fraction_median"]
            lines.append(
                f"| {measure} | {layout} | {c['ALL_NO_REACH']:.1%} | {c['ROBUST_UNIQUE']:.1%} | "
                f"{c['ROBUST_TIED_SET']:.1%} | {c['INDETERMINATE_WITH_NO_REACH']:.1%} | {c['INDETERMINATE_ACTIVE']:.1%} |"
            )
    lines += ["", "`항상 최고`는 모든 허용 상태에서 최고집합에 포함된다는 뜻이다. 이것도 위험 우선순위나 정비 명령이 아니라 현재 제한된 도달관계 모델에서의 검토 후보 관계다.", "",
              "## 새 배치로의 전이", "",
              "| 표본화 | 배치 | fit↔upper 최고집합 변화 중앙값 | 양쪽 도달 조건 변화 중앙값 | fit 무도달 | upper 무도달 |", "|---|---|---:|---:|---:|---:|"]
    for measure in S.MEASURES:
        for layout in ALL_LAYOUTS:
            r = summary["rank"][measure][layout]
            conditional = r["priority_set_change_active_both_fraction"]
            conditional_text = f"{conditional['median']:.1%}" if conditional else "미정의"
            lines.append(
                f"| {measure} | {layout} | {r['priority_set_change_fraction']['median']:.1%} | "
                f"{conditional_text} | {r['fit_empty_fraction']['median']:.1%} | "
                f"{r['development_upper_empty_fraction']['median']:.1%} |"
            )
    edge = {key: value for key, value in summary["sensitivity"].items() if "|edges:" in key}
    supported = sum(value.get("exploratory_convergence_supported", False) for value in edge.values())
    spacing_consensus = sum(value.get("dominant_total_effect_consensus") == "spacing_m" for value in edge.values())
    lines += ["", "## 추가 scramble과 불연속 민감도", "",
              f"배치×곡선×표본화 edge-count 지표 {len(edge)}개 중 {supported}개가 사전 선언한 탐색적 수렴 기준을 충족했다. 이 기준은 N=128→256 변화, 8개 scramble IQR, 추정치 범위를 함께 본다.", "",
              f"{spacing_consensus}/{len(edge)}개 지표에서 spacing이 8개 scramble 중앙 총효과의 최대 변수였다. 이는 선언한 가상배치와 5–40 m 범위에 조건부인 결과이며 보편적 물리 법칙이 아니다.", "",
              "| 표본화 | 배치/곡선 | 중앙 최대효과 변수 | 합의 scramble 비율 | 최대 IQR | 최대 128→256 변화 | 기준 충족 |", "|---|---|---|---:|---:|---:|---|"]
    for key, value in edge.items():
        measure, metric = key.split("|", 1)
        lines.append(
            f"| {measure} | {metric.removeprefix('edges:')} | {value['dominant_total_effect_consensus']} | "
            f"{value['dominant_total_effect_consensus_fraction']:.0%} | {value['max_total_iqr']:.3f} | "
            f"{value['max_total_prefix_change_128_to_256']:.3f} | {value['exploratory_convergence_supported']} |"
        )
    lines += ["", "8개 scramble의 범위와 IQR은 신뢰구간이 아니다. 수치 표본화 변동만 보여주며, 모델형식·현장조건·계측·운영 불확실성은 포함하지 않는다.", "",
              "## 논문에서 허용되는 해석", "",
              "1. `단일 순위`가 아니라 `집합형 관리검토 후보`를 출력하면 무도달과 동률을 숨기지 않고 모델 불확실성을 운영 판단 구조에 전달할 수 있다.",
              "2. 새 가상 배치 결과는 기하형상 변화에 대한 내부 전이성 증거다. 실제 설비나 외부 시험으로 일반화하는 검증 증거는 아니다.",
              "3. 통계 규모는 충분히 커졌지만 독립 물리증거 수는 늘지 않았다. 논문의 강점은 대규모 조건부 계산·재현성·판단 불확실성 보존이다.",
              "4. M01 가상노즐, 분산/LFL, 복사계수, LH2/M02, 과도 결합, 취약도와 현장 디지털트윈 성능은 여전히 별도 검증 경계다.", "",
              "## 산출물", "",
              "- `protocol.json`: 결과 계산 전에 고정한 배치·scramble·판단정의·수렴기준",
              "- `new_design_results.jsonl`: 새 scramble의 물리출력과 6개 배치 도달결과",
              "- `decision_results.jsonl`: 모든 기본 A/B 행의 집합형 판단",
              "- `decision_replicates.json`: scramble별 집합형 판단 비율",
              "- `sensitivity_estimates.json`: 8개 scramble의 표본크기별 Jansen 추정",
              "- `summary.json`: 표·그림의 원자료", "",
              "![가상 배치 분할](01_layout_partition.png)", "", "![집합형 판단](02_set_valued_categories.png)", "",
              "![수렴성](03_scramble_convergence.png)", "", "![배치 전이](04_layout_transfer.png)", ""]
    (output / "집합형_전이평가_결과.md").write_text("\n".join(lines), encoding="utf-8")


def run(output: Path, pilot: Path, base_n: int = 256, workers: int = 4) -> dict:
    if workers < 1:
        raise ValueError("positive worker count required")
    start = time.perf_counter()
    declared = prepare_output(output, base_n, pilot)
    verify_locked_pilot(pilot, declared)
    metric_store: dict = {}
    base_rows: list[dict] = []
    pilot_rows = load_pilot_rows(pilot, metric_store, base_rows)
    print(f"Locked pilot rows loaded: {pilot_rows}", flush=True)
    new_rows, cache = calculate_new_rows(output, base_n, workers, metric_store, base_rows)
    records = sensitivity_records(metric_store, base_n)
    write_json(output / "sensitivity_estimates.json", records)
    decision_replicates, decision_rows = set_valued_analysis(base_rows, output)
    write_json(output / "decision_replicates.json", decision_replicates)
    rank_records = rank_replicates(base_rows)
    write_json(output / "rank_replicates.json", rank_records)
    sensitivity = summarize_sensitivity(records, base_n)
    summary = {
        "schema": SCHEMA,
        "claim_level": "CONDITIONAL_SYNTHETIC_TRANSFER_ONLY",
        "counts": {
            "base_n_per_scramble": base_n,
            "total_scrambles": len(PILOT_SEEDS) + len(NEW_SEEDS),
            "new_scrambles": len(NEW_SEEDS),
            "design_measures": len(S.MEASURES),
            "parameters": S.K,
            "analysis_layouts": len(S.LAYOUTS),
            "transfer_layouts": len(HOLDOUT_LAYOUTS),
            "related_flame_curves": len(S.CURVES),
            "locked_pilot_rows_reused": pilot_rows,
            "new_pick_freeze_rows": new_rows,
            "new_thermodynamic_source_states": len(cache),
            "new_source_failures": sum(r.get("status") != "OK" for r in cache.values()),
            "set_valued_base_rows": decision_rows,
            "set_valued_layout_evaluations": decision_rows * len(ALL_LAYOUTS),
            "independent_physical_experiments_added": 0,
        },
        "set_valued": summarize_replicates(decision_replicates),
        "rank": summarize_rank(rank_records),
        "sensitivity": sensitivity,
        "protocol_hash": sha256(output / "protocol.json"),
        "computation_elapsed_s": time.perf_counter() - start,
    }
    write_json(output / "summary.json", summary)
    write_json(output / "environment.json", {
        "python": platform.python_version(), "platform": platform.platform(), "workers": workers,
        "libraries": {p: version(p) for p in ("CoolProp", "numpy", "scipy", "matplotlib")},
        "timing_boundary": "uncontrolled local wall time; not digital-twin runtime latency",
    })
    render_figures(output, summary)
    render_report(output, summary)
    hashes = {p.name: sha256(p) for p in sorted(output.iterdir())
              if p.is_file() and p.name != "artifact_hashes.json"}
    write_json(output / "artifact_hashes.json", hashes)
    print(json.dumps(summary["counts"], ensure_ascii=False), flush=True)
    print(f"Completed: {output.resolve()}", flush=True)
    return summary


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=root / "논문" / "통계전이평가_20260901")
    parser.add_argument("--pilot", type=Path, default=root / "논문" / "통계예비계산_20260901")
    parser.add_argument("--n", type=int, default=256)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        prepare_output(args.out, args.n, args.pilot)
        print(f"Protocol locked before evaluation: {args.out.resolve()}")
    else:
        run(args.out, args.pilot, args.n, args.workers)


if __name__ == "__main__":
    main()
