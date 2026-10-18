"""
Result export.

Individual Risk contours as GeoJSON so they open in QGIS or on a web map
over a site plan, the FN curve as a table, and a bundle that keeps the
provenance attached to the numbers.

Contours from a grid without a contouring library
--------------------------------------------------
Marching squares on the log of the risk. Log because IR spans decades and
linear interpolation between 1e-6 and 1e-4 on a cell edge would put the
1e-5 line almost at the high corner; in log space it lands halfway, which
is what the field actually does between two grid points.

Provenance travels with the export
-----------------------------------
A GeoJSON handed to someone else loses every caveat the calculation
carried unless they are written into it. Each feature therefore records
the grade, whether the coverage was complete, and what the result may not
be claimed as. A contour that says PUBLISHED_UNVALIDATED on its face is
harder to misuse than one that does not.
"""

from __future__ import annotations

import json
import math
from typing import Any, Iterable, Optional

import numpy as np


# --------------------------------------------------------------------------
# contouring
# --------------------------------------------------------------------------

def _interp(v0: float, v1: float, level: float) -> float:
    """Fraction along an edge where the level is crossed, in log space."""
    if v0 == v1:
        return 0.5
    a = math.log10(max(v0, 1e-300))
    b = math.log10(max(v1, 1e-300))
    t = math.log10(level)
    if a == b:
        return 0.5
    return min(max((t - a) / (b - a), 0.0), 1.0)


def _segments(x: np.ndarray, y: np.ndarray, z: np.ndarray,
              level: float) -> list[tuple]:
    """Marching squares. Returns edge segments as ((x0,y0),(x1,y1))."""
    segs: list[tuple] = []
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    ny, nx = z.shape
    for j in range(ny - 1):
        for i in range(nx - 1):
            v = [float(z[j, i]), float(z[j, i + 1]),
                 float(z[j + 1, i + 1]), float(z[j + 1, i])]
            idx = sum((1 << k) for k, vv in enumerate(v) if vv >= level)
            if idx in (0, 15):
                continue
            px = [float(x[i]), float(x[i + 1]), float(x[i + 1]),
                  float(x[i])]
            py = [float(y[j]), float(y[j]), float(y[j + 1]),
                  float(y[j + 1])]
            pts = []
            for k in range(4):
                k2 = (k + 1) % 4
                if (v[k] >= level) != (v[k2] >= level):
                    t = _interp(v[k], v[k2], level)
                    pts.append((float(px[k] + t * (px[k2] - px[k])),
                                float(py[k] + t * (py[k2] - py[k]))))
            for a in range(0, len(pts) - 1, 2):
                segs.append((pts[a], pts[a + 1]))
    return segs


def _join(segs: list[tuple], tol: float) -> list[list[tuple]]:
    """Chain segments into polylines, closing loops where they meet."""
    remaining = list(segs)
    lines = []
    while remaining:
        a, b = remaining.pop()
        line = [a, b]
        changed = True
        while changed:
            changed = False
            for k, (c, d) in enumerate(remaining):
                if math.dist(line[-1], c) < tol:
                    line.append(d)
                elif math.dist(line[-1], d) < tol:
                    line.append(c)
                elif math.dist(line[0], c) < tol:
                    line.insert(0, d)
                elif math.dist(line[0], d) < tol:
                    line.insert(0, c)
                else:
                    continue
                remaining.pop(k)
                changed = True
                break
        lines.append(line)
    return lines


def contours(grid, levels: Optional[Iterable[float]] = None) -> dict:
    """{level: [polyline, ...]} in the grid's own coordinates, metres."""
    levels = list(levels) if levels is not None else grid.contour_levels()
    tol = grid.cell_size_m * 0.25
    out = {}
    for lv in levels:
        segs = _segments(grid.x, grid.y, grid.values, lv)
        if segs:
            out[lv] = _join(segs, tol)
    return out


# --------------------------------------------------------------------------
# GeoJSON
# --------------------------------------------------------------------------

def _to_lonlat(x_m, y_m, origin_lon: float,
               origin_lat: float) -> tuple[float, float]:
    """Local metres to WGS84, flat-earth about the origin. Good to a metre
    over a site and wrong over a region; a site plan is the former."""
    dlat = float(y_m) / 111_320.0
    dlon = float(x_m) / (111_320.0 * math.cos(math.radians(origin_lat)))
    return origin_lon + dlon, origin_lat + dlat


def ir_geojson(result, origin_lon: Optional[float] = None,
               origin_lat: Optional[float] = None,
               levels: Optional[Iterable[float]] = None) -> dict:
    """Individual Risk contours as a FeatureCollection.

    With no origin the coordinates stay in metres, which QGIS will take as
    a local CRS. With one they become WGS84 for a web map."""
    feats = []
    grade = result.grade.value
    complete = result.coverage.complete
    note = result.coverage.statement()
    for lv, lines in contours(result.grid, levels).items():
        for line in lines:
            if origin_lon is not None and origin_lat is not None:
                coords = [list(_to_lonlat(px, py, origin_lon, origin_lat))
                          for px, py in line]
            else:
                coords = [[float(px), float(py)] for px, py in line]
            feats.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "individual_risk_per_year": lv,
                    "label": f"IR {lv:.0e}/yr",
                    "grade": grade,
                    "coverage_complete": complete,
                    "coverage_note": note,
                    "not_claimable_as": (
                        result.claim_boundary()["not_claimable_as"]
                        + ([] if complete else ["an upper bound on the risk"])),
                },
            })
    return {
        "type": "FeatureCollection",
        "features": feats,
        "properties": {
            "generator": "PRISM LH2 screening QRA",
            "grade": grade,
            "grade_by_route": result.grade_by_route,
            "claim_boundary": result.claim_boundary(),
            "max_individual_risk_per_year": result.max_ir,
            "coverage": note,
            "crs_note": ("coordinates are metres in the site's own frame"
                         if origin_lon is None
                         else "WGS84, flat-earth about the site origin"),
        },
    }


