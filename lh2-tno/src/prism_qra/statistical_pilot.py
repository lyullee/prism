"""Reproducible, conditional GH2 source/flame-reach computational experiment.

This is NOT a QRA, a facility acceptance test, or an independent validation.
Only source_term.discharge and fire.molkov_flame_length are reused. The
unresolved notional-nozzle, radiation, dispersion and LH2 paths are excluded.
The two Molkov curves share an equation: they are NOT independent models.

All distributions below are experimental-design measures, NOT empirical
operating probabilities. Equipment scores count separately possible axial
reach relations, assuming each jet could point at each equal-height target.
They are neither simultaneous events, fragility estimates nor failure risks.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
import hashlib
from importlib.metadata import version
import itertools
import json
import math
from pathlib import Path
import platform
import time

import CoolProp.CoolProp as CP
import numpy as np
from scipy.stats import qmc

import fire
import source_term


SCHEMA = "gh2-conditional-reach-pilot-v1"
TAGS = ("A", "B", "C", "D")
PRESSURE_MULTIPLIERS = np.array([1.0, 0.7, 0.45, 0.25])
CURVES = ("fit", "development_upper")
MEASURES = ("log_diameter", "linear_diameter")
LAYOUTS = {
    "linear": ((0., 0.), (.8, 0.), (1.9, 0.), (3.2, 0.)),
    "compact": ((0., 0.), (1., 0.), (.4, .85), (1.8, .5)),
    "offset": ((0., 0.), (1.2, 0.), (.25, .8), (1.75, 1.3)),
}


@dataclass(frozen=True)
class Parameter:
    name: str
    low: float
    high: float
    unit: str
    basis: str


PARAMETERS = (
    Parameter("pressure_scale_mpa", 10., 70., "MPa absolute",
              "Design assumption; source pressures share fixed ratios, not independent pressures."),
    Parameter("temperature_k", 283.15, 303.15, "K",
              "Ambient-temperature design assumption, not a measured operating distribution."),
    *(Parameter(f"diameter_{tag}_mm", .5, 10., "mm",
                "Design window inside Molkov eq.8 marginal 0.4-10.1 mm development range; NOT joint validation.")
      for tag in TAGS),
    *(Parameter(f"cd_{tag}", .5, 1., "1",
                "Explicit engineering sensitivity range; NOT certified values, NOT fitted to benchmarks.")
      for tag in TAGS),
    Parameter("spacing_m", 5., 40., "m",
              "Arbitrary public synthetic layout scale; not a facility drawing or design recommendation."),
)
K = len(PARAMETERS)


def validate_n(n: int) -> None:
    if isinstance(n, bool) or not isinstance(n, int) or n < 8 or n & (n - 1):
        raise ValueError("base sample size must be a power of two, at least eight")


def sampling_design(n: int, seed: int, dimensions: int = K) -> dict[str, np.ndarray]:
    """Scrambled 2k-dimensional Sobol A/B design and A-with-B-column hybrids."""
    validate_n(n)
    ab = qmc.Sobol(d=2 * dimensions, scramble=True, seed=seed).random_base2(
        int(math.log2(n)))
    a, b = ab[:, :dimensions], ab[:, dimensions:]
    out = {"A": a, "B": b}
    for j in range(dimensions):
        c = a.copy()
        c[:, j] = b[:, j]
        out[f"AB_{j}"] = c
    return out


def transform(unit: np.ndarray, measure: str) -> np.ndarray:
    u = np.asarray(unit, dtype=float)
    if u.shape[-1] != K or not np.isfinite(u).all() or np.any((u < 0) | (u > 1)):
        raise ValueError("invalid unit-cube inputs")
    if measure not in MEASURES:
        raise ValueError("unknown design measure")
    lo = np.array([p.low for p in PARAMETERS])
    hi = np.array([p.high for p in PARAMETERS])
    x = lo + (hi - lo) * u
    if measure == "log_diameter":
        x[..., 2:6] = .5 * 20. ** u[..., 2:6]
    return x


def validate_physical(x: np.ndarray) -> None:
    x = np.asarray(x)
    lo = np.array([p.low for p in PARAMETERS])
    hi = np.array([p.high for p in PARAMETERS])
    if x.shape != (K,) or not np.isfinite(x).all() or np.any((x < lo) | (x > hi)):
        raise ValueError("REFUSED_OUTSIDE_DECLARED_PILOT_DOMAIN")


def source_key(pressure_pa: float, temperature_k: float) -> str:
    return f"{float(pressure_pa).hex()}|{float(temperature_k).hex()}"


def source_jobs(designs: dict[int, dict[str, np.ndarray]]) -> dict[str, tuple[float, float]]:
    jobs = {}
    for blocks in designs.values():
        for unit in blocks.values():
            x = transform(unit, MEASURES[0])
            for row in x:
                for ratio in PRESSURE_MULTIPLIERS:
                    p, t = float(row[0] * ratio * 1e6), float(row[1])
                    jobs[source_key(p, t)] = (p, t)
    return dict(sorted(jobs.items()))


def solve_source(job: tuple[str, tuple[float, float]]) -> dict:
    key, (p, t) = job
    start = time.perf_counter()
    try:
        # Flux is independent of diameter and Cd in this direct-hole model.
        # Only this exact factorization is cached, not interpolated physics.
        r = source_term.discharge(p, t, "Hydrogen", .001, Cd=1., n_scan=240)
        h0 = CP.PropsSI("H", "P", p, "T", t, "Hydrogen")
        s0 = CP.PropsSI("S", "P", p, "T", t, "Hydrogen")
        ht = CP.PropsSI("H", "P", r.throat_pressure_pa, "S", s0, "Hydrogen")
        residual = abs(h0 - ht - .5 * r.velocity_m_s ** 2) / max(abs(h0), 1.)
        if not math.isfinite(r.mass_flux_kg_m2s) or r.mass_flux_kg_m2s <= 0:
            raise ValueError("invalid mass flux")
        return {"key": key, "status": "OK", "pressure_pa": p, "temperature_k": t,
                "flux_kg_m2s": r.mass_flux_kg_m2s,
                "throat_pressure_pa": r.throat_pressure_pa, "choked": r.choked,
                "source_energy_relative_residual": residual,
                "elapsed_s": time.perf_counter() - start}
    except Exception as exc:
        return {"key": key, "status": "FAILED", "pressure_pa": p, "temperature_k": t,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_s": time.perf_counter() - start}


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def fingerprints() -> dict:
    root = Path(__file__).resolve().parent
    names = ("statistical_pilot.py", "source_term.py", "fire.py")
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def study_protocol(n: int, seeds: list[int]) -> dict:
    return {
        "schema": SCHEMA, "base_n": n, "seeds": seeds, "parameters": [asdict(p) for p in PARAMETERS],
        "design": "scrambled Sobol A/B and pick-freeze hybrids; Jansen first/total effects",
        "measures": list(MEASURES), "layouts": LAYOUTS,
        "pressure_multipliers": PRESSURE_MULTIPLIERS.tolist(),
        "source": "source_term.discharge; 240-point isentropic maximum-flux scan; CoolProp Hydrogen",
        "curves": {"fit": "76*(mdot*d)^0.347", "development_upper": "116*(mdot*d)^0.347"},
        "reach": "distance <= flame length; equal-height target with separately target-directed jet; no obstacles",
        "score": "inbound count of separately possible axial reach; no frequencies or failure probabilities",
        "ties": "all positive maximum-score targets retained; all-zero case has EMPTY priority set",
        "information": "exact piecewise reach patterns over independent Cd intervals [0.5,1]; hypothetical perfect revelation at design-row Cd; curves kept as non-probabilistic alternatives",
        "convergence": "prefix estimates and between-scramble ranges; no physical confidence interval; flags use exploratory absolute index change 0.1",
        "excluded": ["notional nozzle M01", "dispersion and LFL", "radiation factor 22.7", "LH2 and M02", "time-varying releases", "ignition/failure frequencies", "wind/buoyancy/obstacles", "equipment fragility", "full QRA and operational digital twin acceptance"],
        "claims_withheld": ["independent physical validation", "actual facility safety", "failure probability", "universal upper safety bound", "formal value of information"],
        "references": [
            "Molkov & Saffers (2013), IJHE 38:8141-8158, eq.8; https://doi.org/10.1016/j.ijhydene.2012.08.106; development-data reuse is not independent validation.",
            "Local handoffs 17, 20, 26: source and joint pressure-diameter validation gaps remain.",
            "Jansen (1999), CPC 117:35-43; https://doi.org/10.1016/S0010-4655(98)00154-4.",
            "scipy.stats.qmc.Sobol, installed version recorded in environment.json.",
        ],
        "source_hashes": fingerprints(),
    }


def acquire_sources(jobs: dict, output: Path, workers: int) -> dict:
    path = output / "source_states.jsonl"
    results = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["key"] in results:
                raise ValueError("duplicate cached source state")
            results[r["key"]] = r
        if not set(results) <= set(jobs):
            raise ValueError("unexpected cached source keys")
    pending = [(key, value) for key, value in jobs.items() if key not in results]
    if pending:
        print(f"Source states: {len(results)} cached; {len(pending)} pending", flush=True)
        with ProcessPoolExecutor(max_workers=workers) as pool, path.open("a", encoding="utf-8") as stream:
            for i, r in enumerate(pool.map(solve_source, pending, chunksize=4), 1):
                results[r["key"]] = r
                stream.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")
                if i % 256 == 0 or i == len(pending):
                    stream.flush()
                    print(f"Source states completed {i}/{len(pending)}", flush=True)
    return results


def priority_mask(scores: np.ndarray) -> int:
    values = np.asarray(scores)
    if values.shape != (4,) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("four finite non-negative scores required")
    if values.max() == 0:
        return 0
    return sum(1 << i for i, value in enumerate(values) if value == values.max())


def unique_positive(mask: int) -> bool:
    return mask > 0 and mask & (mask - 1) == 0


def distance_matrix(layout: str, spacing: float) -> np.ndarray:
    xy = np.array(LAYOUTS[layout]) * spacing
    distance = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=-1)
    np.fill_diagonal(distance, np.inf)  # no self-exposure edges
    return distance


def reach_scores(lengths: np.ndarray, distances: np.ndarray) -> tuple[np.ndarray, int]:
    if lengths.shape != (4,) or not np.isfinite(lengths).all() or (lengths <= 0).any():
        raise ValueError("positive finite lengths required")
    reached = distances <= lengths[:, None]
    scores = reached.sum(axis=0)
    return scores, priority_mask(scores)


def evaluate(x: np.ndarray, cache: dict) -> dict:
    validate_physical(x)
    flux = []
    for ratio in PRESSURE_MULTIPLIERS:
        state = cache[source_key(x[0] * ratio * 1e6, x[1])]
        if state["status"] != "OK":
            return {"status": "SOURCE_FAILED", "failed_key": state["key"], "inputs": x.tolist()}
        flux.append(state["flux_kg_m2s"])
    diameters = x[2:6] * .001
    rate_cd1 = np.array(flux) * np.pi * diameters ** 2 / 4.
    rates = rate_cd1 * x[6:10]
    # Call the production scalar correlation, bypassing flame_length(),
    # which would also execute the unresolved nozzle/radiation paths.
    lengths = np.array([[fire.molkov_flame_length(q, d, conservative=upper)
                         for q, d in zip(rates, diameters)] for upper in (False, True)])
    ideal_rates = np.array([source_term.ideal_gas_choked(
        x[0] * ratio * 1e6, x[1], d, Cd=cd)
        for ratio, d, cd in zip(PRESSURE_MULTIPLIERS, diameters, x[6:10])])
    scores, masks, edges = [], [], []
    for layout in LAYOUTS:
        dm = distance_matrix(layout, x[-1])
        by_curve = [reach_scores(length, dm) for length in lengths]
        scores.append([s.tolist() for s, _ in by_curve])
        masks.append([m for _, m in by_curve])
        edges.append([int(s.sum()) for s, _ in by_curve])
    return {"status": "OK", "inputs": x.tolist(), "rates_kg_s": rates.tolist(),
            "rate_cd1_kg_s": rate_cd1.tolist(), "ideal_rates_kg_s": ideal_rates.tolist(),
            "flame_lengths_m": lengths.tolist(), "scores": scores, "priority_masks": masks,
            "edge_counts": edges, "total_rate_kg_s": float(rates.sum()),
            "max_flame_fit_m": float(lengths[0].max())}


def jansen_indices(a, b, hybrids) -> dict:
    a, b, c = np.asarray(a, float), np.asarray(b, float), np.asarray(hybrids, float)
    if a.ndim != 1 or b.shape != a.shape or c.ndim != 2 or c.shape[1] != a.size:
        raise ValueError("invalid pick-freeze array shape")
    if not all(np.isfinite(v).all() for v in (a, b, c)):
        return {"status": "WITHHELD_INCOMPLETE_DESIGN", "first": None, "total": None}
    var = float(np.var(np.concatenate((a, b)), ddof=1))
    if var <= 0:
        return {"status": "UNDEFINED_ZERO_VARIANCE", "first": None, "total": None}
    first = 1. - np.mean((b[None, :] - c) ** 2, axis=1) / (2. * var)
    total = np.mean((a[None, :] - c) ** 2, axis=1) / (2. * var)
    # Never clip noisy estimators to [0,1]; excursions are convergence evidence.
    return {"status": "ESTIMATED", "first": first.tolist(), "total": total.tolist()}


def scalar_metrics(result: dict) -> dict[str, float]:
    names = ["total_rate_kg_s", "max_flame_fit_m"]
    names += [f"edges:{layout}:{curve}" for layout in LAYOUTS for curve in CURVES]
    if result["status"] != "OK":
        return dict.fromkeys(names, float("nan"))
    values = [result[n] for n in names[:2]] + list(np.array(result["edge_counts"]).ravel())
    return dict(zip(names, map(float, values)))


def source_patterns(distances: np.ndarray, lo: float, hi: float) -> list[np.ndarray]:
    """Exactly enumerate all binary reach rows for a continuous length interval."""
    if not 0 < lo <= hi:
        raise ValueError("invalid length interval")
    candidates = [lo, hi]
    for d in distances[np.isfinite(distances)]:
        if lo <= d <= hi:
            candidates.append(float(d))
            if lo < d:
                candidates.append(float(np.nextafter(d, -np.inf)))
    return [np.array(row, dtype=int) for row in sorted({tuple(distances <= v) for v in candidates})]


def possible_priorities(result: dict, layout: str, known: tuple[int, ...] = ()) -> set[int]:
    """Exact reach-pattern enumeration, not endpoint-only or Monte Carlo guessing.

    A curve is selected globally; it is never independently mixed per source.
    Unknown Cd values are independent set-valued assumptions, not random data.
    """
    if result["status"] != "OK":
        raise ValueError("cannot rank a failed calculation")
    x = np.array(result["inputs"])
    distances = distance_matrix(layout, x[-1])
    options = set()
    for curve_i, upper in enumerate((False, True)):
        patterns = []
        for i in range(4):
            if i in known:
                length = result["flame_lengths_m"][curve_i][i]
                patterns.append([np.array(distances[i] <= length, dtype=int)])
            else:
                q = result["rate_cd1_kg_s"][i]
                d = x[2 + i] * .001
                low = fire.molkov_flame_length(.5 * q, d, conservative=upper)
                high = fire.molkov_flame_length(q, d, conservative=upper)
                patterns.append(source_patterns(distances[i], low, high))
        for rows in itertools.product(*patterns):
            options.add(priority_mask(np.sum(rows, axis=0)))
    return options


def information_summary(base_rows: list[dict]) -> dict:
    summary = {}
    for layout in LAYOUTS:
        observations = []
        for r in base_rows:
            if r["status"] != "OK":
                continue
            sets = [possible_priorities(r, layout, known)
                    for known in ((), (0,), (1,), (2,), (3,), (0, 1, 2, 3))]
            if any(not s <= sets[0] for s in sets[1:]):
                raise AssertionError("information cannot expand the feasible priority set")
            observations.append({"options": [len(s) for s in sets],
                                 "unique": [len(s) == 1 and unique_positive(next(iter(s))) for s in sets]})
        summary[layout] = {"rows": len(observations),
            "states": ["none_known", "cd_A_known", "cd_B_known", "cd_C_known", "cd_D_known", "all_cd_known"],
            "mean_possible_priority_sets": np.mean([o["options"] for o in observations], axis=0).tolist() if observations else None,
            "unique_priority_guaranteed_fraction": np.mean([o["unique"] for o in observations], axis=0).tolist() if observations else None}
    return summary


def rank_summary(base_rows: list[dict]) -> dict:
    valid = [r for r in base_rows if r["status"] == "OK"]
    out = {"base_rows": len(base_rows), "valid_rows": len(valid), "failed_rows": len(base_rows) - len(valid), "layouts": {}}
    for li, layout in enumerate(LAYOUTS):
        if not valid:
            out["layouts"][layout] = {"status": "WITHHELD_NO_VALID_ROWS"}
            continue
        masks = np.array([r["priority_masks"][li] for r in valid])
        scores = np.array([r["scores"][li] for r in valid])
        active_both = (masks > 0).all(axis=1)
        changed = masks[:, 0] != masks[:, 1]
        curves = {}
        for ci, curve in enumerate(CURVES):
            m = masks[:, ci]
            curves[curve] = {"empty_fraction": float(np.mean(m == 0)),
                            "unique_fraction": float(np.mean([unique_positive(int(v)) for v in m])),
                            "tied_fraction": float(np.mean([v > 0 and not unique_positive(int(v)) for v in m])),
                            "top_membership_fraction": [float(np.mean((m & (1 << i)) > 0)) for i in range(4)]}
        unique_both = np.array([unique_positive(int(a)) and unique_positive(int(b)) for a, b in masks])
        out["layouts"][layout] = {
            "status": "CONDITIONAL_DESIGN_FRACTIONS", "rows": len(valid),
            "score_vector_change_fraction": float(np.mean(np.any(scores[:, 0] != scores[:, 1], axis=1))),
            "priority_set_change_fraction": float(np.mean(changed)),
            "active_both_rows": int(active_both.sum()),
            "priority_set_change_active_both_fraction": float(np.mean(changed[active_both])) if active_both.any() else None,
            "unique_both_rows": int(unique_both.sum()),
            "unique_leader_reversal_rows": int(np.sum(changed & unique_both)),
            "curves": curves,
        }
    return out


def numerical_checks(cache: dict, rows: list[dict]) -> dict:
    valid_states = [r for _, r in sorted(cache.items()) if r["status"] == "OK"]
    checks = []
    if valid_states:
        for idx in np.unique(np.linspace(0, len(valid_states) - 1, min(16, len(valid_states)), dtype=int)):
            r = valid_states[int(idx)]
            refined = source_term.discharge(r["pressure_pa"], r["temperature_k"], "Hydrogen", .001, n_scan=960)
            checks.append({"key": r["key"], "relative_flux_change_240_to_960":
                           abs(refined.mass_flux_kg_m2s / r["flux_kg_m2s"] - 1.)})
    scaling = []
    good = [r for r in rows if r["status"] == "OK"]
    if good:
        for idx in np.unique(np.linspace(0, len(good) - 1, min(8, len(good)), dtype=int)):
            r = good[int(idx)]
            x = r["inputs"]
            for i, ratio in enumerate(PRESSURE_MULTIPLIERS):
                direct = source_term.discharge(x[0] * ratio * 1e6, x[1], "Hydrogen", x[2 + i] * .001, Cd=x[6 + i])
                scaling.append(abs(direct.rate_kg_s / r["rates_kg_s"][i] - 1.))
    return {"source_refinement": checks,
            "source_refinement_max_relative_change": max((c["relative_flux_change_240_to_960"] for c in checks), default=None),
            "exact_cache_scaling_comparisons": len(scaling), "exact_cache_scaling_max_relative_error": max(scaling, default=None),
            "max_source_energy_relative_residual": max((r["source_energy_relative_residual"] for r in valid_states), default=None),
            "note": "Checks concern the discharge throat, not the unresolved downstream notional nozzle. Refinement checks are a subset, not a full numerical-convergence proof."}


def summarize_sensitivity(records: list[dict], n: int) -> dict:
    out = {}
    groups = sorted({(r["measure"], r["metric"]) for r in records})
    for measure, metric in groups:
        final = [r for r in records if r["measure"] == measure and r["metric"] == metric and r["n"] == n and r["status"] == "ESTIMATED"]
        previous = [r for r in records if r["measure"] == measure and r["metric"] == metric and r["n"] == n // 2 and r["status"] == "ESTIMATED"]
        if not final:
            out[f"{measure}|{metric}"] = {"status": "WITHHELD"}
            continue
        totals = np.array([r["total"] for r in final])
        first = np.array([r["first"] for r in final])
        span = np.ptp(totals, axis=0)
        jumps = [np.abs(np.array(f["total"]) - np.array(p["total"]))
                 for f in final for p in previous if f["seed"] == p["seed"]]
        delta = float(np.max(jumps)) if jumps else None
        out[f"{measure}|{metric}"] = {
            "status": "PILOT_ESTIMATE_NOT_CONFIDENCE_INTERVAL", "total_mean": totals.mean(axis=0).tolist(),
            "first_mean": first.mean(axis=0).tolist(), "total_seed_min": totals.min(axis=0).tolist(),
            "total_seed_max": totals.max(axis=0).tolist(), "max_total_seed_span": float(span.max()),
            "max_total_prefix_change": delta,
            "requires_more_samples": bool(span.max() > .1 or delta is None or delta > .1 or
                                          (totals < -.05).any() or (totals > 1.05).any()),
            "flag_threshold_is_exploratory": True,
        }
    return out


def run_study(output: Path, n: int = 256, seeds: tuple[int, ...] = (20260901, 20260902), workers: int = 4) -> dict:
    validate_n(n)
    if len(set(seeds)) != len(seeds) or len(seeds) < 2 or workers < 1:
        raise ValueError("at least two distinct scrambles and a positive worker count are required")
    start = time.perf_counter()
    protocol = study_protocol(n, list(seeds))
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = output / "protocol.json"
    # Never silently mix caches after changing code, scope or sampling design.
    if protocol_path.exists():
        existing = json.loads(protocol_path.read_text(encoding="utf-8"))
        if existing != json.loads(json.dumps(protocol)):
            raise ValueError("protocol/source fingerprint changed; select a new output directory")
    elif any(output.iterdir()):
        raise ValueError("output directory must be empty or contain an identical protocol")
    else:
        write_json(protocol_path, protocol)
    designs = {seed: sampling_design(n, seed) for seed in seeds}
    cache = acquire_sources(source_jobs(designs), output, workers)
    all_base = {measure: [] for measure in MEASURES}
    sensitivity_records, status_counts = [], {}
    prefix_sizes = [v for v in (8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096) if v <= n]
    if n not in prefix_sizes:
        prefix_sizes.append(n)
    with (output / "design_results.jsonl").open("w", encoding="utf-8") as stream:
        for measure in MEASURES:
            for seed, blocks in designs.items():
                metrics = {}
                for block, unit in blocks.items():
                    block_metrics = []
                    for idx, x in enumerate(transform(unit, measure)):
                        r = evaluate(x, cache)
                        r.update({"measure": measure, "seed": seed, "block": block, "index": idx})
                        stream.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")
                        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
                        block_metrics.append(scalar_metrics(r))
                        if block in ("A", "B"):
                            all_base[measure].append(r)
                    metrics[block] = {key: np.array([r[key] for r in block_metrics]) for key in block_metrics[0]}
                for metric in metrics["A"]:
                    for size in prefix_sizes:
                        indices = jansen_indices(metrics["A"][metric][:size], metrics["B"][metric][:size],
                                                 [metrics[f"AB_{j}"][metric][:size] for j in range(K)])
                        sensitivity_records.append({"measure": measure, "seed": seed, "metric": metric, "n": size, **indices})
                print(f"Evaluated {measure}, scramble {seed}", flush=True)
    information = {}
    for measure, base_rows in all_base.items():
        information[measure] = information_summary(base_rows)
        print(f"Exact set-valued information analysis completed: {measure}", flush=True)
    write_json(output / "sensitivity_estimates.json", sensitivity_records)
    summary = {
        "schema": SCHEMA, "claim_level": "CONDITIONAL_SYNTHETIC_SCREENING_ONLY",
        "counts": {"base_n_per_scramble": n, "scrambles": len(seeds), "independent_physical_experiments_added": 0,
                   "design_measures": len(MEASURES), "parameters": K, "synthetic_layouts": len(LAYOUTS),
                   "related_flame_curves": len(CURVES), "unique_thermodynamic_source_states": len(cache),
                   "source_failures": sum(r["status"] != "OK" for r in cache.values()),
                   "pick_freeze_parameter_rows": sum(status_counts.values()),
                   "base_AB_rows_per_measure": len(next(iter(all_base.values()))),
                   "layout_curve_evaluations": status_counts.get("OK", 0) * len(LAYOUTS) * len(CURVES),
                   "status_counts": status_counts},
        "rank": {measure: rank_summary(rows) for measure, rows in all_base.items()},
        "information": information,
        "sensitivity": summarize_sensitivity(sensitivity_records, n),
        "numerical_checks": numerical_checks(cache, all_base[MEASURES[0]]),
        "source_hashes": protocol["source_hashes"],
        "computation_elapsed_s": time.perf_counter() - start,
    }
    write_json(output / "summary.json", summary)
    write_json(output / "environment.json", {
        "python": platform.python_version(), "platform": platform.platform(), "workers": workers,
        "libraries": {p: version(p) for p in ("CoolProp", "numpy", "scipy", "matplotlib")},
        "timing": "batch computation wall time excluding process startup and figure/report rendering; uncontrolled local load; not real-time DT latency"})
    render_outputs(output, summary, all_base)
    artifact_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(output.iterdir()) if p.is_file() and p.name != "artifact_hashes.json"}
    write_json(output / "artifact_hashes.json", artifact_hashes)
    print(json.dumps(summary["counts"], ensure_ascii=False), flush=True)
    print(f"Completed: {output.resolve()}", flush=True)
    return summary


def render_outputs(output: Path, summary: dict, base: dict) -> None:
    # Scientific figures use explicit axes and conditional labels, not AI images.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    colors = ("#196b83", "#cc6b27", "#5b4794")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    color_max = max((r["flame_lengths_m"][0][0] for rows in base.values() for r in rows if r["status"] == "OK"), default=1.)
    for ax, measure in zip(axes, MEASURES):
        rows = [r for r in base[measure] if r["status"] == "OK"]
        sc = ax.scatter([r["inputs"][0] for r in rows], [r["inputs"][2] for r in rows],
                        c=[r["flame_lengths_m"][0][0] for r in rows], s=12, cmap="viridis", vmin=0, vmax=color_max)
        ax.set(xlabel="Source A pressure (MPa absolute)", ylabel="Source A diameter (mm)", title=measure.replace("_", " "))
        fig.colorbar(sc, ax=ax, label="Source A fitted flame length (m)")
    fig.suptitle("Synthetic design coverage — NOT a validation or facility-safety map")
    fig.savefig(output / "01_design_coverage.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    for ax, metric, title in zip(axes, ("total_rate_kg_s", "edges:compact:fit"),
                                 ("Total source mass flow", "Compact layout: axial-reach edge count")):
        for i, measure in enumerate(MEASURES):
            s = summary["sensitivity"][f"{measure}|{metric}"]
            if "total_mean" not in s:
                continue
            x = np.arange(K) + (i - .5) * .3
            mean, low, high = map(np.array, (s["total_mean"], s["total_seed_min"], s["total_seed_max"]))
            ax.errorbar(x, mean, yerr=np.array([mean - low, high - mean]), fmt="o", capsize=3,
                        color=colors[i], label=measure)
        ax.set_xticks(range(K), ["P", "T", "dA", "dB", "dC", "dD", "CdA", "CdB", "CdC", "CdD", "spacing"], rotation=45)
        ax.set(title=title, ylabel="Jansen total-effect estimate (unclipped)")
        ax.axhline(0, color="gray", lw=.5)
        ax.legend(fontsize=8)
    fig.suptitle("Pilot sensitivity — error bars are scramble ranges, NOT confidence intervals")
    fig.savefig(output / "02_global_sensitivity.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for ax, measure in zip(axes, MEASURES):
        for li, layout in enumerate(LAYOUTS):
            rows = [r for r in base[measure] if r["status"] == "OK"]
            bins = np.linspace(5, 40, 6)
            means = []
            counts = []
            for a, b in zip(bins[:-1], bins[1:]):
                selected = [r for r in rows if a <= r["inputs"][-1] < b]
                means.append(np.mean([r["priority_masks"][li][0] != r["priority_masks"][li][1] for r in selected]) if selected else np.nan)
                counts.append(len(selected))
            ax.plot((bins[:-1] + bins[1:]) / 2, means, "o-", color=colors[li], label=layout)
        ax.set(xlabel="Synthetic layout spacing scale (m)", ylabel="Fraction with changed top set", ylim=(0, 1), title=f"{measure}; n={min(counts)}–{max(counts)} per bin")
        ax.legend()
    fig.suptitle("Related fitted/upper curves: priority-set changes (ties and empty sets retained)")
    fig.savefig(output / "03_priority_stability.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True, constrained_layout=True)
    for ax, measure in zip(axes, MEASURES):
        for i, layout in enumerate(LAYOUTS):
            s = summary["information"][measure][layout]
            if s["mean_possible_priority_sets"] is not None:
                ax.plot(np.arange(6) + (i - 1) * .13, s["mean_possible_priority_sets"], "o", label=layout, color=colors[i])
        ax.set_xticks(range(6), ["None", "Cd A", "Cd B", "Cd C", "Cd D", "All Cd"])
        ax.set(xlabel="Hypothetically revealed coefficients (each alternative starts from None)",
               ylabel="Mean number of feasible top sets", title=measure)
        ax.legend()
    fig.suptitle("Information sensitivity — exact reach-pattern sets; NOT formal value of information")
    fig.savefig(output / "04_information_sensitivity.png", dpi=180)
    plt.close(fig)

    counts = summary["counts"]
    checks = summary["numerical_checks"]
    lines = ["# 통계 예비 계산 결과", "", "## 핵심 범위", "",
             "이 결과는 공개 가상 GH2 설비의 **조건부 수치 스크리닝**이다. 현장 데이터, 독립 실험, 검증된 절대 위험도 또는 설비 고장확률이 아니다.", "",
             "현재 생산 코드의 방출량 계산과 Molkov 화염 길이 함수만 사용했다. 가상 노즐·분산·복사·LH2·과도 방출·점화/누출 빈도·장애물/바람·설비 취약도는 계산하지 않았다.", "",
             "두 화염 곡선은 같은 식의 최적합선과 개발자료 상한선이다. 독립 모델 두 개 또는 보장된 안전 한계가 아니다. 화염 길이가 거리를 넘는 경우의 ‘방향 미정 잠재 도달’만 세며, 실제 접촉·손상 판정이 아니다.", "",
             "## 표본을 어떻게 세었는가", "",
             "| 항목 | 값 |", "|---|---:|",
             *[f"| {key} | {value} |" for key, value in counts.items() if key != "status_counts"], "",
             "기본 A/B 표본과 민감도용 혼합 표본은 구분했다. 배치·화염 곡선·표본화 방식 간 비교는 짝지어진 계산이며 독립 실험으로 세지 않는다. 열역학 상태 캐시는 정확한 면적×Cd 비례관계만 재사용한다.", "",
             "## 관리 검토 순위의 변화", "",
             "입력 분포는 실측 확률이 아니라 설계 범위를 덮기 위한 가정이다. 아래 비율의 모집단은 이 가상 설계이며 실제 사고 발생확률이 아니다. 최고 점수 동률은 모두 남기고 모든 점수가 0이면 후보 집합을 비운다.", "",
             "| 표본화 | 배치 | 유효 기본 행 | 점수벡터 변화 | 최고집합 변화 | 양쪽 유일 1위 역전 건수 |", "|---|---|---:|---:|---:|---:|"]
    for measure in MEASURES:
        for layout, r in summary["rank"][measure]["layouts"].items():
            if "rows" in r:
                lines.append(f"| {measure} | {layout} | {r['rows']} | {r['score_vector_change_fraction']:.1%} | {r['priority_set_change_fraction']:.1%} | {r['unique_leader_reversal_rows']} |")
    lines += ["", "‘최고집합 변화’는 동률의 해소·추가와 무도달↔도달 전환도 포함하므로 유일 1위 역전 비율로 부르면 안 된다.", "",
              "## 전역 민감도와 표본 수렴", "",
              "Jansen 분산 기반 1차·총효과를 전용 pick-freeze 설계로 계산했다. 변수 간 독립성은 선언된 설계좌표에 대한 것이며 실제 설비에서의 독립성을 주장하지 않는다. source pressure들은 공통 배율로 연결되어 있다.", "",
              "| 표본화 | 지표 | 최대 총효과 변수 | 총효과 추정 | 두 scramble 최대 차이 | 마지막 표본 증가 최대 변화 | 추가 표본 필요 플래그 |",
              "|---|---|---|---:|---:|---:|---|"]
    for key, s in summary["sensitivity"].items():
        if "total_mean" not in s:
            continue
        i = int(np.argmax(s["total_mean"]))
        measure, metric = key.split("|", 1)
        delta = s["max_total_prefix_change"]
        lines.append(f"| {measure} | {metric} | {PARAMETERS[i].name} | {s['total_mean'][i]:.3f} | {s['max_total_seed_span']:.3f} | {delta:.3f} | {s['requires_more_samples']} |" if delta is not None else f"| {measure} | {metric} | {PARAMETERS[i].name} | {s['total_mean'][i]:.3f} | {s['max_total_seed_span']:.3f} | 미평가 | True |")
    lines += ["", "플래그는 총효과 추정의 절대 변화 0.1 등을 사용한 탐색 기준이다. 두 scramble의 범위는 신뢰구간이 아니며, 플래그가 없어도 전체 통계 수렴이나 현실 타당성이 입증되는 것은 아니다. 원시 추정치를 [0,1]로 잘라내지 않았다.", "",
              "## 정보 확보 민감도", "",
              "각 기본 조건에서 Cd의 가정 구간 전체를 유지한 뒤, 특정 Cd만 해당 가상 조건의 값으로 정확히 알게 되는 경우를 비교했다. 도달관계가 바뀌는 중간 임계값까지 열거했으며 양 끝점만 비교하지 않았다. 두 화염 곡선은 항상 별도 대안으로 남긴다.", "",
              "| 표본화 | 배치 | 미확보: 가능한 최고집합 평균 개수 | 모든 Cd 확보 후 | 확보 후에도 유일 1위가 보장되는 조건 비율 |", "|---|---|---:|---:|---:|"]
    for measure in MEASURES:
        for layout, r in summary["information"][measure].items():
            if r["mean_possible_priority_sets"] is not None:
                lines.append(f"| {measure} | {layout} | {r['mean_possible_priority_sets'][0]:.3f} | {r['mean_possible_priority_sets'][-1]:.3f} | {r['unique_priority_guaranteed_fraction'][-1]:.1%} |")
    lines += ["", "이는 자료 확보의 조건부 민감도다. 비용·의사결정 손실·실측 사전분포가 없어 경제적 가치나 정식 Value of Information은 계산하지 않았다. Cd가 다른 기하/상태 오차를 흡수할 수 있으므로 이 계산이 인증계수 확보만으로 전체 방출원을 검증한다는 뜻도 아니다.", "",
              "## 수치 확인", "",
              f"- 방출원 실패: {counts['source_failures']} / {counts['unique_thermodynamic_source_states']}",
              f"- 면적·Cd 캐시 재사용 직접 비교: {checks['exact_cache_scaling_comparisons']}건; 최대 상대오차 {checks['exact_cache_scaling_max_relative_error']}",
              f"- 방출원 240→960점 탐색의 확인 부분집합 최대 상대변화: {checks['source_refinement_max_relative_change']}",
              f"- 방출원 목 상태의 최대 상대 에너지 잔차: {checks['max_source_energy_relative_residual']}",
              "- 위 에너지 검사는 미해결 하류 가상 노즐(M01)의 해결을 뜻하지 않는다.", "",
              "## 논문 해석 및 다음 단계", "",
              "1. 이번 결과는 계산 기반과 통계 설계의 예비 증거다. 논문 게재 가능성이나 새로운 물리 현상을 입증한 결과는 아니다.",
              "2. 화염 길이의 구경·유량 의존성은 기존 상관식에 이미 내재한다. 그 추세를 새로운 발견으로 포장하지 않는다.",
              "3. 로그/선형 구경 표본화에 따라 결론이 바뀌면 그 차이를 결과로 보고하고, 어느 한 쪽만 골라 일반화하지 않는다.",
              "4. 민감도 수렴 플래그와 동률 비중을 보고 본 계산의 표본 수와 관리 지표를 결정한다. 같은 설계의 무작정 대량 반복은 독립 검증을 늘리지 않는다.",
              "5. 최종 논문에는 공개 실험 비교·공동 압력/구경 적용범위·별도 미사용 배치군 평가가 여전히 필요하다. 이번 3개 배치는 모두 분석에 사용했으며 외부 검증용 holdout이 아니다.",
              "6. 시간·기상·빈도·전체 위험도·실제 디지털 트윈으로 확대하려면 제외한 모델 문제와 증거 게이트 통합을 별도로 다룬다.", "",
              "## 산출물", "",
              "- protocol.json: 실행 전 범위·표본화·가정·출처·코드 지문", "- source_states.jsonl: 열역학 계산과 실패 기록",
              "- design_results.jsonl: 각 설계행의 입력·출력·배치별 점수 및 동률",
              "- sensitivity_estimates.json: 표본 크기별 원시 1차/총효과", "- summary.json: 본 문서 수치의 원본",
              "- environment.json / artifact_hashes.json: 실행환경·산출물 체크섬", "",
              "![설계 범위](01_design_coverage.png)", "", "![전역 민감도](02_global_sensitivity.png)", "",
              "![순위 안정성](03_priority_stability.png)", "", "![정보 확보 민감도](04_information_sensitivity.png)", ""]
    (output / "통계예비계산_결과.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--n", type=int, default=256)
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260901, 20260902])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run_study(args.out, args.n, tuple(args.seeds), args.workers)


if __name__ == "__main__":
    main()
