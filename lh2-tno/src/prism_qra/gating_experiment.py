"""
What is refusing worth?

The claim that a gated model is better than an ungated one has been
asserted throughout this project and never measured. This measures it.

The experiment
--------------
Run the same site twice. In one run a scenario outside its model premise
is refused and excluded; in the other the same scenario is computed
anyway and the number used. Three quantities come out:

    coverage      how much frequency sits in refused scenarios. If it is
                  two percent, refusal is a nicety. If it is forty, it is
                  the whole argument.

    magnitude     how far the forced values are from the bound the gate
                  offers, where one is defined. The bound is the premise
                  edge, which is the last place the model was inside its
                  own assumptions.

    direction     whether forcing runs conservative or not. If forcing is
                  systematically conservative, refusing costs realism. If
                  it runs the other way, refusing is protecting the
                  answer, and that is a different argument.

What this cannot settle
-----------------------
Whether the forced values are RIGHT. There is no measurement outside the
premise to compare them against — that is what being outside the premise
means. What can be shown is how much they differ from the model's own
edge behaviour and from the gated result, and which way.

A caveat on the third quantity
------------------------------
"Conservative" here means larger, and larger is not always safer. A
longer flammable distance is conservative for a separation distance and
NOT conservative for an ignition probability, because a cloud that
reaches further has more chance of finding a source. The direction is
reported per quantity rather than as a single verdict.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Optional

from gating import RefusePolicy

warnings.filterwarnings("ignore")


@dataclass
class QuantityComparison:
    """One refused quantity, gated against forced."""
    quantity: str
    reason: str
    forced: Optional[float]
    bound: Optional[float]

    @property
    def ratio_to_bound(self) -> Optional[float]:
        if self.forced is None or not self.bound:
            return None
        return self.forced / self.bound

    @property
    def direction(self) -> str:
        r = self.ratio_to_bound
        if r is None:
            return "no bound to compare against"
        if r > 1.05:
            return "forced LARGER than the premise edge"
        if r < 0.95:
            return "forced SMALLER than the premise edge"
        return "forced close to the premise edge"


@dataclass
class Experiment:
    site_name: str
    ir_gated: float
    ir_forced: float
    integral_gated: float
    integral_forced: float
    refused_frequency: float
    total_frequency: float
    comparisons: list = field(default_factory=list)

    @property
    def refused_share(self) -> float:
        t = self.total_frequency
        return self.refused_frequency / t if t > 0 else 0.0

    @property
    def ir_ratio(self) -> float:
        return (self.ir_forced / self.ir_gated
                if self.ir_gated > 0 else math.inf)

    def lines(self) -> list[str]:
        out = [f"site: {self.site_name}",
               f"  frequency in refused scenarios   "
               f"{self.refused_share * 100:.2f}%",
               f"  max IR, gated                    {self.ir_gated:.4e}",
               f"  max IR, forced                   {self.ir_forced:.4e}",
               f"  ratio                            {self.ir_ratio:.4f}",
               f"  area integral, gated             {self.integral_gated:.4f}",
               f"  area integral, forced            {self.integral_forced:.4f}"]
        if self.comparisons:
            out.append("  refused quantities:")
            for c in self.comparisons:
                f = "none" if c.forced is None else f"{c.forced:.3g}"
                b = "none" if c.bound is None else f"{c.bound:.3g}"
                out.append(f"    {c.quantity:22s} forced={f:>10s} "
                           f"bound={b:>10s}  {c.direction}")
        return out


# --------------------------------------------------------------------------
# a site that actually triggers refusal
# --------------------------------------------------------------------------

def refusing_site():
    """Small components in near-still air, which is where the premise
    fails.

    The premise tests rise against advection, and it fails when there is
    too little advection rather than too much rise. A first version of
    this used large components on the assumption that a big release would
    break it; nothing failed at all. A site built to stay inside the
    premise cannot measure what the premise is worth, and neither can one
    built on the wrong guess about where it breaks."""
    from taxonomy import (ComponentSpec, Position, Primitive, Section,
                          Service, Site)
    return Site(
        name="premise-stressing",
        sections=[
            Section(id="TK", inventory_kg=5000, isolation_time_s=1800,
                    service=Service.LH2),
            Section(id="TR", inventory_kg=500, isolation_time_s=120,
                    service=Service.LH2)],
        components=[
            ComponentSpec(primitive=Primitive.VESSEL, service=Service.LH2,
                          tag="TK-1", nominal_diameter_m=0.012,
                          pressure_pa=6e5, temperature_k=22,
                          position=Position(x=0, y=0), section_id="TK"),
            ComponentSpec(primitive=Primitive.PIPE, service=Service.LH2,
                          count=6, tag="LP", nominal_diameter_m=0.012,
                          pressure_pa=6e5, temperature_k=22,
                          position=Position(x=20, y=0), section_id="TR"),
            ComponentSpec(primitive=Primitive.VALVE, service=Service.LH2,
                          count=8, tag="LV", nominal_diameter_m=0.012,
                          pressure_pa=6e5, temperature_k=22,
                          position=Position(x=25, y=0), section_id="TR")])


def still_air_weather(n_sectors: int = 12, wind_m_s: float = 0.3):
    """Class F at 0.3 m/s, which is where the premise actually fails.

    Found by scanning rather than assumed. At 1.5 m/s nothing fails at
    all: the cold cloud is dense, sinks rather than rises, and the
    rise-to-advection ratio stays near zero over the range the answer is
    read. The premise fails for SMALL releases in NEAR-STILL air, where
    there is little advection to compete with the rise -- the opposite of
    the large-release case that was assumed at first.

    Sector probabilities still sum to one: a weather set that does not
    close scales the whole answer, and that is a separate defect from
    the one being measured here."""
    import pipeline as P
    p = 1.0 / n_sectors
    return [P.Weather(
        label=f"F {wind_m_s}", wind_m_s=wind_m_s, stability="F",
        sectors=[P.WeatherSector(f"F {wind_m_s}", (i * 360 / n_sectors,
                                           (i + 1) * 360 / n_sectors),
                                 p_day=p, p_night=p)
                 for i in range(n_sectors)])]


# --------------------------------------------------------------------------

def probe_quantities(rate_kg_s: float = 0.1, wind_m_s: float = 0.3
                     ) -> list[QuantityComparison]:
    """What the gate refuses for one condition, and what it was holding."""
    import dispersion_cache as dc
    import slabx_adapter as SX
    dc.clear()
    r = SX.dispersion(rate_kg_s, wind_m_s, duration_s=600.0, stability="F",
                      liquid_fraction=0.0)
    out = []
    for name in ("lfl_distance_m", "flammable_mass_kg", "footprint_area_m2",
                 "cloud_top_height_m"):
        g = getattr(r, name)
        if g.refused:
            out.append(QuantityComparison(
                quantity=name, reason=g.reason,
                forced=g.forced_value, bound=g.bound))
    return out


def run(site=None, weather=None) -> Experiment:
    import export
    import pipeline as P
    from ignition import IgnitionScheme

    site = site or refusing_site()
    weather = weather or still_air_weather()

    gated = P.run(site, weather=weather, half_extent_m=400, cell_size_m=50,
                  ignition_scheme=IgnitionScheme.HYRAM,
                  refuse_policy=RefusePolicy.EXCLUDE)
    forced = P.run(site, weather=weather, half_extent_m=400, cell_size_m=50,
                   ignition_scheme=IgnitionScheme.HYRAM,
                   refuse_policy=RefusePolicy.FORCE)

    return Experiment(
        site_name=site.name,
        ir_gated=gated.max_ir, ir_forced=forced.max_ir,
        integral_gated=export.risk_integral(gated),
        integral_forced=export.risk_integral(forced),
        refused_frequency=gated.coverage.refused_frequency,
        total_frequency=gated.coverage.total_frequency,
        comparisons=probe_quantities())


VERDICT_TEMPLATE = """
What the numbers mean

  refused share      the fraction of enumerated frequency the gate
                     removes. Below a few percent, gating is a nicety;
                     the argument for it is about honesty rather than
                     magnitude.

  IR ratio           forced over gated. Above one, refusing LOWERS the
                     reported risk, so the gate is costing conservatism
                     and the coverage statement carrying "LOWER BOUND"
                     is doing real work. Below one, refusing RAISES it,
                     and the gate is protecting against a model that
                     under-predicts outside its premise.

  direction per      whether each forced value is larger or smaller than
  quantity           the premise edge, which is the last place the model
                     was inside its own assumptions.
"""


if __name__ == "__main__":
    e = run()
    print("\n".join(e.lines()))
    print(VERDICT_TEMPLATE)
