"""
Distributed point source on a back-to-back weighted ellipsoid (DPE).

Hankinson & Lowesmith (2012) compare six ways of turning a fraction of
heat radiated into an incident flux and conclude that this one is the
best: it behaves well in the near field and the far field alike, and
alone among them it needs NO adjustment to the fraction of heat radiated.
The solid flame shapes all run about 1.2 times the weighted multi-point
result in the far field, so a radiant fraction derived for one is not
valid in the other; the cylinder and the cone additionally produce kinks
in the contours as different faces come into view, which means the
predicted radiation field is not smooth.

Why bother, given the weighted multi-point model already works
------------------------------------------------------------------
Two reasons, both of which bite for hydrogen.

The multi-point model puts its sources on the flame AXIS. Close in that
is wrong in a specific way: a receptor beside the flame sees sources that
are all at the same lateral offset, when the real flame presents a
surface wrapped around it. For hydrogen the 35 kW/m2 contour sits within
a flame radius or two of the envelope, which is exactly where that
matters.

And the paper's own reason: the radiant power emitted by an element of a
real flame surface is uniform over the hemisphere above it, not varying
as the cosine of the angle to the element normal. A view factor model
imposes the cosine; distributed hemispherical sources do not. That is
the difference the paper attributes the DPE model's behaviour to.

Geometry
--------
The back-to-back weighted ellipsoid is two half-ellipsoids sharing a
common equatorial disc, the join sitting at 0.75 of the flame length
where the emission peaks, with a maximum width of 0.17 L. Sources are
placed over that surface in proportion to the area each represents, and
a source contributes only if it can see the receptor and be seen by it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

import fire as F

JOIN_FRACTION = F.PEAK_FRACTION          # 0.75 L, where the emission peaks
WIDTH_RATIO = F.FLAME_WIDTH_RATIO        # 0.17 L, maximum width


@dataclass(frozen=True)
class Surface:
    """Point sources over the flame surface: position, outward normal,
    and the fraction of the total area each represents."""
    points: np.ndarray        # (n, 3)
    normals: np.ndarray       # (n, 3), unit
    weights: np.ndarray       # (n,), summing to 1


def ellipsoid_surface(flame_length_m: float, n_axial: int = 24,
                      n_around: int = 16,
                      orientation: str = "HORIZONTAL",
                      bearing_deg: float = 0.0,
                      origin_height_m: float = 1.0) -> Surface:
    """Back-to-back weighted ellipsoid, discretised by area.

    The axis runs from the orifice to the flame tip. Semi-axes:
    a1 = 0.75 L up to the join, a2 = 0.25 L beyond it, and b = 0.085 L
    across. Ring areas are taken from the local radius and the arc length
    along the profile, so the weights are true area fractions rather than
    equal steps in the axial coordinate.
    """
    L = max(flame_length_m, 1e-9)
    b = float(WIDTH_RATIO) * L / 2.0
    s_join = float(JOIN_FRACTION) * L
    a1, a2 = s_join, L - s_join

    pts, nrm, wts = [], [], []
    # parametrise each half separately so the join lands on a ring
    for a, s0, sign in ((a1, s_join, -1.0), (a2, s_join, +1.0)):
        n_half = max(2, int(round(n_axial * a / L)))
        for i in range(n_half):
            u = (i + 0.5) / n_half                     # 0 at join, 1 at end
            s = s0 + sign * a * u
            r = b * math.sqrt(max(1.0 - u * u, 0.0))   # local radius
            if r <= 1e-9:
                continue
            # profile slope for the surface normal and the arc length
            drds = (-b * u / (a * math.sqrt(max(1.0 - u * u, 1e-12)))) * sign
            ds = a / n_half
            ring_area = 2.0 * math.pi * r * ds * math.sqrt(1.0 + drds ** 2)
            for j in range(n_around):
                phi = 2.0 * math.pi * (j + 0.5) / n_around
                # local frame: axis along +x (horizontal) or +z (vertical)
                ny, nz = math.cos(phi), math.sin(phi)
                if orientation == "VERTICAL":
                    p = (r * ny, r * nz, s + origin_height_m)
                    n = (ny, nz, -drds)
                else:
                    th = math.radians(bearing_deg)
                    ax, ay = math.cos(th), math.sin(th)
                    # radial direction perpendicular to the axis
                    p = (s * ax - r * ny * ay, s * ay + r * ny * ax,
                         origin_height_m + r * nz)
                    n = (-drds * ax - ny * ay, -drds * ay + ny * ax, nz)
                mag = math.sqrt(sum(c * c for c in n)) or 1.0
                pts.append(p)
                nrm.append(tuple(c / mag for c in n))
                wts.append(ring_area / n_around)

    w = np.asarray(wts, dtype=float)
    total = w.sum() or 1.0
    return Surface(points=np.asarray(pts, dtype=float),
                   normals=np.asarray(nrm, dtype=float),
                   weights=w / total)


def dpe_heat_flux(flame: "F.Flame", distance_m: float,
                  receptor_height_m: float = 1.0,
                  bearing_deg: float = 0.0,
                  orientation: str = "HORIZONTAL",
                  relative_humidity: float = 0.5,
                  n_axial: int = 24, n_around: int = 16,
                  surface: Optional[Surface] = None) -> float:
    """Incident flux [W/m2] from distributed hemispherical point sources.

    A source contributes only if the receptor lies in the hemisphere above
    it -- the paper's "can see and be seen by". A receptor inside the
    envelope has no source above it in any consistent sense and is
    reported as ENGULFED rather than given a number.
    """
    if surface is None:
        surface = ellipsoid_surface(flame.length_m, n_axial, n_around,
                                    orientation, bearing_deg,
                                    receptor_height_m)
    rx = np.array([distance_m, 0.0, receptor_height_m])
    d = rx[None, :] - surface.points
    r = np.linalg.norm(d, axis=1)
    if (r < 1e-6).any():
        return F.ENGULFED

    # visible only where the receptor is on the outward side
    cos_out = np.einsum("ij,ij->i", d / r[:, None], surface.normals)
    visible = cos_out > 0.0
    if not visible.any():
        return F.ENGULFED

    tau = np.array([F.transmissivity(float(x), relative_humidity)
                    for x in r])
    # hemispherical emission: uniform over the hemisphere above the
    # element, so no cosine on the source side
    q = (surface.weights * flame.radiant_power_w * tau
         / (2.0 * math.pi * r ** 2))
    return float(q[visible].sum())


def dpe_distance_to_flux(flame: "F.Flame", target_w_m2: float,
                         receptor_height_m: float = 1.0,
                         bearing_deg: float = 0.0,
                         orientation: str = "HORIZONTAL",
                         relative_humidity: float = 0.5,
                         x_max: float = 1000.0) -> Optional[float]:
    surface = ellipsoid_surface(flame.length_m, 24, 16, orientation,
                                bearing_deg, receptor_height_m)

    def q(x: float) -> float:
        return dpe_heat_flux(flame, x, receptor_height_m, bearing_deg,
                             orientation, relative_humidity,
                             surface=surface)

    # Step outward until a source can see the receptor. Along the axis
    # that means clearing the flame tip, so the multiplicative walk used
    # elsewhere is too coarse: it can jump past the answer. For hydrogen
    # the 35 kW/m2 contour sits within a metre or two of the tip.
    r_flame = float(F.FLAME_RADIUS_RATIO) * flame.length_m
    lo = r_flame + 0.05
    step = max(r_flame * 0.05, 0.05)
    while lo < x_max and q(lo) == F.ENGULFED:
        lo += step
    if lo >= x_max:
        return None
    if q(lo) < target_w_m2 or q(x_max) > target_w_m2:
        return None
    hi = x_max
    for _ in range(70):
        mid = 0.5 * (lo + hi)
        if q(mid) > target_w_m2:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


SOLID_FLAME_ADJUSTMENT = 1.0 / 1.2
SOLID_FLAME_NOTE = (
    "Hankinson & Lowesmith found the four solid flame shapes running about "
    "1.2 times the weighted multi-point result in the far field, so a "
    "fraction of heat radiated derived with one is not valid in the other "
    "without dividing by that. The DPE model needs no such adjustment, "
    "which is the main reason to prefer it."
)
