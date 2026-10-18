"""
Vectorised radiant flux over a grid.

Profiling put 42% of pipeline time in transmissivity and 83% in the
radiation stack, called 1.8 million times for a 13x13 grid. The cause is
the loop nesting: grid cell, then bearing, then flame point, with a
transcendental at the bottom. None of it depends on the loop order, so the
whole thing collapses into array arithmetic of shape
(cells, bearings, points).

The physics is identical to fire.heat_flux; equality with the scalar
version is asserted in the test rather than assumed. Where they differ,
the scalar version is the reference, because it is the one written from
the papers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

import fire as F

P_AMB = F.P_AMB


def _transmissivity(path_m: np.ndarray, relative_humidity: float,
                    temperature_k: float, co2_ppm: float = 400.0
                    ) -> np.ndarray:
    """Vectorised Wayne (1991), kept in step with fire.transmissivity.

    This was duplicated once and drifted: the scalar version was corrected
    against the source (wrong leading coefficient by ten, missing CO2 term,
    flipped sign) and this copy was not, which left the vectorised field
    25% high while the equality test that would have caught it had already
    been run and retired. Two implementations of one equation is the
    defect; the numbers below are derived from the same constants the
    scalar version uses, and the golden test asserts they agree.
    """
    t = temperature_k
    s_mm = math.exp(10.386 - 5132.0 / t)
    x_h2o = np.maximum(relative_humidity * path_m * s_mm * 288.651 / t, 1e-12)
    x_co2 = np.maximum(path_m * (273.0 / t) * (co2_ppm / 335.0), 1e-12)
    lw, lc = np.log10(x_h2o), np.log10(x_co2)
    tau = (1.006 - 0.001171 * lw - 0.02368 * lw ** 2
           - 0.03188 * lc + 0.001164 * lc ** 2)
    return np.clip(tau, 0.0, 1.0)


@dataclass(frozen=True)
class DirectionalFlux:
    """Flux with bearing on the last axis; +inf denotes flame contact."""
    by_bearing: np.ndarray


def directional_flux_field(flame: F.Flame, dx: np.ndarray, dy: np.ndarray,
               height_m: float = 1.0, n_points: int = 15,
               n_bearings: int = 12, relative_humidity: float = 0.5,
               temperature_k: float = F.T_AMB,
               orientation: str = "HORIZONTAL",
               source_height_m: float = 0.0,
               azimuth_deg: float | None = None) -> DirectionalFlux:
    """Preserve each bearing until AFTER nonlinear damage is evaluated."""
    if np.shape(dx) != np.shape(dy):
        raise ValueError("receptor offset arrays must have the same shape")
    if n_points <= 0 or n_bearings <= 0:
        raise ValueError("point and bearing counts must be positive")
    if azimuth_deg is not None and not math.isfinite(azimuth_deg):
        raise ValueError("release azimuth must be finite")
    shape = np.shape(dx)
    rx = np.asarray(dx, dtype=float).ravel()[:, None, None]
    ry = np.asarray(dy, dtype=float).ravel()[:, None, None]

    w = np.asarray(F.weights_hankinson(n_points))[None, None, :]
    s = flame.length_m * (np.arange(n_points) + 0.5)[None, None, :] / n_points

    if orientation in ("VERTICAL", "UP"):
        px = np.zeros_like(s)
        py = np.zeros_like(s)
        pz = source_height_m + s
    elif orientation == "DOWN":
        px = np.zeros_like(s)
        py = np.zeros_like(s)
        pz = source_height_m - s
    else:
        bearings = (np.asarray([azimuth_deg]) if azimuth_deg is not None
                    else 360.0 * np.arange(n_bearings) / n_bearings)
        b = np.radians(bearings)[None, :, None]
        px = s * np.cos(b)
        py = s * np.sin(b)
        pz = np.full_like(px, source_height_m)

    r = np.sqrt((rx - px) ** 2 + (ry - py) ** 2 + (height_m - pz) ** 2)
    r_flame = float(F.FLAME_RADIUS_RATIO) * flame.length_m

    engulfed_bearing = (r < r_flame).any(axis=2)              # (cells, bearings)
    tau = _transmissivity(np.maximum(r, 1e-3), relative_humidity,
                          temperature_k)
    q = (w * flame.radiant_power_w * tau
         / (4.0 * math.pi * np.maximum(r, 1e-3) ** 2)).sum(axis=2)

    q = np.where(engulfed_bearing, np.inf, q)
    return DirectionalFlux(q.reshape(shape + (q.shape[-1],)))


def flux_field(flame: F.Flame, dx: np.ndarray, dy: np.ndarray,
               height_m: float = 1.0, n_points: int = 15,
               n_bearings: int = 12, relative_humidity: float = 0.5,
               temperature_k: float = F.T_AMB,
               orientation: str = "HORIZONTAL", source_height_m: float = 0.0
               ) -> tuple[np.ndarray, np.ndarray]:
    """Legacy descriptive mean ONLY; do not feed it to nonlinear damage."""
    q = directional_flux_field(
        flame, dx, dy, height_m, n_points, n_bearings, relative_humidity,
        temperature_k, orientation, source_height_m).by_bearing
    engulfed = np.isposinf(q)
    frac = engulfed.mean(axis=-1)
    mean = (np.where(engulfed, 0.0, q).sum(axis=-1)
            / np.maximum((~engulfed).sum(axis=-1), 1))
    return np.where(frac >= 1.0, np.inf, mean), frac


def coverage_field(dx: np.ndarray, dy: np.ndarray, cell_size: float,
                   radius: float, n_sub: int = 7) -> np.ndarray:
    """Fraction of each cell inside a circle of the given radius, by
    subsampling. Vectorised form of damage.cell_coverage_fraction."""
    shape = np.shape(dx)
    off = (np.arange(n_sub) + 0.5) / n_sub - 0.5
    ox, oy = np.meshgrid(off * cell_size, off * cell_size, indexing="ij")
    o = np.stack([ox.ravel(), oy.ravel()], axis=0)[:, None, :]
    p = np.stack([np.asarray(dx, float).ravel(),
                  np.asarray(dy, float).ravel()], axis=0)[:, :, None]
    d = np.hypot(*(p + o))
    return (d <= radius).mean(axis=1).reshape(shape)


def _inside_directional_footprint(
        x: np.ndarray, y: np.ndarray, axial_m: np.ndarray,
        radius_m: np.ndarray, azimuth_deg: float) -> np.ndarray:
    """Point membership in an axially tabulated, symmetric jet contour."""
    angle = math.radians(azimuth_deg)
    along = x * math.cos(angle) + y * math.sin(angle)
    cross = -x * math.sin(angle) + y * math.cos(angle)
    allowed = np.interp(along.ravel(), axial_m, radius_m,
                        left=-1.0, right=-1.0).reshape(along.shape)
    return np.abs(cross) <= allowed


def directional_footprint_field(
        dx: np.ndarray, dy: np.ndarray, cell_size: float,
        axial_m, radius_m, azimuth_deg: float | None = None,
        n_bearings: int = 12, n_sub: int = 7) -> np.ndarray:
    """Cell fraction inside a Schefer-style directional jet footprint.

    Azimuth is counter-clockwise from the +x site axis. If the release
    bearing is unknown, the result is averaged uniformly over bearings;
    this is the plan-view analogue of the horizontal jet-fire treatment.
    """
    axial = np.asarray(axial_m, dtype=float)
    radii = np.asarray(radius_m, dtype=float)
    if (axial.ndim != 1 or radii.ndim != 1 or axial.size < 2
            or axial.shape != radii.shape
            or np.any(np.diff(axial) <= 0.0)
            or np.any(radii < 0.0)):
        raise ValueError("axial and radius profiles must be equal monotone arrays")
    if n_sub <= 0 or n_bearings <= 0:
        raise ValueError("subsamples and bearings must be positive")

    shape = np.shape(dx)
    off = (np.arange(n_sub) + 0.5) / n_sub - 0.5
    ox, oy = np.meshgrid(off * cell_size, off * cell_size, indexing="ij")
    x = np.asarray(dx, float).ravel()[:, None] + ox.ravel()[None, :]
    y = np.asarray(dy, float).ravel()[:, None] + oy.ravel()[None, :]
    if azimuth_deg is not None:
        inside = _inside_directional_footprint(
            x, y, axial, radii, float(azimuth_deg))
        return inside.mean(axis=1).reshape(shape)

    covered = np.zeros(x.shape, dtype=float)
    for bearing in np.linspace(0.0, 360.0, n_bearings, endpoint=False):
        covered += _inside_directional_footprint(
            x, y, axial, radii, float(bearing))
    return (covered / n_bearings).mean(axis=1).reshape(shape)


def point_in_directional_footprint(
        dx: float, dy: float, axial_m, radius_m,
        azimuth_deg: float | None) -> bool:
    """Equipment-screening membership for a directional jet contour.

    An unknown bearing is treated as a conservative envelope because the
    equipment escalation graph stores a boolean, not an orientation
    probability. Individual-risk fields use bearing averaging instead.
    """
    axial = np.asarray(axial_m, dtype=float)
    radii = np.asarray(radius_m, dtype=float)
    if azimuth_deg is None:
        return math.hypot(dx, dy) <= float(axial[-1])
    inside = _inside_directional_footprint(
        np.asarray([dx]), np.asarray([dy]), axial, radii,
        float(azimuth_deg))
    return bool(inside[0])
