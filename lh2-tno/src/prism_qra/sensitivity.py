"""
Sensitivity to the unresolved items.

The verification backlog lists things that are not settled. It does not
say which of them matter. This measures that: each is perturbed across
the range the disagreement actually spans, one at a time, and the effect
on maximum individual risk is recorded.

Why one at a time
-----------------
These are not independent uncertainties to be combined. Each is a
disagreement with a specific alternative -- one published correlation
against another, a value read against a value calibrated -- so the
question is "what would the answer be if the other side is right",
not "what is the joint distribution". Combining them would produce a
spread that corresponds to no defensible position.

What this cannot do
-------------------
It measures sensitivity, not error. An item that moves the answer by
1% is not thereby correct; it is unimportant to THIS site with THIS
component mix. A site dominated by a different component would rank
them differently, which is why the ranking is reported alongside the
site it was computed for rather than as a property of the system.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Callable

warnings.filterwarnings("ignore")


@dataclass
class Case:
    """One unresolved item and the alternative it is measured against."""
    key: str
    question: str
    baseline: str
    alternative: str
    apply: Callable[[], None]
    restore: Callable[[], None]
    note: str = ""


@dataclass
class Metrics:
    """Several, because one is not enough.

    Maximum individual risk is dominated by whatever is closest to the
    worst cell, so an item that changes a distant contour leaves it
    untouched. Reporting that as zero sensitivity would say the item does
    not matter when what happened is that it never entered the metric.
    Contour area and the risk integrated over the grid catch that; the
    count of contributions catches an item that removes a pathway
    entirely."""
    max_ir: float
    integrated_ir: float          # risk-area integral, IR summed x cell area
    area_1e6_cells: int           # cells above 1e-6/yr
    n_contributions: int
    reached: bool                 # did the perturbed path run at all


@dataclass
class Result:
    key: str
    question: str
    baseline: Metrics
    alternative: Metrics
    note: str = ""

    def _r(self, a: float, b: float) -> float:
        return b / a if a > 0 else (math.inf if b > 0 else 1.0)

    @property
    def ratio(self) -> float:
        return self._r(self.baseline.max_ir, self.alternative.max_ir)

    @property
    def integrated_ratio(self) -> float:
        return self._r(self.baseline.integrated_ir,
                       self.alternative.integrated_ir)

    @property
    def area_ratio(self) -> float:
        return self._r(float(self.baseline.area_1e6_cells),
                       float(self.alternative.area_1e6_cells))

    @property
    def swing_pct(self) -> float:
        return (self.ratio - 1.0) * 100.0

    @property
    def untouched(self) -> bool:
        """Nothing moved on any metric. Either the item genuinely does not
        matter here, or the path it perturbs never ran."""
        return (abs(self.ratio - 1.0) < 1e-9
                and abs(self.integrated_ratio - 1.0) < 1e-9)


# --------------------------------------------------------------------------

def reference_site():
    """The demonstration station: LH2 tank, transfer section, high
    pressure gas, a vacuum-jacketed line and a cryogenic pump."""
    from taxonomy import (AssemblySpec, Assembly, ComponentSpec, Position,
                          Primitive, Section, Service, Site)
    return Site(
        name="reference",
        sections=[
            Section(id="TK", inventory_kg=5000, isolation_time_s=1800,
                    service=Service.LH2),
            Section(id="TR", inventory_kg=80, isolation_time_s=30,
                    service=Service.LH2),
            Section(id="HP", inventory_kg=120, isolation_time_s=15,
                    service=Service.GH2)],
        components=[
            ComponentSpec(primitive=Primitive.VESSEL, service=Service.LH2,
                          tag="TK-101", nominal_diameter_m=0.05,
                          pressure_pa=6e5, temperature_k=22,
                          position=Position(x=0, y=0), section_id="TK"),
            ComponentSpec(primitive=Primitive.VALVE, service=Service.LH2,
                          count=6, tag="LV-201", nominal_diameter_m=0.05,
                          pressure_pa=6e5, temperature_k=22,
                          position=Position(x=25, y=0), section_id="TR"),
            ComponentSpec(primitive=Primitive.FLANGE, service=Service.LH2,
                          count=12, tag="FL-201", nominal_diameter_m=0.05,
                          pressure_pa=6e5, temperature_k=22,
                          position=Position(x=25, y=10), section_id="TR"),
            ComponentSpec(primitive=Primitive.VALVE, service=Service.GH2,
                          count=12, tag="HV-301", nominal_diameter_m=0.012,
                          pressure_pa=4.5e7, temperature_k=288,
                          position=Position(x=80, y=0), section_id="HP")],
        assemblies=[
            AssemblySpec(assembly=Assembly.VJ_LINE, service=Service.LH2,
                         tag="VJ-201", count=3, nominal_diameter_m=0.05,
                         pressure_pa=6e5, temperature_k=22,
                         position=Position(x=12, y=0), section_id="TR"),
            AssemblySpec(assembly=Assembly.LH2_PUMP, service=Service.LH2,
                         tag="P-401", nominal_diameter_m=0.04,
                         pressure_pa=8e5, temperature_k=22,
                         position=Position(x=35, y=5), section_id="TR")])


def measure(site, scheme_name: str = "hyram") -> Metrics:
    import numpy as np
    from ignition import IgnitionScheme
    import pipeline
    scheme = {"hyram": IgnitionScheme.HYRAM,
              "purple": IgnitionScheme.PURPLE}[scheme_name]
    r = pipeline.run(site, half_extent_m=300, cell_size_m=50,
                     ignition_scheme=scheme)
    g = np.asarray(r.grid.values)
    # Area-weighted, not a bare cell sum. A bare sum scales with the
    # number of cells, so it is not comparable between grid resolutions
    # and is not a physical quantity; multiplying by the cell area gives
    # the risk integrated over the ground, which converges.
    return Metrics(max_ir=float(g.max()),
                   integrated_ir=float(g.sum()) * r.grid.cell_size_m ** 2,
                   area_1e6_cells=int((g >= 1e-6).sum()),
                   n_contributions=len(r.contributions),
                   reached=True)


# --------------------------------------------------------------------------
# the cases
# --------------------------------------------------------------------------

def build_cases() -> list[Case]:
    import fire as F

    import taxonomy as T
    cases: list[Case] = []

    # 1. the cryogenic pump, the only unsourced row, and named as the
    #    dominant risk unit by two independent published QRAs
    pump = T.FREQUENCY_LIBRARY[(T.Primitive.PUMP_SEAL, T.Fuel.OANDG)]
    original_pump = list(pump.medians)
    # Yoo et al. give 5.0e-5/yr for catastrophic rupture. Placed in the
    # full-bore bin, with the smaller bins scaled by the same factor.
    scale = 5.0e-5 / original_pump[4]

    def _pump_yoo():
        pump.medians[:] = [v * scale for v in original_pump]

    def _pump_restore():
        pump.medians[:] = original_pump

    cases.append(Case(
        key="pump_seal_frequency",
        question="what if the cryogenic pump frequency is the published "
                 "value rather than the oil and gas proxy",
        baseline=f"{original_pump[4]:.2e}/yr full bore, unsourced",
        alternative="5.0e-5/yr, Yoo et al. (2021) ref [60]",
        apply=_pump_yoo, restore=_pump_restore,
        note="the only unsourced row in the library, and two independent "
             "published LH2 QRAs name this component as the dominant "
             "risk unit"))

    # 2. the radiant fraction residual
    original_molina = F.MOLINA_UNEXPLAINED_FACTOR.value

    def _molina_off():
        object.__setattr__(F.MOLINA_UNEXPLAINED_FACTOR, "value", 1.0)

    def _molina_restore():
        object.__setattr__(F.MOLINA_UNEXPLAINED_FACTOR, "value",
                           original_molina)

    cases.append(Case(
        key="molina_residual",
        question="what if the published correlation is right as written "
                 "and the factor of 22.7 is an error here",
        baseline="factor 22.7 applied to match an independent code",
        alternative="factor 1, correlation taken at face value",
        apply=_molina_off, restore=_molina_restore,
        note="reading the source ruled out a_p, the residence time "
             "definition, flame length and flame width; what remains is "
             "the functional form and extrapolation below the fitted range"))

    # 3. the LH2 joint frequency anomaly, which is what actually
    #    dominates: Brooks et al. publish larger leaks as MORE frequent
    #    than smaller ones for hoses and joints and say they cannot tell
    #    whether that is physical or an artefact.
    joint = T.FREQUENCY_LIBRARY[(T.Primitive.JOINT, T.Fuel.LH2)]
    original_joint = list(joint.medians)

    def _joint_monotone():
        # Give the joint the SHAPE the other components have, anchored on
        # its own smallest bin, rather than an arbitrary decade per step.
        #
        # A first attempt used m0 * 10^-i, which drops the full-bore bin
        # by 36,700 and is not a monotone reordering but a deletion. It
        # reported a sixfold effect that was the size of the perturbation,
        # not the size of the anomaly. The shape below is the median of
        # the valve, flange and pipe rows, all of which fall with leak
        # size the way every other component in the library does.
        ref = []
        for p in (T.Primitive.VALVE, T.Primitive.FLANGE, T.Primitive.PIPE):
            e = T.FREQUENCY_LIBRARY[(p, T.Fuel.LH2)]
            ref.append([v / e.medians[0] for v in e.medians])
        shape = [sorted(col)[len(col) // 2] for col in zip(*ref)]
        joint.medians[:] = [original_joint[0] * f for f in shape]

    def _joint_restore():
        joint.medians[:] = original_joint

    cases.append(Case(
        key="lh2_joint_anomaly",
        question="what if the rising trend with leak size in the LH2 "
                 "joint row is an artefact",
        baseline=f"as published, {original_joint[4]:.2e} at full bore "
                 f"against {original_joint[0]:.2e} at 0.01%",
        alternative="given the falling shape the valve, flange and pipe "
                    "rows share, anchored on its own smallest bin",
        apply=_joint_monotone, restore=_joint_restore,
        note="the authors state they cannot explain the trend; this row "
             "carries most of the risk on this site"))

    # 4. the x1.25 safety factor on LH2 flammable distance, derived from
    #    and evaluated on the same six FFI trials
    # slabx takes the factor as a DEFAULT ARGUMENT, so rebinding the
    # module constant does nothing once the function object exists. The
    # adapter's call has to be intercepted instead. Getting this wrong
    # produced a clean 1.00 that looked like insensitivity and was a
    # perturbation that never happened.
    import slabx_adapter as SX
    _orig_fd = SX.flammable_distance

    def _sf_off():
        def _no_factor(traj, atm, *a, **kw):
            kw["safety_factor"] = 1.0
            return _orig_fd(traj, atm, *a, **kw)
        SX.flammable_distance = _no_factor
        import dispersion_cache as _dc
        _dc.clear()          # results are memoised; a stale cache hides
                             # the perturbation entirely

    def _sf_restore():
        SX.flammable_distance = _orig_fd
        import dispersion_cache as _dc
        _dc.clear()

    cases.append(Case(
        key="lfl_safety_factor",
        question="what if the x1.25 factor on LH2 flammable distance is "
                 "dropped",
        baseline="x1.25 applied",
        alternative="raw model distance",
        apply=_sf_off, restore=_sf_restore,
        note="the factor was derived from and evaluated on the same six "
             "FFI trials, so it is not independently validated"))

    # 5. Molkov conservative against best fit
    # 5. Molkov conservative against best fit
    def _molkov_fit():
        object.__setattr__(F.C_MOLKOV_CONSERVATIVE, "value",
                           float(F.C_MOLKOV_FIT))

    def _molkov_restore():
        object.__setattr__(F.C_MOLKOV_CONSERVATIVE, "value", 116.0)

    cases.append(Case(
        key="flame_length_branch",
        question="what if the best fit is used instead of the "
                 "conservative flame length",
        baseline="116 (mdot D)^0.347, the upper limiting curve",
        alternative="76 (mdot D)^0.347, the best fit",
        apply=_molkov_fit, restore=_molkov_restore,
        note="a separation distance from a best fit is exceeded by half "
             "the data behind it"))

    # 6. LH2 fireball extrapolated three orders past its data
    import fireball as FB
    _orig_fb = FB.C_LH2_CONSERVATIVE.value

    def _fb_fit():
        object.__setattr__(FB.C_LH2_CONSERVATIVE, "value",
                           float(FB.C_LH2_BEST_FIT))

    def _fb_restore():
        object.__setattr__(FB.C_LH2_CONSERVATIVE, "value", _orig_fb)

    cases.append(Case(
        key="lh2_fireball_branch",
        question="what if the LH2 fireball best fit is used instead of "
                 "the conservative curve",
        baseline="10 m^0.45, conservative",
        alternative="8.16 m^0.45, best fit",
        apply=_fb_fit, restore=_fb_restore,
        note="both are extrapolated three orders beyond the 0.2 to 6.3 kg "
             "the correlation was fitted over"))

    # 7. VJ release probability
    vj = T.ASSEMBLY_COMPOSITION[T.Assembly.VJ_LINE]
    _orig_vj = list(vj)

    def _vj_old():
        vj[:] = [(p, n, o, T.ReleasePath.VIA_RELIEF, 0.1)
                 for (p, n, o, _pth, _pb) in _orig_vj]

    def _vj_restore():
        vj[:] = _orig_vj

    cases.append(Case(
        key="vj_release_probability",
        question="what if a vacuum-jacketed inner leak reaches atmosphere "
                 "only one time in ten",
        baseline="unit probability, as the incident report shows",
        alternative="0.1, the invented value that stood before it",
        apply=_vj_old, restore=_vj_restore,
        note="both paths route to the same physics, so the probability is "
             "the whole of the difference"))

    # 8. ignition scheme, already measured but included for ranking
    cases.append(Case(
        key="ignition_scheme",
        question="what if the free field bound is used instead of the "
                 "hydrogen-specific set",
        baseline="HYRAM",
        alternative="PURPLE, free field without the escape clause",
        apply=lambda: None, restore=lambda: None,
        note="handled by re-running rather than by patching"))

    return cases


# --------------------------------------------------------------------------

def outcome_shares(site) -> dict:
    """Which outcome types carry the risk here. An item that only affects
    an outcome absent from this list cannot move anything, and that is a
    property of the site rather than of the item."""
    import collections
    from ignition import IgnitionScheme
    import pipeline
    r = pipeline.run(site, half_extent_m=300, cell_size_m=50,
                     ignition_scheme=IgnitionScheme.HYRAM)
    by = collections.defaultdict(float)
    for c in r.contributions:
        by[c.ignition_event] += c.delta_ir
    total = sum(by.values()) or 1.0
    return {k: v / total for k, v in
            sorted(by.items(), key=lambda x: -x[1])}


def run(site=None) -> list[Result]:
    site = site or reference_site()
    base = measure(site)
    out: list[Result] = []
    for c in build_cases():
        if c.key == "ignition_scheme":
            alt = measure(site, "purple")
        else:
            c.apply()
            try:
                alt = measure(site)
            finally:
                c.restore()
        out.append(Result(c.key, c.question, base, alt, c.note))
    out.sort(key=lambda r: -max(abs(math.log10(max(r.ratio, 1e-12))),
                                abs(math.log10(max(r.integrated_ratio,
                                                   1e-12)))))
    return out


def report(results: list[Result], site=None) -> list[str]:
    b = results[0].baseline
    lines = [f"baseline: max IR {b.max_ir:.3e}/yr, "
             f"integrated {b.integrated_ir:.3e}, "
             f"{b.area_1e6_cells} cells above 1e-6", ""]
    if site is not None:
        shares = outcome_shares(site)
        lines.append("risk carried by: " + ", ".join(
            f"{k} {v*100:.0f}%" for k, v in shares.items()))
        lines.append("")
    lines.append(f"{'item':24}{'max IR':>10}{'integrated':>12}"
                 f"{'area':>8}   status")
    lines.append("-" * 72)
    for r in results:
        # rank by how far the ratio is from one in EITHER direction; an
        # item that halves the answer matters as much as one that doubles
        # it, and comparing a percentage swing against a threshold hides
        # that because a ratio of 0.17 is only a -83% swing.
        dev = max(r.ratio, 1.0 / max(r.ratio, 1e-12))
        status = ("PATH NOT EXERCISED" if r.untouched
                  else "dominant" if dev >= 2.0
                  else "material" if dev >= 1.2
                  else "minor")
        lines.append(f"{r.key:24}{r.ratio:10.2f}{r.integrated_ratio:12.2f}"
                     f"{r.area_ratio:8.2f}   {status}")
    return lines


if __name__ == "__main__":
    site = reference_site()
    rs = run(site)
    print("\n".join(report(rs, site)))
