"""Sequential N=512 extension for discontinuous GH2 edge-count Sobol indices.

The locked N=256 rows are reused as the first half of the same scrambled Sobol
sequences.  Only indices 256--511 are newly evaluated.  This is numerical
convergence evidence for a conditional synthetic screening experiment, not
physical validation, facility acceptance, QRA, or operational-DT evidence.
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

import statistical_pilot as S
import statistical_transfer as T


SCHEMA = "gh2-discontinuous-sobol-sequential-n512-v1"
PRIOR_N = 256
FINAL_N = 512
SEEDS = (*T.PILOT_SEEDS, *T.NEW_SEEDS)
EDGE_METRICS = tuple(
    f"edges:{layout}:{curve}" for layout in T.ALL_LAYOUTS for curve in S.CURVES
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict[str, str]:
    code = Path(__file__).resolve().parent
    names = ("statistical_convergence_extension.py", "statistical_transfer.py",
             "statistical_pilot.py", "source_term.py", "fire.py")
    return {name: sha256(code / name) for name in names}


def upstream_hashes(pilot: Path, transfer: Path) -> dict[str, dict[str, str]]:
    selected = {
        "pilot": (pilot, ("protocol.json", "design_results.jsonl", "summary.json",
                           "artifact_hashes.json")),
        "transfer": (transfer, ("protocol.json", "new_design_results.jsonl",
                                 "sensitivity_estimates.json", "summary.json",
                                 "artifact_hashes.json")),
    }
    result = {}
    for label, (directory, names) in selected.items():
        missing = [name for name in names if not (directory / name).is_file()]
        if missing:
            raise FileNotFoundError(f"missing {label} artifacts: {missing}")
        result[label] = {name: sha256(directory / name) for name in names}
    return result


def verify_artifact_manifest(directory: Path) -> None:
    manifest = json.loads((directory / "artifact_hashes.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        path = directory / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"upstream artifact integrity failure: {path}")


def assert_prefix_identity(seed: int) -> None:
    prior = S.sampling_design(PRIOR_N, seed)
    extended = S.sampling_design(FINAL_N, seed)
    if set(prior) != set(extended):
        raise AssertionError("Sobol block set changed")
    for block in prior:
        if not np.array_equal(prior[block], extended[block][:PRIOR_N]):
            raise AssertionError(f"N=256 prefix changed for seed={seed}, block={block}")


def tail_designs() -> dict[int, dict[str, np.ndarray]]:
    designs = {}
    for seed in SEEDS:
        assert_prefix_identity(seed)
        full = S.sampling_design(FINAL_N, seed)
        designs[seed] = {block: values[PRIOR_N:] for block, values in full.items()}
    return designs


def protocol(pilot: Path, transfer: Path) -> dict:
    for seed in SEEDS:
        assert_prefix_identity(seed)
    pilot_protocol = json.loads((pilot / "protocol.json").read_text(encoding="utf-8"))
    transfer_protocol = json.loads((transfer / "protocol.json").read_text(encoding="utf-8"))
    if pilot_protocol.get("base_n") != PRIOR_N or tuple(pilot_protocol.get("seeds", ())) != T.PILOT_SEEDS:
        raise ValueError("pilot prefix is not the locked N=256 design")
    if transfer_protocol.get("base_n") != PRIOR_N:
        raise ValueError("transfer prefix is not the locked N=256 design")
    if tuple(transfer_protocol.get("new_independent_scrambles", ())) != T.NEW_SEEDS:
        raise ValueError("transfer scramble set changed")
    return {
        "schema": SCHEMA,
        "claim_level": "NUMERICAL_CONVERGENCE_OF_CONDITIONAL_SYNTHETIC_SCREENING_ONLY",
        "trigger": (
            "The locked N=256 transfer assessment found only 3/24 discontinuous "
            "edge-count metrics meeting its predeclared exploratory convergence rule."
        ),
        "prior_n": PRIOR_N,
        "final_n": FINAL_N,
        "new_tail_indices": [PRIOR_N, FINAL_N - 1],
        "scrambles": list(SEEDS),
        "design_measures": list(S.MEASURES),
        "layouts": T.ALL_LAYOUTS,
        "related_curves": list(S.CURVES),
        "edge_metrics": list(EDGE_METRICS),
        "reuse_rule": (
            "N=256 is byte-identical to the first half of each N=512 scrambled "
            "Sobol block; only indices 256--511 are newly evaluated."
        ),
        "estimator": "Jansen first/total pick-freeze estimators, left unclipped",
        "metric_rule": {
            "primary_eligible_if_all": [
                "maximum absolute paired total-effect change N256-to-N512 across all variables and scrambles <= 0.1",
                "maximum across-variable N512 total-effect scramble IQR <= 0.1",
                "no N512 total-effect estimate outside exploratory interval [-0.05, 1.05]",
            ],
            "otherwise": "EXPLORATORY_APPENDIX",
        },
        "family_rule": (
            "The discontinuous Sobol family is eligible for the main quantitative "
            "claim only if at least 80% (20/24) of metrics are individually primary-eligible; "
            "otherwise exact magnitudes move to an exploratory appendix."
        ),
        "no_automatic_further_escalation": (
            "If N=512 fails, do not choose N=1024 after inspecting individual values; "
            "report the locked appendix decision unless a new sequential protocol is registered."
        ),
        "uncertainty_boundary": (
            "Scramble IQR and prefix change concern numerical sampling only, not model-form, "
            "physical, measurement, operational, or prediction uncertainty."
        ),
        "excluded_claims": [
            "physical validation", "actual facility safety", "failure probability",
            "empirical operating distribution", "operational digital-twin acceptance",
        ],
        "upstream_hashes": upstream_hashes(pilot, transfer),
        "code_hashes": code_hashes(),
    }


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def prepare_output(output: Path, pilot: Path, transfer: Path) -> dict:
    declared = protocol(pilot, transfer)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "protocol.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != json.loads(json.dumps(declared)):
            raise ValueError("N=512 protocol or code fingerprint changed; use a new output directory")
    elif any(output.iterdir()):
        raise ValueError("output directory must be empty before protocol lock")
    else:
        write_json(path, declared)
    return declared


def verify_upstream(pilot: Path, transfer: Path, declared: dict) -> None:
    actual = upstream_hashes(pilot, transfer)
    if actual != declared["upstream_hashes"]:
        raise ValueError("locked N=256 upstream changed after N=512 protocol registration")
    verify_artifact_manifest(pilot)
    verify_artifact_manifest(transfer)


def metric_store_row(store: dict, row: dict, layouts: dict) -> None:
    metrics = T.scalar_metrics(row, layouts)
    key = (row["measure"], int(row["seed"]), row["block"])
    if key not in store:
        store[key] = defaultdict(list)
    for metric in EDGE_METRICS:
        store[key][metric].append(float(metrics[metric]))


def load_prefix_rows(pilot: Path, transfer: Path) -> tuple[dict, dict]:
    store: dict = {}
    counts = Counter()
    with (pilot / "design_results.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            layouts = T.layout_outputs(row) if row.get("status") == "OK" else {}
            metric_store_row(store, row, layouts)
            counts["pilot_rows"] += 1
    with (transfer / "new_design_results.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            layouts = row.get("layout_evaluations", {})
            if row.get("status") == "OK" and layouts != T.layout_outputs(row):
                raise ValueError("N=256 transfer layout result changed")
            metric_store_row(store, row, layouts)
            counts["transfer_rows"] += 1
    expected_keys = len(S.MEASURES) * len(SEEDS) * (S.K + 2)
    if len(store) != expected_keys:
        raise ValueError("incomplete N=256 metric block set")
    for key, metrics in store.items():
        if set(metrics) != set(EDGE_METRICS):
            raise ValueError(f"incomplete edge metric set: {key}")
        if any(len(values) != PRIOR_N for values in metrics.values()):
            raise ValueError(f"N=256 block length mismatch: {key}")
    return store, dict(counts)


def calculate_tail(output: Path, workers: int, store: dict) -> tuple[int, dict]:
    designs = tail_designs()
    cache = S.acquire_sources(S.source_jobs(designs), output, workers)
    rows = 0
    with (output / "tail_design_results.jsonl").open("w", encoding="utf-8") as stream:
        for measure in S.MEASURES:
            for seed, blocks in designs.items():
                for block, unit in blocks.items():
                    for offset, x in enumerate(S.transform(unit, measure), start=PRIOR_N):
                        row = S.evaluate(x, cache)
                        row.update({"measure": measure, "seed": seed,
                                    "block": block, "index": offset})
                        layouts = T.layout_outputs(row) if row.get("status") == "OK" else {}
                        stored = {**row, "layout_evaluations": layouts}
                        stream.write(json.dumps(stored, ensure_ascii=False, allow_nan=False) + "\n")
                        metric_store_row(store, row, layouts)
                        rows += 1
                print(f"N=512 tail evaluated: {measure}, scramble {seed}", flush=True)
    for key, metrics in store.items():
        if any(len(values) != FINAL_N for values in metrics.values()):
            raise AssertionError(f"N=512 block length mismatch: {key}")
    return rows, cache


def calculate_sensitivity(store: dict) -> list[dict]:
    records = []
    for measure in S.MEASURES:
        for seed in SEEDS:
            a = store[(measure, seed, "A")]
            b = store[(measure, seed, "B")]
            for metric in EDGE_METRICS:
                hybrids = [store[(measure, seed, f"AB_{j}")][metric]
                           for j in range(S.K)]
                for size in (PRIOR_N, FINAL_N):
                    estimate = S.jansen_indices(
                        np.asarray(a[metric])[:size], np.asarray(b[metric])[:size],
                        [np.asarray(values)[:size] for values in hybrids],
                    )
                    records.append({"measure": measure, "seed": seed,
                                    "metric": metric, "n": size, **estimate})
    return records


def compare_locked_n256(records: list[dict], transfer: Path) -> dict:
    prior_records = json.loads((transfer / "sensitivity_estimates.json").read_text(encoding="utf-8"))
    prior = {(r["measure"], r["seed"], r["metric"]): r for r in prior_records
             if r["n"] == PRIOR_N and r["metric"] in EDGE_METRICS}
    current = {(r["measure"], r["seed"], r["metric"]): r for r in records
               if r["n"] == PRIOR_N}
    if set(prior) != set(current):
        raise ValueError("N=256 sensitivity record key mismatch")
    max_error = 0.
    comparisons = 0
    for key in prior:
        if prior[key]["status"] != current[key]["status"]:
            raise ValueError(f"N=256 sensitivity status drift: {key}")
        for field in ("first", "total"):
            error = float(np.max(np.abs(
                np.asarray(prior[key][field], dtype=float)
                - np.asarray(current[key][field], dtype=float))))
            max_error = max(max_error, error)
            comparisons += S.K
    if max_error != 0.:
        raise ValueError(f"N=256 sensitivity drift: {max_error}")
    return {"vectors": len(current) * 2, "scalar_comparisons": comparisons,
            "max_absolute_error": max_error}


def summarize(records: list[dict]) -> dict:
    result = {}
    for measure in S.MEASURES:
        for metric in EDGE_METRICS:
            prior = {r["seed"]: r for r in records if r["measure"] == measure
                     and r["metric"] == metric and r["n"] == PRIOR_N}
            final = {r["seed"]: r for r in records if r["measure"] == measure
                     and r["metric"] == metric and r["n"] == FINAL_N}
            if set(prior) != set(SEEDS) or set(final) != set(SEEDS):
                result[f"{measure}|{metric}"] = {"status": "WITHHELD_INCOMPLETE"}
                continue
            if any(r["status"] != "ESTIMATED" for r in (*prior.values(), *final.values())):
                result[f"{measure}|{metric}"] = {"status": "WITHHELD_ESTIMATOR"}
                continue
            p = np.asarray([prior[seed]["total"] for seed in SEEDS], dtype=float)
            f = np.asarray([final[seed]["total"] for seed in SEEDS], dtype=float)
            change = np.abs(f - p)
            q25, q75 = np.quantile(f, [.25, .75], axis=0)
            max_change = float(change.max())
            max_iqr = float((q75 - q25).max())
            excursion = bool((f < -.05).any() or (f > 1.05).any())
            eligible = max_change <= .1 and max_iqr <= .1 and not excursion
            dominant = np.argmax(f, axis=1)
            dominant_counts = Counter(S.PARAMETERS[int(i)].name for i in dominant)
            spacing_i = S.K - 1
            result[f"{measure}|{metric}"] = {
                "status": "PRIMARY_ELIGIBLE" if eligible else "EXPLORATORY_APPENDIX",
                "scrambles": len(SEEDS),
                "total_n256_median": np.median(p, axis=0).tolist(),
                "total_n512_median": np.median(f, axis=0).tolist(),
                "total_n512_q25": q25.tolist(),
                "total_n512_q75": q75.tolist(),
                "total_n512_min": f.min(axis=0).tolist(),
                "total_n512_max": f.max(axis=0).tolist(),
                "max_absolute_paired_change_n256_to_n512": max_change,
                "max_total_n512_iqr": max_iqr,
                "estimator_excursion_n512": excursion,
                "dominant_n512_by_scramble": dict(sorted(dominant_counts.items())),
                "dominant_n512_consensus": max(dominant_counts, key=dominant_counts.get),
                "dominant_n512_consensus_fraction": max(dominant_counts.values()) / len(SEEDS),
                "spacing_total_n256_median": float(np.median(p[:, spacing_i])),
                "spacing_total_n512_median": float(np.median(f[:, spacing_i])),
                "spacing_total_n512_q25": float(q25[spacing_i]),
                "spacing_total_n512_q75": float(q75[spacing_i]),
            }
    return result


def render_figures(output: Path, summary: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    labels = [f"{layout}\n{curve.replace('development_upper', 'upper')}"
              for layout in T.ALL_LAYOUTS for curve in S.CURVES]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True, constrained_layout=True)
    for ax, measure in zip(axes, S.MEASURES):
        items = [summary["metrics"][f"{measure}|{metric}"] for metric in EDGE_METRICS]
        values = [item["max_absolute_paired_change_n256_to_n512"] for item in items]
        colors = ["#2a7f9e" if item["status"] == "PRIMARY_ELIGIBLE" else "#c94f5c"
                  for item in items]
        ax.bar(range(len(items)), values, color=colors)
        ax.axhline(.1, color="black", ls="--", lw=1, label="locked threshold = 0.1")
        ax.axvline(5.5, color="gray", ls=":", lw=1)
        ax.set(ylabel="Max |ST(N512) - ST(N256)|", title=measure)
        ax.legend(loc="upper right")
    axes[-1].set_xticks(range(len(labels)), labels, rotation=35, ha="right")
    fig.suptitle("Sequential convergence of discontinuous edge-count total effects")
    fig.savefig(output / "01_n256_n512_change.png", dpi=190)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True, constrained_layout=True)
    for ax, measure in zip(axes, S.MEASURES):
        items = [summary["metrics"][f"{measure}|{metric}"] for metric in EDGE_METRICS]
        med = np.asarray([item["spacing_total_n512_median"] for item in items])
        q25 = np.asarray([item["spacing_total_n512_q25"] for item in items])
        q75 = np.asarray([item["spacing_total_n512_q75"] for item in items])
        colors = ["#2a7f9e" if item["status"] == "PRIMARY_ELIGIBLE" else "#c94f5c"
                  for item in items]
        ax.errorbar(range(len(items)), med, yerr=np.vstack((med - q25, q75 - med)),
                    fmt="none", ecolor="#506b75", capsize=3)
        ax.scatter(range(len(items)), med, c=colors, s=38)
        ax.axvline(5.5, color="gray", ls=":", lw=1)
        ax.set(ylabel="Spacing ST at N=512\nmedian [IQR]", title=measure)
    axes[-1].set_xticks(range(len(labels)), labels, rotation=35, ha="right")
    fig.suptitle("N=512 spacing total effects; blue metrics satisfy every locked rule")
    fig.savefig(output / "02_n512_spacing_effect.png", dpi=190)
    plt.close(fig)


def render_report(output: Path, summary: dict) -> None:
    counts = summary["counts"]
    lines = [
        "# 불연속 Sobol N=512 순차 확장 결과", "", "## 판정", "",
        f"N=512에서 개별 불연속 edge-count 지표 {counts['edge_metrics']}개 중 {counts['primary_eligible_metrics']}개가 결과 전 고정한 기준을 모두 충족했다.", "",
        f"사전 family 기준은 최소 {counts['family_required_metrics']}개 통과였다. 최종 family 판정은 `{summary['family_decision']}`이다.", "",
        "`EXPLORATORY_APPENDIX`이면 불연속 Sobol 총효과의 정확한 크기는 본문 핵심 정량결론에서 제외하고 부록의 수치수렴 진단으로 낮춘다. spacing이 반복적으로 최대라는 정성적 관찰도 선언한 가상 배치·범위에 조건부로만 기술한다.", "",
        "## 순차 계산 규모", "", "| 항목 | 값 |", "|---|---:|",
        f"| 기존/최종 base N | {counts['prior_n']} / {counts['final_n']} |",
        f"| scramble | {counts['scrambles']} |",
        f"| 신규 열역학 상태 | {counts['new_thermodynamic_source_states']:,} |",
        f"| 신규 후반 pick-freeze 행 | {counts['new_tail_rows']:,} |",
        f"| 신규 저장 배치×곡선 관계 | {counts['new_tail_layout_curve_relations']:,} |",
        f"| 방출원 실패 | {counts['new_source_failures']} |",
        "| 독립 물리실험 추가 | 0 |", "",
        "기존 N=256은 같은 scrambled Sobol sequence의 앞부분과 byte-identical함을 모든 seed·block에서 확인했다. N=256 민감도 벡터도 잠긴 이전 산출물과 정확히 일치했다.", "",
        "## 지표별 결과", "",
        "| 표본화 | 배치/곡선 | N256→512 최대변화 | N512 최대 IQR | 범위이탈 | N512 최대효과 합의 | 판정 |", "|---|---|---:|---:|---|---|---|",
    ]
    for key, item in summary["metrics"].items():
        measure, metric = key.split("|", 1)
        lines.append(
            f"| {measure} | {metric.removeprefix('edges:')} | "
            f"{item['max_absolute_paired_change_n256_to_n512']:.3f} | "
            f"{item['max_total_n512_iqr']:.3f} | {item['estimator_excursion_n512']} | "
            f"{item['dominant_n512_consensus']} ({item['dominant_n512_consensus_fraction']:.0%}) | "
            f"{item['status']} |"
        )
    lines += ["", "## 논문 배치", "",
              f"주결과 유지 가능 지표는 {counts['primary_eligible_metrics']}개이고 부록으로 낮춰야 할 지표는 {counts['appendix_metrics']}개다. family 판정이 `EXPLORATORY_APPENDIX`이면 선택적으로 통과한 지표만 본문에 골라 싣지 않는다.", "",
              "본문에는 집합형 범주분율, 곡선별 최고집합 변화, 새 가상배치 전이 결과를 유지한다. 이 값들은 별도 8-scramble 안정성 결과가 있다. 불연속 Sobol은 계산 수렴 한계를 투명하게 보이는 부록 표·그림으로 사용한다.", "",
              "N=1024는 이번 값을 보고 자동으로 추가하지 않는다. 필요하면 새로운 순차 프로토콜과 종료규칙을 먼저 고정해야 한다.", "",
              "## 범위 경계", "",
              "이번 확장은 수치 표본 수렴만 다룬다. 독립 실험, 모델형식 불확실성, 실제 운전분포, 설비 취약도, 사고확률, 현장 디지털 트윈 성능을 추가하거나 검증하지 않는다.", "",
              "## 산출물", "",
              "- `protocol.json`: 결과 전에 고정한 순차 확장·판정·중단 규칙",
              "- `tail_design_results.jsonl`: 각 Sobol block의 신규 인덱스 256–511",
              "- `sensitivity_estimates.json`: N=256과 N=512 원시 Jansen 추정",
              "- `summary.json`: 판정과 도표의 수치 원본",
              "- `artifact_hashes.json`: 최종 산출물 체크섬", "",
              "![N 변화](01_n256_n512_change.png)", "",
              "![N512 spacing 총효과](02_n512_spacing_effect.png)", ""]
    (output / "불연속_Sobol_N512_결과.md").write_text("\n".join(lines), encoding="utf-8")


def run(output: Path, pilot: Path, transfer: Path, workers: int = 4) -> dict:
    if workers < 1:
        raise ValueError("positive worker count required")
    start = time.perf_counter()
    declared = prepare_output(output, pilot, transfer)
    verify_upstream(pilot, transfer, declared)
    store, prefix_counts = load_prefix_rows(pilot, transfer)
    print(f"Locked N=256 rows loaded: {sum(prefix_counts.values())}", flush=True)
    tail_rows, cache = calculate_tail(output, workers, store)
    records = calculate_sensitivity(store)
    locked_match = compare_locked_n256(records, transfer)
    write_json(output / "sensitivity_estimates.json", records)
    metric_summary = summarize(records)
    eligible = sum(item.get("status") == "PRIMARY_ELIGIBLE"
                   for item in metric_summary.values())
    required = int(np.ceil(.8 * len(metric_summary)))
    family = "PRIMARY_ELIGIBLE" if eligible >= required else "EXPLORATORY_APPENDIX"
    summary = {
        "schema": SCHEMA,
        "claim_level": "NUMERICAL_CONVERGENCE_ONLY",
        "family_decision": family,
        "counts": {
            "prior_n": PRIOR_N, "final_n": FINAL_N, "scrambles": len(SEEDS),
            "design_measures": len(S.MEASURES), "edge_metrics": len(metric_summary),
            "family_required_metrics": required, "primary_eligible_metrics": eligible,
            "appendix_metrics": len(metric_summary) - eligible,
            "locked_prefix_rows_reused": sum(prefix_counts.values()),
            "new_thermodynamic_source_states": len(cache),
            "new_source_failures": sum(row.get("status") != "OK" for row in cache.values()),
            "new_tail_rows": tail_rows,
            "new_tail_layout_curve_relations": tail_rows * len(T.ALL_LAYOUTS) * len(S.CURVES),
            "independent_physical_experiments_added": 0,
        },
        "locked_n256_exact_match": locked_match,
        "metrics": metric_summary,
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
    print(f"Family decision: {family}", flush=True)
    print(f"Completed: {output.resolve()}", flush=True)
    return summary


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=root / "논문" / "불연속Sobol_N512_20260901")
    parser.add_argument("--pilot", type=Path,
                        default=root / "논문" / "통계예비계산_20260901")
    parser.add_argument("--transfer", type=Path,
                        default=root / "논문" / "통계전이평가_20260901")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        prepare_output(args.out, args.pilot, args.transfer)
        print(f"N=512 protocol locked before evaluation: {args.out.resolve()}")
    else:
        run(args.out, args.pilot, args.transfer, args.workers)


if __name__ == "__main__":
    main()
