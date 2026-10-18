"""
Risk integration, following the Purple Book (CPR 18E) chapter 6.

What this module is
-------------------
The bookkeeping layer: it turns (LOC frequency, weather, wind direction,
ignition event, probability of death) into Individual Risk contours and an
FN curve. Dispersion, fire and explosion models are inputs, not part of it.

    IR(grid point) = sum over  LOC x weather x wind direction x ignition
                     of  fS * PM * Pphi * Pi * Pd                    (6.1, 6.2)

Two routes to Pd exist and they are not interchangeable:

  toxic      (6.2.5)  Pd = Pcl * Pci, where Pci scales the on-axis
                      lethality by how much of the wind sector the
                      effective cloud actually covers.
  flammable  (6.2.6)  the impact area is assumed to span several wind
                      sectors, so no Pci correction is applied. For a flash
                      fire the book recommends grading Pd by the fraction
                      of the grid cell inside the flame envelope rather
                      than letting it jump between 0 and 1.

Hydrogen is flammable, so the flammable route is the one this project will
use. The toxic route is implemented because Appendix 6.B -- the only fully
worked example in the book -- is a toxic case, and it is the available
check on the summation, the effective cloud width and the wind sector
geometry. Passing 6.B validates the bookkeeping, NOT the hydrogen Pd path.

Overpressure note: Purple Book 5.2.4 states its 0.3 / 0.1 bar zone
probabilities do not apply to detonation, because the blast duration
differs. Hydrogen DDT is a credible scenario, so the overpressure route
here is marked as out of its own validity range rather than silently used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Optional

import numpy as np


SQRT2 = math.sqrt(2.0)


# --------------------------------------------------------------------------
# probit
# --------------------------------------------------------------------------

def probit_to_probability(pr: float) -> float:
    """Purple Book Table 5.1: P = Phi(Pr - 5). Below Pr = 2.67 the book
    truncates at 1% lethality; that truncation is applied by the caller."""
    return 0.5 * (1.0 + math.erf((pr - 5.0) / SQRT2))


def probability_to_probit(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be strictly between 0 and 1")
    lo, hi = -10.0, 20.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if probit_to_probability(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


PR_1PCT = probability_to_probit(0.01)   # ~2.674; the book's cut-off


@dataclass(frozen=True)
class ToxicProbit:
    """Pr = a + b*ln(C^n * t). Units are those of the constants: the Purple
    Book tabulates CO with C in mg/m3 and t in minutes."""
    a: float
    b: float
    n: float
    substance: str = ""

    def probit(self, concentration: float, exposure: float) -> float:
        return self.a + self.b * math.log(concentration ** self.n * exposure)


CO_PROBIT = ToxicProbit(a=-7.4, b=1.0, n=1.0, substance="carbon monoxide")


@dataclass(frozen=True)
class ThermalProbit:
    """Green Book / Purple Book 5.2.3: Pr = -36.38 + 2.56 ln(Q^(4/3) t),
    Q in W/m2, t in s. Substance independent -- it is a skin dose relation,
    so it carries over to hydrogen unchanged."""
    a: float = -36.38
    b: float = 2.56

    def probit(self, heat_flux_w_m2: float, exposure_s: float) -> float:
        return self.a + self.b * math.log(heat_flux_w_m2 ** (4.0 / 3.0)
                                          * exposure_s)


# --------------------------------------------------------------------------
# effective cloud width and sector coverage  (toxic route, 6.2.5 / 6.A)
# --------------------------------------------------------------------------

def probability_integral(p_of_y: Callable[[float], float],
                         y_max: float, n: int = 2001) -> float:
    """PI(R) = integral of the off-axis death probability across the wind,
    in metres. The book truncates the limits at 1% lethality."""
    ys = np.linspace(-y_max, y_max, n)
    return float(np.trapezoid([p_of_y(float(y)) for y in ys], ys))


def gaussian_lateral_pi(pr_centreline: float, sigma_y: float) -> float:
    """PI for a Gaussian crosswind profile. Off axis the concentration falls
    as exp(-y^2 / 2 sigma_y^2), so for a probit linear in ln C the probit
    falls by exactly y^2 / (2 sigma_y^2) times b*n."""
    if pr_centreline <= PR_1PCT:
        return 0.0
    u_max = math.sqrt(2.0 * (pr_centreline - PR_1PCT))
    return sigma_y * probability_integral(
        lambda u: probit_to_probability(pr_centreline - 0.5 * u * u),
        u_max)


def effective_cloud_width(pi_metres: float, p_centreline: float) -> float:
    """ECW = PI / Pcl -- the width of an equivalent top-hat cloud that
    would kill with the centreline probability."""
    if p_centreline <= 0.0:
        return 0.0
    return pi_metres / p_centreline


def probability_covered(ecw: float, distance_m: float,
                        n_wind_sectors: int = 12) -> float:
    """Equation 6.10: Pci = ECW / (2 pi R / nws).

    Appendix 6.A shows this stays valid even when Pci would exceed 1,
    provided Pphi varies little between adjacent sectors, because the
    surplus is really the contribution of the neighbouring sectors. It is
    therefore NOT clipped here; clipping would drop real risk."""
    sector_arc = 2.0 * math.pi * distance_m / n_wind_sectors
    if sector_arc <= 0.0:
        return 0.0
    return ecw / sector_arc


# --------------------------------------------------------------------------
# weather
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class WeatherSector:
    """P(weather class M and wind sector phi), split day / night."""
    weather_class: str
    sector_deg: tuple[float, float]
    p_day: float
    p_night: float
    day_fraction: float = 0.44

    @property
    def pm_pphi(self) -> float:
        f = self.day_fraction
        return f * self.p_day + (1.0 - f) * self.p_night


# --------------------------------------------------------------------------
# individual risk
# --------------------------------------------------------------------------

class PdRoute(str, Enum):
    TOXIC = "TOXIC"
    FLAMMABLE = "FLAMMABLE"


@dataclass(frozen=True)
class RiskContribution:
    loc_id: str
    weather_class: str
    sector_deg: tuple[float, float]
    ignition_event: Optional[str]
    pm_pphi: float
    p_ignition: float
    p_death: float
    frequency_per_year: float
    route: PdRoute
    # which frequency-library entry produced this, so uncertainty can be
    # resampled without re-running the physics: ((primitive, fuel), bin index)
    source_key: Optional[tuple] = None
    # Grid contributions must retain their receptor. None is reserved for
    # explicitly single-point worked examples, never a whole-grid maximum.
    receptor_id: Optional[tuple[int, int]] = None

    @property
    def delta_ir(self) -> float:
        """Equation 6.1."""
        return (self.frequency_per_year * self.pm_pphi
                * self.p_ignition * self.p_death)


def total_individual_risk(contributions: Iterable[RiskContribution]) -> float:
    """Equation 6.2."""
    return float(sum(c.delta_ir for c in contributions))


@dataclass
class IRGrid:
    """Individual Risk accumulated on a regular grid.

    Cell size follows 6.2.1: 25 m where effect distances are at or below
    about 300 m, 100 m beyond that. Choosing a cell larger than the risk
    gradient smooths the contours and is a silent error, so the chosen
    size is recorded with the grid."""
    x: np.ndarray
    y: np.ndarray
    cell_size_m: float
    values: np.ndarray = field(init=False)

    def __post_init__(self):
        self.values = np.zeros((len(self.y), len(self.x)), dtype=float)

    @classmethod
    def square(cls, half_extent_m: float, cell_size_m: float) -> "IRGrid":
        if (not math.isfinite(half_extent_m) or half_extent_m <= 0.0
                or not math.isfinite(cell_size_m) or cell_size_m <= 0.0):
            raise ValueError("grid extent and cell size must be finite and positive")
        intervals = 2.0 * half_extent_m / cell_size_m
        rounded_intervals = round(intervals)
        if not math.isclose(intervals, rounded_intervals,
                            rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                "cell size must divide the full grid extent exactly")
        n = rounded_intervals + 1
        ax = np.linspace(-half_extent_m, half_extent_m, n)
        return cls(x=ax, y=ax.copy(), cell_size_m=cell_size_m)

    def add(self, ix: int, iy: int, delta_ir: float) -> None:
        self.values[iy, ix] += delta_ir

    def contour_levels(self) -> list[float]:
        """6.3 requires 1e-4 through 1e-8 to be shown where they exist."""
        return [1e-4, 1e-5, 1e-6, 1e-7, 1e-8]

    def max_ir(self) -> float:
        return float(self.values.max())


# --------------------------------------------------------------------------
# societal risk
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SocietalOutcome:
    """One (LOC, weather, wind direction, ignition) combination: its
    frequency and the expected number of deaths it produces."""
    frequency_per_year: float
    n_deaths: float


def fn_curve(outcomes: Iterable[SocietalOutcome]
             ) -> tuple[np.ndarray, np.ndarray]:
    """FN curve: for each N, the summed frequency of outcomes killing N or
    more. Returns (N, F) sorted ascending in N, with N >= 1 only, per 6.3."""
    frequencies: dict[float, float] = {}
    for outcome in outcomes:
        if outcome.n_deaths >= 1.0:
            frequencies[outcome.n_deaths] = (
                frequencies.get(outcome.n_deaths, 0.0)
                + outcome.frequency_per_year
            )
    if not frequencies:
        return np.array([]), np.array([])
    pts = sorted(frequencies.items())
    ns = np.array([point[0] for point in pts])
    fs = np.array([point[1] for point in pts])
    cumulative = np.cumsum(fs[::-1])[::-1]
    return ns, cumulative


def dutch_sr_limit(n: np.ndarray) -> np.ndarray:
    """Purple Book 6.3 recommended limit line for establishments:
    F < 1e-3 * N^-2 per year, for N >= 10."""
    return 1e-3 * np.asarray(n, dtype=float) ** -2.0


# --------------------------------------------------------------------------
# flammable route helpers  (6.2.6)
# --------------------------------------------------------------------------

def flash_fire_pd(cell_fraction_inside_envelope: float) -> float:
    """6.2.6 note 1. Inside a flash fire envelope lethality is taken as 1
    and outside as 0; the book recommends grading partially covered cells
    by area fraction so that IR and SR vary smoothly."""
    return min(max(cell_fraction_inside_envelope, 0.0), 1.0)


def fraction_of_deaths(f_indoor: float, f_outdoor: float,
                       pop_indoor: float, pop_outdoor: float) -> float:
    """Equation 6.13."""
    return f_indoor * pop_indoor + f_outdoor * pop_outdoor


OVERPRESSURE_VALIDITY = (
    "Purple Book 5.2.4 gives lethality by 0.3 / 0.1 bar zones for vapour "
    "cloud explosion only, and states it does not apply to detonation "
    "because the blast duration differs. Hydrogen DDT falls outside it. "
    "Use a pressure-impulse criterion instead, or record the result as "
    "out of validity range."
)
