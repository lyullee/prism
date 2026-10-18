"""
Uncertainty propagation.

The pipeline reports a risk to three significant figures from a frequency
library whose LH2 storage vessel spans a factor of 29,000 between its 5th
and 95th percentile. Those digits are not wrong so much as unearned, and a
number that looks precise gets treated as precise.

What is propagated
------------------
Only the leak frequencies, and only where the source publishes a
distribution: the updated filter row from SAND2024-06491 Table 4-1 and all
six liquid hydrogen components from Brooks, Ehrhart & LaFleur (2021)
Table 2. Everything else is held at its point value.

That is a deliberate floor, not a complete uncertainty analysis. The
ignition scheme alone moves the answer by a factor of 52 and is not a
distribution at all but a choice between two incompatible bodies of data,
so it cannot be sampled. Nor can the dispersion premise or the Planck
absorption coefficient. The interval this module produces is therefore a
LOWER BOUND on the spread, and is labelled as one.

Sampling
--------
Each component's frequency is lognormal on ln(frequency) with the mu and
sigma stored alongside its medians. Bins within a component are sampled
with a shared draw rather than independently: the underlying Bayesian model
is a regression across leak size, so a component that leaks more often than
expected does so at every size. Sampling bins independently would let the
100% bin exceed the 0.01% bin and would understate the spread by averaging
away the correlation that actually exists.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

import taxonomy as T


@dataclass(frozen=True)
class Interval:
    """A sampled quantity. Reported as a range, never as a mean."""
    median: float
    p05: float
    p95: float
    samples: int
    span: float = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "span",
                           self.p95 / self.p05 if self.p05 > 0 else math.inf)

    def statement(self, unit: str = "/yr") -> str:
        return (f"{self.median:.2g}{unit} "
                f"[{self.p05:.2g}, {self.p95:.2g}] "
                f"(x{self.span:,.0f} span, {self.samples} samples)")

    def significant_figures(self) -> int:
        """How many digits of the median are actually supported.

        If the interval spans more than a factor of three, the leading
        digit is the only one carrying information; beyond a factor of
        thirty, not even that."""
        if self.span >= 30.0:
            return 0
        if self.span >= 3.0:
            return 1
        return 2

    def rounded(self) -> str:
        n = self.significant_figures()
        if self.median == 0.0:
            return "0"
        if n == 0:
            return f"order 1e{math.floor(math.log10(self.median)):.0f}"
        return f"{self.median:.{n}g}"


@dataclass(frozen=True)
class ModelFormEnvelope:
    """Non-probabilistic bounds across named jet-flame correlations.

    These alternatives are model choices, not random samples. The object
    therefore reports an envelope and never percentiles or a mean.
    """
    max_ir_by_model: dict[str, float]
    integrated_ir_by_model: dict[str, float]

    @property
    def max_ir_low(self) -> float:
        return min(self.max_ir_by_model.values())

    @property
    def max_ir_high(self) -> float:
        return max(self.max_ir_by_model.values())

    @property
    def max_ir_span(self) -> float:
        return (self.max_ir_high / self.max_ir_low
                if self.max_ir_low > 0.0 else math.inf)

    @property
    def integrated_low(self) -> float:
        return min(self.integrated_ir_by_model.values())

    @property
    def integrated_high(self) -> float:
        return max(self.integrated_ir_by_model.values())

    @property
    def integrated_span(self) -> float:
        return (self.integrated_high / self.integrated_low
                if self.integrated_low > 0.0 else math.inf)

    def statement(self) -> str:
        return (f"jet-flame model envelope: max IR "
                f"[{self.max_ir_low:.3g}, {self.max_ir_high:.3g}]/yr "
                f"(x{self.max_ir_span:.3g}); no probabilities assigned")


def flame_model_envelope(results: dict[str, object]) -> ModelFormEnvelope:
    """Reduce pipeline results from alternative flame models to bounds."""
    if len(results) < 2:
        raise ValueError("a model-form envelope needs at least two models")
    max_ir: dict[str, float] = {}
    integrated: dict[str, float] = {}
    for name, result in results.items():
        value = float(result.max_ir)
        area_value = (float(np.asarray(result.grid.values).sum())
                      * float(result.grid.cell_size_m) ** 2)
        if not math.isfinite(value) or not math.isfinite(area_value):
            raise ValueError(f"non-finite result for flame model {name}")
        max_ir[str(name)] = value
        integrated[str(name)] = area_value
    return ModelFormEnvelope(max_ir, integrated)


def _has_distribution(entry: T.FrequencyEntry) -> bool:
    return entry.mu is not None and entry.sigma is not None


def sample_library(rng: random.Random) -> dict:
    """One draw of the whole frequency library.

    Returns {(primitive, fuel): [freq per bin]}. Components without a
    published distribution are returned at their point value, which
    quietly narrows the result -- see the module docstring."""
    out = {}
    for key, e in T.FREQUENCY_LIBRARY.items():
        if not _has_distribution(e):
            out[key] = list(e.medians)
            continue
        # one standard normal per component, shared across its bins
        z = rng.gauss(0.0, 1.0)
        out[key] = [math.exp(mu + z * sig) * e.conservatism_factor
                    for mu, sig in zip(e.mu, e.sigma)]
    return out


def coverage() -> dict:
    """Which parts of the library carry a distribution at all."""
    total = len(T.FREQUENCY_LIBRARY)
    withd = sum(1 for e in T.FREQUENCY_LIBRARY.values() if _has_distribution(e))
    return {"entries": total, "with_distribution": withd,
            "point_only": total - withd,
            "fraction": withd / total if total else 0.0}


def propagate(run_once: Callable[[dict], float], n: int = 200,
              seed: int = 0) -> Interval:
    """Run the pipeline n times against sampled frequencies.

    run_once receives the sampled library and returns one scalar risk."""
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        v = run_once(sample_library(rng))
        if math.isfinite(v) and v > 0:
            vals.append(v)
    if not vals:
        return Interval(0.0, 0.0, 0.0, 0)
    a = np.array(sorted(vals))
    return Interval(median=float(np.median(a)),
                    p05=float(np.percentile(a, 5)),
                    p95=float(np.percentile(a, 95)),
                    samples=len(a))


# --------------------------------------------------------------------------
# a cheaper route: the risk is linear in frequency
# --------------------------------------------------------------------------

def propagate_linear(contributions, n: int = 5000, seed: int = 0,
                     *, receptor_id: tuple[int, int] | None = None,
                     single_point: bool = False) -> Interval:
    """Sample the spatial maximum, or one explicitly selected receptor.

    Individual Risk is a sum of terms each linear in one component's leak
    frequency (equation 6.1: fS x PM x Pphi x Pi x Pd, where only fS is
    uncertain). So the frequencies can be resampled and the terms rescaled
    without recomputing any physics. This holds only while the physics is
    independent of frequency, which it is here -- consequence depends on
    hole size and weather, not on how often the hole appears.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError("sample count must be a positive integer")
    contributions = list(contributions)
    if not contributions:
        return Interval(0.0, 0.0, 0.0, 0)
    receptors = {c.receptor_id for c in contributions}
    if None in receptors and (not single_point or len(receptors) != 1):
        raise ValueError("spatial IR uncertainty requires a receptor_id on every contribution")
    if single_point and (len(receptors) != 1 or receptor_id is not None):
        raise ValueError("single_point requires exactly one receptor and no selector")
    if receptor_id is not None and receptor_id not in receptors:
        raise ValueError("selected receptor is absent from the contributions")
    selected = [receptor_id] if receptor_id is not None else list(receptors)
    receptor_index = {r: i for i, r in enumerate(selected)}
    groups: dict[tuple, np.ndarray] = {}
    for c in contributions:
        if c.receptor_id not in receptor_index:
            continue
        if not math.isfinite(c.delta_ir) or c.delta_ir < 0.0:
            raise ValueError("IR contributions must be finite and non-negative")
        values = groups.setdefault(c.source_key, np.zeros(len(selected)))
        values[receptor_index[c.receptor_id]] += c.delta_ir

    rng = random.Random(seed)
    totals = []
    for _ in range(n):
        lib = sample_library(rng)
        t = np.zeros(len(selected))
        for key, s in groups.items():
            if key is None or key[0] not in lib:
                t += s
                continue
            prim_fuel, bin_index = key
            e = T.FREQUENCY_LIBRARY.get(prim_fuel)
            if e is None or not _has_distribution(e):
                t += s
                continue
            scale = lib[prim_fuel][bin_index] / max(e.medians[bin_index], 1e-30)
            t += s * scale
        # The maximum can move when frequency families change. Do not
        # rescale only the baseline maximizer or sum different receptors.
        totals.append(float(t.max()))
    a = np.array(sorted(totals))
    return Interval(median=float(np.median(a)),
                    p05=float(np.percentile(a, 5)),
                    p95=float(np.percentile(a, 95)),
                    samples=len(a))


NOT_PROPAGATED = [
    "ignition scheme: PURPLE_SOURCES against HYRAM is about a factor of "
    "two on a quiet site, not the fifty that PURPLE against HYRAM gave. "
    "Most of that gap was a misreading of Purple Book 4.7.2, not a "
    "disagreement about hydrogen. What remains is a choice between "
    "bodies of data and cannot be sampled",
    "Molina radiant fraction residual: factor 22.7, unexplained",
    "jet-flame model choice is not sampled as a probability; Molkov "
    "conservative, Molkov best fit, and Delichatsios can instead be "
    "exported as a separate model-form envelope",
    "LH2 fireball size beyond 6.3 kg: extrapolated three orders past the "
    "data it was fitted to",
    "pump seal frequency: no source, and the direction of its bias is "
    "known while its size is not",
    "blast wave decay: refused outright, the curves are figures",
    "dispersion premise refusals: excluded scenarios, not uncertain ones",
]