# --------------------------------------------------------------------------
# FN curve
# --------------------------------------------------------------------------

def risk_integral(result) -> float:
    """IR integrated over the ground, /yr x m2.

    Summing grid cells without the area gives a number that scales with
    resolution and is not comparable between runs. This one converges:
    on the reference site it holds at 0.66 from 200 m cells down to
    6.25 m while the bare sum changes by three orders."""
    import numpy as np
    g = np.asarray(result.grid.values)
    return float(g.sum()) * result.grid.cell_size_m ** 2


def fn_table(result) -> list[dict]:
    """FN points with the Dutch limit line alongside each."""
    from risk import dutch_sr_limit
    n, f = result.fn()
    rows = []
    for ni, fi in zip(np.asarray(n), np.asarray(f)):
        lim = float(dutch_sr_limit(np.array([ni]))[0])
        rows.append({
            "n_fatalities": float(ni),
            "frequency_per_year": float(fi),
            "dutch_limit_per_year": lim,
            "exceeds_limit": bool(ni >= 10 and fi > lim),
        })
    return rows


# --------------------------------------------------------------------------
# bundle
# --------------------------------------------------------------------------

def export(result, interval=None, report=None, model_form=None,
           origin_lon: Optional[float] = None,
           origin_lat: Optional[float] = None) -> dict:
    """Everything a reader needs, with the caveats attached rather than
    delivered separately and lost."""
    from uncertainty import NOT_PROPAGATED
    out: dict[str, Any] = {
        "claim_boundary": result.claim_boundary(),
        "summary": {
            "max_individual_risk_per_year": result.max_ir,
            "grade": result.grade.value,
            "grade_by_route": result.grade_by_route,
            "scenarios_enumerated": result.n_scenarios,
            "scenarios_evaluated": result.n_computed,
            "scenarios_skipped": result.n_skipped,
            "coverage_fraction": result.coverage.evaluated_fraction,
            "coverage_statement": result.coverage.statement(),
            "risk_integral_per_year_m2": risk_integral(result),
            "flame_model": result.flame_model.value,
        },
        "ir_contours_geojson": ir_geojson(result, origin_lon, origin_lat),
        "fn_curve": fn_table(result),
        "notes": list(result.notes),
    }
    if interval is not None:
        out["uncertainty"] = {
            "median_per_year": interval.median,
            "p05_per_year": interval.p05,
            "p95_per_year": interval.p95,
            "span": interval.span,
            "supported_significant_figures":
                interval.significant_figures(),
            "reported_as": interval.rounded(),
            "covers": "leak frequency only; a lower bound on the spread",
            "not_propagated": NOT_PROPAGATED,
        }
    if model_form is not None:
        out["model_form_uncertainty"] = {
            "type": "non-probabilistic envelope",
            "models": sorted(model_form.max_ir_by_model),
            "max_ir_per_year_by_model": model_form.max_ir_by_model,
            "max_ir_low_per_year": model_form.max_ir_low,
            "max_ir_high_per_year": model_form.max_ir_high,
            "max_ir_span": model_form.max_ir_span,
            "risk_integral_per_year_m2_by_model":
                model_form.integrated_ir_by_model,
            "risk_integral_low_per_year_m2": model_form.integrated_low,
            "risk_integral_high_per_year_m2": model_form.integrated_high,
            "risk_integral_span": model_form.integrated_span,
            "note": (
                "Molkov conservative, Molkov best fit, and Delichatsios "
                "are alternative model forms. No probability distribution "
                "is assigned and this envelope is not combined with the "
                "leak-frequency percentile interval."),
        }
    if getattr(result, "ignition_checks", None):
        import hiad as H
        out["ignition_against_recorded_incidents"] = {
            "note": H.WHY_NOT_A_CORRECTION,
            "source": H.HIAD_PROV.source,
            "not_claimable_as": H.HIAD_PROV.not_claimable_as,
            "checks": [
                {"scheme": c.scheme, "medium": c.medium,
                 "scheme_probability": c.scheme_probability,
                 "recorded_low": c.recorded_low,
                 "recorded_high": c.recorded_high,
                 "within_recorded_range": c.within_recorded_range,
                 "ratio_to_midpoint": c.ratio_to_midpoint}
                for c in result.ignition_checks],
        }
    if getattr(result, "transient_audit", None):
        from dataclasses import asdict
        out["transient_coupling"] = {
            "note": (
                "Supplied time-dependent profiles replace the ordinary "
                "blocking branches for their exact scenario IDs. The "
                "downstream consequence models are steady, so each audit "
                "row records the selected single-rate reduction and nearest "
                "profile state; this is not a time-resolved consequence "
                "calculation."),
            "cases": [asdict(a) for a in result.transient_audit],
        }
    if report is not None:
        out["decision"] = {
            "scope": "numerical criterion comparison only; facility acceptance is withheld",
            "individual": report.individual.statement(),
            "verdict": report.individual.verdict.value,
            "societal": (report.societal.statement()
                         if report.societal else None),
            "top_scenarios": [
                {"rank": i.rank, "key": i.key,
                 "fussell_vesely": i.fussell_vesely, "rrw": i.rrw}
                for i in report.top_scenarios[:10]],
            "top_outcomes": [
                {"rank": i.rank, "key": i.key,
                 "fussell_vesely": i.fussell_vesely}
                for i in report.top_outcomes],
        }
    return out


def write(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, allow_nan=False)
