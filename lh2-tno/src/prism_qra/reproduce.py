#!/usr/bin/env python3
"""
Reproduce every number this project claims.

Writes results.json. Nothing quoted in a document or a paper should be
typed by hand; it should be read out of here, so that a claim and the code
that produces it cannot drift apart.

Each entry carries:

    value       the number
    grade       what it may be claimed as
    source      where the number came from
    claim       what it is evidence for, in one line

Entries whose grade is PLACEHOLDER or whose source is a calibration are
still emitted. Omitting them would make the register look stronger than
the work is.

    python3 reproduce.py            write results.json
    python3 reproduce.py --check    compare against the existing file
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from result_comparison import differences

warnings.filterwarnings("ignore")

RESULTS: dict[str, dict[str, Any]] = {}


def record(key: str, value: Any, grade: str, source: str, claim: str) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(
            f"{key} is {value}. A non-finite result is not a result, and "
            f"JSON has no way to spell it. Either the quantity is undefined "
            f"here and should not be recorded, or the case is wrong.")
    RESULTS[key] = {"value": value, "grade": grade, "source": source,
                    "claim": claim}
    return value


# --------------------------------------------------------------------------

def purple_book_6b() -> None:
    """The only fully worked example in the Purple Book."""
    from risk import (CO_PROBIT, PdRoute, RiskContribution, WeatherSector,
                      effective_cloud_width, gaussian_lateral_pi,
                      probability_covered, probit_to_probability)

    G, S = "PUBLISHED_VALIDATED", "Purple Book (CPR 18E) Appendix 6.B"
    w = WeatherSector("D 5.0", (196.0, 225.0), 0.0376, 0.0362)
    record("6B.pm_pphi", w.pm_pphi, G, S,
           "weather and wind-direction probability, day/night blended")

    pr = CO_PROBIT.probit(21300.0, 30.0)
    record("6B.probit", pr, G, S, "CO probit on the centreline")
    pcl = probit_to_probability(pr)
    record("6B.p_centreline", pcl, G, S, "centreline lethality")

    lo, hi = 1.0, 500.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if gaussian_lateral_pi(pr, mid) < 72.0 else (lo, mid)
    sigma_y = 0.5 * (lo + hi)
    record("6B.sigma_y_implied", sigma_y, "PUBLISHED_UNVALIDATED", S,
           "lateral dispersion coefficient the book does not print, "
           "recovered from PI = 72 m; the target for a Gaussian plume "
           "implementation at 361 m, class D 5.0, z0 = 0.1 m")

    ecw = effective_cloud_width(72.0, pcl)
    record("6B.effective_cloud_width_m", ecw, G, S, "equivalent top-hat width")
    pci = probability_covered(ecw, 361.0, 12)
    record("6B.p_covered", pci, G, S, "wind sector coverage, eq 6.10")
    pd = pcl * pci
    record("6B.p_death", pd, G, S, "probability of death at the grid point")

    c = RiskContribution(loc_id="pipe rupture", weather_class="D 5.0",
                         sector_deg=(196, 225), ignition_event=None,
                         pm_pphi=w.pm_pphi, p_ignition=1.0, p_death=pd,
                         frequency_per_year=5e-7, route=PdRoute.TOXIC)
    record("6B.delta_ir", c.delta_ir, G, S,
           "individual risk contribution; the book prints 7.0e-9")


def red_book_104() -> None:
    """Includes the arithmetic error the book's own closure rule rejects."""
    G, S = "PUBLISHED_VALIDATED", "Red Book (CPR 12E) section 10.4"
    pa, pb, pc, pd = 5.0e-7, 0.7, 0.7, 0.1
    out = {"safe_dispersal": pa * (1 - pb) * (1 - pc),
           "flash_fire": pa * (1 - pb) * pc * (1 - pd),
           "uvce": pa * (1 - pb) * pc * pd,
           "bleve": pa * pb}
    for k, v in out.items():
        record(f"10.4.{k}", v, G, S, "event tree outcome frequency")
    record("10.4.closure", sum(out.values()), G, S,
           "sum of outcomes; must equal the initiating frequency 5.0e-7")
    record("10.4.book_flash_fire_printed", 9.8e-8, "PUBLISHED_VALIDATED", S,
           "the value printed in the book")
    record("10.4.book_total_with_printed_value",
           4.5e-8 + 9.8e-8 + 1.05e-8 + 3.5e-7, "PUBLISHED_VALIDATED", S,
           "outcomes summed using the printed flash fire value: 5.035e-7 "
           "against an initiating frequency of 5.0e-7, so the book's own "
           "closure criterion rejects its own number")


def source_terms() -> None:
    from source_term import discharge, ideal_gas_choked
    G = "PUBLISHED_VALIDATED"
    S = "isentropic maximum mass flux with CoolProp; cross-checked"
    for d_mm, p_bar in [(3.0, 100.0), (6.0, 350.0), (12.0, 450.0),
                        (25.0, 700.0)]:
        r = discharge(p_bar * 1e5, 288.15, "Hydrogen", d_mm / 1000.0)
        record(f"source.gh2.{d_mm:g}mm_{p_bar:g}bar.rate_kg_s",
               r.rate_kg_s, G, S,
               "choked discharge rate; agrees with an independent "
               "implementation to four significant figures")
    r = discharge(4.5e7, 288.15, "Hydrogen", 0.012)
    record("source.gh2.z_at_450bar", r.z_stagnation, G, S,
           "compressibility factor; ideal gas is 30% out on density")
    q_i = ideal_gas_choked(4.5e7, 288.15, 0.012)
    record("source.gh2.ideal_gas_rate_error", q_i / r.rate_kg_s - 1.0, G, S,
           "yet only 5% out on rate: the density error and the expansion "
           "behaviour partly cancel")

    r = discharge(6e5, None, "ParaHydrogen", 0.05, saturated_liquid=True)
    record("source.lh2.50mm_6bar.rate_kg_s", r.rate_kg_s, G,
           "homogeneous equilibrium model", "flashing discharge rate")
    record("source.lh2.50mm_6bar.throat_quality", r.throat_quality, G,
           "homogeneous equilibrium model",
           "vapour fraction at the throat; further flashing follows")


def fire() -> None:
    import fire as F
    from source_term import discharge

    def flame(d_mm, p_bar):
        d = d_mm / 1000.0
        r = discharge(p_bar * 1e5, 288.15, "Hydrogen", d)
        rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
        nz = F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                               r.velocity_m_s, rho, d)
        return r, F.flame_length(r.rate_kg_s, nz, hole_diameter_m=d,
                                 model="delichatsios")

    S_L = "Delichatsios (1993) eq.18, read from the paper"
    S_R = ("Molina, Schefer & Houf (2007), via HyRAM+ technical reference; "
           "power-form output includes the unresolved 22.7 multiplier")
    G_RAD = F.FIRE_PROV.grade.value
    ref_len = {3.0: 3.82, 6.0: 13.73, 12.0: 30.65, 25.0: 68.61}
    ref_rad = {3.0: 0.26, 6.0: 6.38, 12.0: 46.81, 25.0: 394.69}

    for d_mm, p_bar in [(3.0, 100.0), (6.0, 350.0), (12.0, 450.0),
                        (25.0, 700.0)]:
        r, fl = flame(d_mm, p_bar)
        k = f"fire.{d_mm:g}mm_{p_bar:g}bar"
        record(f"{k}.flame_length_m", fl.length_m, "PUBLISHED_UNVALIDATED", S_L,
               "calculated jet flame length; not an independent experiment")
        record(f"{k}.flame_length_ratio_to_reference",
               fl.length_m / ref_len[d_mm], "PUBLISHED_UNVALIDATED", S_L,
               "against an independent implementation of the same "
               "correlation; all four cases agree within 1% after using "
               "the published flame-temperature Froude term; this is "
               "implementation agreement, not physical validation")
        record(f"{k}.radiant_fraction", fl.radiant_fraction,
               G_RAD, S_R,
               "calibrated/extrapolated engineering output; the unresolved "
               "multiplier prevents a validated-radiation claim")
        record(f"{k}.radiant_power_ratio_to_reference",
               fl.radiant_power_w / 1e6 / ref_rad[d_mm],
               G_RAD, S_R, "agreement with another implementation after "
               "applying the unexplained multiplier is not validation")

    # Measured at 25 m, past the flame tip in every bearing, because at
    # 15 m the head-on case is inside the envelope and the ratio is not a
    # ratio of fluxes but of a flux to flame contact.
    # Molkov, the hydrogen-specific correlation now used by the pipeline
    for d_mm, p_bar in [(3.0, 100.0), (6.0, 350.0), (25.0, 700.0)]:
        rr, _ = flame(d_mm, p_bar)
        k = f"fire.molkov.{d_mm:g}mm_{p_bar:g}bar"
        record(f"{k}.length_fit_m",
               F.molkov_flame_length(rr.rate_kg_s, d_mm / 1000.0, False),
               "PUBLISHED_UNVALIDATED" if d_mm <= 10.1 else "ENGINEERING_JUDGEMENT",
               "Molkov & Saffers (2013) eq.8, best fit to 95 points",
               "calculated flame length; the 95-point development family "
               "is not independent validation, and 25 mm is outside the "
               "0.4-10.1 mm equation-8 development diameter range")
        record(f"{k}.length_conservative_m",
               F.molkov_flame_length(rr.rate_kg_s, d_mm / 1000.0, True),
               "PUBLISHED_UNVALIDATED" if d_mm <= 10.1 else "ENGINEERING_JUDGEMENT",
               "Molkov & Saffers (2013), upper limiting curve",
               "development-data upper curve used for engineering "
               "screening; not a probabilistic or universal upper bound")

    _, fl = flame(6.0, 350.0)
    record("fire.flame_width_ratio", float(F.FLAME_WIDTH_RATIO),
           "PUBLISHED_VALIDATED",
           "Hankinson & Lowesmith (2012) sec.5, citing Sivathanu & Gore",
           "flame envelope width as a fraction of visible length; the "
           "radius is half of it, and conflating the two doubled the "
           "exclusion zone in an earlier version")
    record("fire.weighting_peak_fraction", float(F.PEAK_FRACTION),
           "PUBLISHED_VALIDATED",
           "Hankinson & Lowesmith (2012) eq.15, n = 0.75N",
           "position of the emission peak along the flame axis; an assumed "
           "triangle peaking at 0.6 stood here before")
    tip = F.heat_flux(fl, fl.length_m * 1.02, 1.0, bearing_deg=0.0)
    record("fire.flux_just_past_tip_kw", tip / 1e3, G_RAD,
           S_R, "calculated flux at 6 mm and 350 bar, below the "
           "35 kW/m2 threshold: for hydrogen that contour lies inside the "
           "flame in this example; no validated thermal-distance claim")
    d35 = F.distance_to_flux(fl, 35e3, bearing_deg=0.0)
    record("fire.distance_to_35kw_head_on_m", d35, G_RAD,
           S_R, "screening distance with an unresolved calibration factor; "
           "cross-implementation agreement is not experimental validation")
    head = F.heat_flux(fl, 25.0, 1.0, bearing_deg=0.0)
    across = F.heat_flux(fl, 25.0, 1.0, bearing_deg=90.0)
    record("fire.direction_ratio_at_25m", head / across, "ENGINEERING_JUDGEMENT",
           "own calculation", "flux at a fixed receptor, jet aimed at them "
           "versus across; the Purple Book event tree does not treat "
           "discharge direction at all")
    mean, worst, engulfed = F.heat_flux_direction_averaged(fl, 15.0, 1.0)
    record("fire.engulfed_bearing_fraction_at_15m", engulfed,
           "ENGINEERING_JUDGEMENT", "own calculation",
           "fraction of discharge directions for which a receptor 15 m away "
           "is inside the flame; there the outcome is contact, not a flux")
    record("fire.a_p_molina_table2", float(F.A_P_MOLINA_H2),
           "PUBLISHED_VALIDATED",
           "Molina, Schefer & Houf (2007) Table 2, RADCAL",
           "the value the correlation was fitted against, read from the "
           "paper that presents the correlation")
    record("fire.a_p_chmielewski_computed", F.planck_mean_absorption(),
           "PUBLISHED_VALIDATED",
           "Chmielewski & Gieras (2015) Table 2 and eq.10, computed",
           "0.126 1/m from HITEMP against 0.23 from RADCAL; a disagreement "
           "between spectroscopic databases, not a transcription error")
    _, fl6 = flame(6.0, 350.0)
    from source_term import discharge as _dis
    _r6 = _dis(3.5e7, 288.15, "Hydrogen", 0.006)
    record("fire.molina_group_for_6mm_350bar",
           F.residence_time(_r6.rate_kg_s, fl6.length_m)
           * float(F.A_P_MOLINA_H2) * float(F.T_ADIABATIC_H2) ** 4,
           "PUBLISHED_UNVALIDATED", "own calculation",
           "Molina's data spans about 5e13 to 1e16 on this abscissa; the "
           "releases modelled here land two orders below it, so the "
           "correlation is extrapolated below its entire fitted range")
    record("fire.molina_unexplained_factor",
           float(F.MOLINA_UNEXPLAINED_FACTOR), "ENGINEERING_JUDGEMENT",
           "UNEXPLAINED",
           "what remains once a_p is computed properly: the correlation "
           "under-predicts an independent implementation by this factor, "
           "near enough constant across five decades, so it is a constant "
           "somewhere and not a trend. A calibrated a_p of 177 had been "
           "hiding it inside a physical constant.")


def damage_figures() -> None:
    """The Purple Book damage figures, recorded directly.

    The reference case does not reach 35 kW/m2 anywhere on its grid, so it
    exercises neither the flame-contact branch nor the step at the
    threshold. A correction to those branches therefore moved no
    end-to-end number, which is exactly how a wrong branch survives. The
    figures are pinned here so that they are covered whatever the
    reference case happens to touch."""
    import damage as D
    G = "PUBLISHED_VALIDATED"
    S4 = "Purple Book Figure 5.4, read from the figure"
    S5 = "Purple Book Figure 5.5, read from the figure"

    r = D.heat_radiation(25e3, 20)
    record("fig5.4.below.pe", r.pe, G, S4, "probit lethality at 25 kW/m2")
    record("fig5.4.below.fe_in", r.fe_in, G, S4,
           "zero: the indoor population is taken as fully protected")
    record("fig5.4.below.fe_out_over_pe", r.fe_out / r.pe, G, S4,
           "0.14, the clothing factor; PE itself carries no such credit "
           "because it is the Individual Risk quantity")
    a = D.heat_radiation(40e3, 20)
    record("fig5.4.above.fe_in", a.fe_in, G, S4,
           "one above 35 kW/m2, where clothing and buildings both ignite")

    for name, p in [("high", 0.35), ("mid", 0.15), ("low", 0.05)]:
        o = D.overpressure(p)
        record(f"fig5.5.{name}.pe", o.pe, G, S5, f"PE at {p} barg")
        record(f"fig5.5.{name}.fe_in", o.fe_in, G, S5, f"FE_in at {p} barg")
        record(f"fig5.5.{name}.fe_out", o.fe_out, G, S5, f"FE_out at {p} barg")
    record("fig5.5.mid.pe_is_zero_while_fe_in_is_not", 1.0, G, S5,
           "an unprotected individual survives 0.1 to 0.3 barg while 2.5% "
           "of the indoor population does not, because what kills there is "
           "the building rather than the blast")

    f = D.flash_fire(1.0)
    record("fig5.3.inside.pe", f.pe, G,
           "Purple Book Figure 5.3, read from the figure",
           "death is certain inside the flame envelope, indoors and out")


def fireballs() -> None:
    """Hydrogen fireball, against the experiments in the source paper."""
    import fireball as FB
    G = "PUBLISHED_VALIDATED"
    S = "Makarov, Shentsov, Kuznetsov & Molkov (2021), Hydrogen 2(1) 134-146"

    for m, label, ref in [(1.367, "tamura", 10.95), (3.9, "shen_full", 15.4)]:
        v = FB.gh2_tank_rupture_fireball(m, conservative=False).size_m
        record(f"fireball.gh2.{label}.hemispherical_m", v, G, S,
               f"theoretical hemispherical diameter; the paper gives {ref} m")
    record("fireball.gh2.undervehicle_conservative_m",
           FB.gh2_tank_rupture_fireball(1.87).size_m, G, S,
           "equation 8 is calibrated to this 24 m measurement")
    record("fireball.gh2.undervehicle_pancake_m",
           FB.gh2_tank_rupture_fireball(1.87, width_to_height=22.6).size_m,
           G, S, "the flattening ratio the paper infers from that test")

    record("fireball.lh2.1.06kg_conservative_m",
           FB.lh2_spill_fireball(1.06).size_m, G, S,
           "equation 12; the paper states the binding Zabetakis point as "
           "10.37 m and this gives 10.27, a 1% gap on a mass that could "
           "not be confirmed from the retrieved text")
    for m in (80.0, 5000.0):
        f = FB.lh2_spill_fireball(m)
        record(f"fireball.lh2.{m:g}kg_size_m", f.size_m,
               "PUBLISHED_UNVALIDATED", S,
               "extrapolated: Zabetakis spanned 0.2 to 6.3 kg")

    yb = 2 * 3.24 * 5000.0 ** 0.325
    record("fireball.yellow_book_underprediction_at_5t",
           FB.lh2_spill_fireball(5000.0).size_m / yb,
           "PUBLISHED_VALIDATED", S,
           "how far the Yellow Book LPG correlation falls short of the "
           "hydrogen one at storage-tank scale, in the unsafe direction")
    record("fireball.a_p_yan_third_route", FB.planck_absorption_yan(),
           G, "Yan, Yue & He (2015) as used by Makarov et al.",
           "0.220 against Molina's 0.23; two independent routes within 5% "
           "settle the constant, so the factor of thirty in the radiant "
           "fraction chain is elsewhere")


def dispersion() -> None:
    import fire as F
    import gh2_jet as G
    from source_term import discharge
    S = "Schefer, Houf & Williams (2008) eqs.9-11 and Table 2"
    for d_mm, p_bar in [(3.0, 100.0), (6.0, 350.0), (12.0, 450.0)]:
        d = d_mm / 1000.0
        r = discharge(p_bar * 1e5, 288.15, "Hydrogen", d)
        rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
        nz = F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                               r.velocity_m_s, rho, d)
        fl = F.flame_length(r.rate_kg_s, nz, hole_diameter_m=d,
                            model="molkov", conservative=True)
        by_mass = G.centreline_distance_to_mass(G.LFL_MASS_FRACTION, nz)
        result = G.dispersion(
            r.rate_kg_s, 5.0, throat_pressure_pa=r.throat_pressure_pa,
            throat_velocity_m_s=r.velocity_m_s,
            throat_density_kg_m3=rho, hole_diameter_m=d)
        k = f"dispersion.gh2.{d_mm:g}mm_{p_bar:g}bar"
        record(f"{k}.lfl_distance_m", by_mass, "PUBLISHED_UNVALIDATED", S,
               "flammable extent, mass-fraction form")
        record(f"{k}.ratio_to_flame_length", by_mass / fl.length_m,
               "PUBLISHED_UNVALIDATED", S,
               "against the conservative Molkov flame; the LFL centreline "
               "distance remains longer than every flame model tested")
        record(f"{k}.footprint_area_m2", result.footprint_area_m2.value,
               "PUBLISHED_UNVALIDATED", S,
               "plan area inside LFL from the measured Gaussian radial "
               "mass-fraction profile, equation 11")
        record(f"{k}.flammable_mass_kg", result.flammable_mass_kg.value,
               "PUBLISHED_UNVALIDATED", S,
               "hydrogen mass inside LFL from equations 9 and 11; radial "
               "H2-air mixture density follows HyRAM+ v5 eq.76 at ambient "
               "temperature")


def cold_hydrogen() -> None:
    """What the uncovered fraction was, and what closed it."""
    import taxonomy as T
    from slabx_lh2 import air_condensation as ac
    G = "PUBLISHED_VALIDATED"

    for t_k in (250.0, 150.0, 40.0, 30.0):
        record(f"cold.density_ratio_at_{t_k:g}K", T.density_ratio_of(t_k),
               G, "CoolProp",
               "the parameter the jet correlation is built on; ambient "
               "hydrogen is 0.070 and ambient methane 0.556, and Schefer "
               "reports the decay constant independent of it across that "
               "range")
    record("cold.jet_route_upper_bound", T.JET_DENSITY_RATIO_MAX, G,
           "Schefer, Houf & Williams (2008) Table 2",
           "end of the validated density range; below it the cold band is "
           "interpolation rather than extrapolation")
    for sp, key in (("N2", "nitrogen"), ("O2", "oxygen")):
        o = ac.condensation_onset(species=sp)
        record(f"cold.air_condensation_onset_{key}_molpct",
               o["onset_mol_pct"], G,
               "slabx_lh2.air_condensation, no free parameters",
               "onset is above the 75 mol% upper flammability limit, so "
               "inside the flammable range no air has left the gas phase; "
               "this is the main physical objection to treating cold "
               "hydrogen with an ordinary dispersion model, and it is "
               "measured rather than assumed")


def blast_wave() -> None:
    import blast as B
    G, S = "PUBLISHED_VALIDATED", "Molkov & Kashkarov, ICHS 2015, paper 329"
    b = B.tank_rupture_blast(72.4e-3, 34.3e6, 300.15)
    record("blast.standalone.mass_kg", b.mass_kg, G, S,
           "Abel-Noble; the paper gives 1.654 and ideal gas would give "
           "1.18 times that")
    record("blast.standalone.mechanical_MJ", b.mechanical_energy_j / 1e6,
           G, S, "real-gas Brode; the paper gives 5.23")
    record("blast.standalone.products_radius_m", b.products_radius_m, G, S,
           "r_b, the hemisphere of complete combustion products; the "
           "paper gives 5.88 and uses it in place of the measured "
           "fireball, which made predictions worse")
    record("blast.standalone.chemical_over_mechanical",
           b.chemical_to_mechanical, G, S,
           "chemical energy reaching the blast against mechanical; the "
           "paper gives 1.4")
    u = B.tank_rupture_blast(88e-3, 31.8e6, 306.15, under_vehicle=True)
    record("blast.undervehicle.chemical_over_mechanical",
           u.chemical_to_mechanical, G, S,
           "thirty, because the mechanical energy went into throwing the "
           "vehicle 22 m. The prevailing view had been that combustion "
           "does not contribute to a blast wave at all")
    record("blast.standalone.starting_shock_solved", b.starting_shock, G, S,
           "solved from the shock-tube relation rather than read off the "
           "log-log figure, which the paper does and gets 52")
    record("blast.station_10m3_100MPa.starting_shock",
           B.starting_shock(100e6, 300.15), G, S, "the paper reads 110")
    for k, v in [("1pct_lung_haemorrhage", 100.0e3),
                 ("50pct_lung_haemorrhage", 140.0e3)]:
        record(f"blast.harm.{k}_pa", v, G, S + " Table 6",
               "peak overpressure, outdoors, direct pressure effect; not "
               "the same quantity as the Purple Book indoor fraction, "
               "which is dominated by building collapse")


def frequencies() -> None:
    import taxonomy as T
    S_G = "SAND2024-06491 Tables 1-1 and 4-1"
    S_L = "Brooks, Ehrhart & LaFleur (2021) Table 2"

    e = T.FREQUENCY_LIBRARY[(T.Primitive.FILTER, T.Fuel.GH2)]
    record("freq.filter.superseded_full_bore", 4.39e-3, "PUBLISHED_VALIDATED",
           S_G, "HyRAM+ v5.1 value, Table 1-1")
    record("freq.filter.current_full_bore", e.medians[4],
           "PUBLISHED_VALIDATED", S_G,
           "Table 4-1 recommendation, a factor of ninety lower; the two "
           "were both encountered during this work and neither was "
           "recognised as a different revision until the report was opened")

    v_l = T.FREQUENCY_LIBRARY[(T.Primitive.VESSEL, T.Fuel.LH2)]
    v_g = T.FREQUENCY_LIBRARY[(T.Primitive.VESSEL, T.Fuel.GH2)]
    a_l = T.FREQUENCY_LIBRARY[(T.Primitive.VALVE, T.Fuel.LH2)]
    a_g = T.FREQUENCY_LIBRARY[(T.Primitive.VALVE, T.Fuel.GH2)]
    record("freq.lh2_vessel_over_gh2_smallest",
           v_l.medians[0] / v_g.medians[0], "PUBLISHED_UNVALIDATED", S_L,
           "LH2 vessel against gaseous at the 0.01% bin")
    record("freq.lh2_valve_over_gh2_smallest",
           a_l.medians[0] / a_g.medians[0], "PUBLISHED_UNVALIDATED", S_L,
           "and the valve goes the other way, which a straight copy of the "
           "gaseous values could not produce")

    for prim in (T.Primitive.VESSEL, T.Primitive.HOSE):
        e = T.FREQUENCY_LIBRARY[(prim, T.Fuel.LH2)]
        for i, lab in enumerate(T.BIN_LABELS):
            if lab not in ("1%", "100%"):
                continue
            lo, hi = e.percentile(0.05)[i], e.percentile(0.95)[i]
            record(f"freq.lh2.{prim.value.lower()}.{lab}.span", hi / lo,
                   "PUBLISHED_UNVALIDATED", S_L,
                   "ratio of 95th to 5th percentile as published")

    record("freq.no_data_components", len(T.NO_DATA), "MEASURED",
           "audit of the library",
           "exchanger, vaporizer, arm and vent stack: no published leak "
           "frequency in any fuel. Sandia marks the first three infinite "
           "rather than estimating them; the vent stack was added after a "
           "retrospective check against real incidents and is decomposed "
           "into the relief devices that feed it")

    stale = sum(1 for x in T.FREQUENCY_LIBRARY.values()
                if x.provenance.transcription
                is T.TranscriptionSource.CODE_INSPECTION)
    record("freq.entries_not_read_from_report", stale, "MEASURED",
           "audit of the library", "entries still taken from software "
           "rather than from a publication")


def ignition() -> None:
    from ignition import (IgnitionScheme, Outcome, ReleaseType,
                          build_ignition_tree)
    S = "Purple Book 4.5-4.8 against HyRAM+ hydrogen defaults"
    import ignition_sources as ISRC
    for name, p in [("flare", 1.0), ("motor vehicle", 0.4),
                    ("pleasure craft", 0.1)]:
        s = ISRC.IgnitionSource(name, ISRC.SourceKind.POINT)
        record(f"ignition.source.{name.replace(' ', '_')}.p60",
               s.probability(60.0), "PUBLISHED_UNVALIDATED",
               "Purple Book Appendix 4.A eq.4.A.1 and Table 4.A.1",
               "recovers the tabulated one-minute value; the book warns "
               "these numbers are not well established")
    for label, dc in [("quiet_site", 0.10), ("beside_a_road", 0.784),
                      ("beside_a_chemical_plant", 0.90)]:
        t = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                                IgnitionScheme.PURPLE_SOURCES,
                                delayed_conditional=dc)
        record(f"ignition.method_a.{label}.p_ignited", t.p_ignited,
               "PUBLISHED_UNVALIDATED", "Purple Book 4.7.2 method A",
               "ignition probability from the sources actually present")
    free = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                               IgnitionScheme.PURPLE).p_ignited
    hy = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                             IgnitionScheme.HYRAM).p_ignited
    quiet = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                                IgnitionScheme.PURPLE_SOURCES,
                                delayed_conditional=0.10).p_ignited
    record("ignition.gap_free_field_over_hyram", free / hy,
           "PUBLISHED_UNVALIDATED", "own calculation",
           "the fifty-fold divergence that stood as the largest "
           "uncertainty in this system")
    record("ignition.gap_method_a_over_hyram", quiet / hy,
           "PUBLISHED_UNVALIDATED", "own calculation",
           "and what is left once 4.7.2 is read properly: most of the gap "
           "was method B applied without its escape clause, not a "
           "disagreement about hydrogen")

    for q in (0.06, 6.08):
        a = build_ignition_tree(ReleaseType.CONTINUOUS, q,
                                IgnitionScheme.PURPLE)
        b = build_ignition_tree(ReleaseType.CONTINUOUS, q,
                                IgnitionScheme.HYRAM)
        record(f"ignition.p_ignited_ratio_at_{q}kgs",
               a.p_ignited / b.p_ignited, "PUBLISHED_VALIDATED", S,
               "the two schemes are irreconcilable, and this is not a "
               "distribution but a choice between bodies of data")
        record(f"ignition.purple_no_ignition_at_{q}kgs",
               a.by_outcome(Outcome.NO_IGNITION), "PUBLISHED_VALIDATED", S,
               "stationary units take delayed ignition as 1 minus direct, "
               "so a release always ignites eventually")


def incident_comparison() -> None:
    """Against HIAD event 58, the only LH2 loss-of-vacuum release with a
    recorded rate."""
    from source_term import discharge
    import taxonomy as T
    G = "MEASURED"
    S = ("HIAD 2.1 event 58, LH2 rail tanker, Italy 1991-07-09, via "
         "European Commission JRC")
    record("incident.hiad58.recorded_rate_kg_s", 0.10, G, S,
           "2,500 kg vented over 25,000 s through the safety valves after "
           "a micro-crack in the outer wall lost the interspace vacuum")
    record("incident.hiad58.recorded_mass_kg", 2500.0, G, S,
           "whole inventory, and it did not ignite, in an inhabited area")
    q = discharge(6e5, None, "ParaHydrogen", T.VJ_RELIEF_DIAMETER_M,
                  stagnation_quality=(
                      T.VJ_RELIEF_VAPOUR_QUALITY_MIN)).rate_kg_s
    record("incident.hiad58.model_rate_kg_s", q, "PUBLISHED_UNVALIDATED",
           S, "with the relief bore fitted to that rate")
    bore = discharge(6e5, None, "ParaHydrogen", 0.05,
                     stagnation_quality=(
                         T.VJ_RELIEF_VAPOUR_QUALITY_MIN)).rate_kg_s
    record("incident.hiad58.full_bore_overprediction", bore / 0.10,
           "MEASURED", S,
           "what modelling the same high-vapour source state as a full-bore "
           "release of the 50 mm line would have given; this error was making the "
           "vacuum-jacketed line the dominant risk contributor")


def empirical_ignition() -> None:
    """HIAD 2.2, the first empirical figure available to this project on
    the largest single uncertainty in it."""
    import hiad
    G, S = "MEASURED", hiad.HIAD_PROV.source
    record("hiad.n_events", 1142, G, S, "events in the export")
    record("hiad.lh2_ignition_rate", hiad.LH2.rate, G, S,
           "conditional on a recorded release; 61 ignited of 172")
    record("hiad.gh2_ignition_rate", hiad.GH2.rate, G, S,
           "544 ignited of 689")
    record("hiad.lh2_over_gh2", hiad.lh2_over_gh2(), G, S,
           "liquid hydrogen ignites about half as often as gaseous; the "
           "quantity that survives reporting bias, because the bias "
           "applies to both phases")
    lo, hi = hiad.lh2_range()
    record("hiad.lh2_rate_low_quality", lo, G, S,
           "Q=2; the rate rises monotonically with quality grade, which "
           "is what reporting bias looks like")
    record("hiad.lh2_rate_high_quality", hi, G, S, "Q=5")
    record("hiad.vent_related_events", hiad.VENT_RELATED.n, G, S,
           "events naming a vent stack, relief valve, rupture disc or "
           "safety valve; the vent stack was added to the taxonomy after "
           "a retrospective check and this is how well represented it is")
    from ignition import (IgnitionScheme as _IS, ReleaseType as _RT,
                          build_ignition_tree as _bit)
    for _lab, _q, _sch, _dc in [
            ("hyram_small", 0.06, _IS.HYRAM, None),
            ("hyram_large", 60.0, _IS.HYRAM, None),
            ("purple_free_field", 6.08, _IS.PURPLE, None),
            ("purple_method_a_quiet", 6.08, _IS.PURPLE_SOURCES, 0.10)]:
        _p = _bit(_RT.CONTINUOUS, _q, _sch,
                  delayed_conditional=_dc).p_ignited
        _c = hiad.check_scheme(_sch.value, _p, "LH2")
        record(f"hiad.scheme_vs_record.{_lab}", _c.ratio_to_midpoint, G, S,
               "scheme probability over the midpoint of the recorded LH2 "
               "range; compared, never corrected, because the recorded "
               "figures are conditional on a release being REPORTED and a "
               "scheme's on one OCCURRING")

    record("hiad.largest_unignited_lh2_release_kg",
           max(m for m, _ in hiad.RELEASES_THAT_DID_NOT_IGNITE), G, S,
           "a model taking ignition as certain above some release rate "
           "has to account for 145 tonnes that did not ignite")


def new_phenomena() -> None:
    """The four capabilities added after a gap review against commercial
    consequence tools."""
    import blast as B
    import fragments as FR
    import indoor as IN
    import spill_fire as SF

    S1 = "Royle & Willoughby / Hall et al., HSL ignited LH2 spills"
    record("spill.radiative_fraction_low", float(SF.XRAD_SPILL_LOW),
           "PUBLISHED_VALIDATED", S1, "measured on ignited LH2 spills")
    record("spill.radiative_fraction_high", float(SF.XRAD_SPILL_HIGH),
           "PUBLISHED_VALIDATED", S1, "same")
    record("spill.sep_ratio_hydrocarbon_over_hydrogen",
           SF.SEP_HYDROCARBON_POOL / float(SF.SEP_H2_HIGH),
           "PUBLISHED_VALIDATED",
           "BAM hydrogen jet flame measurements against LNG Montoir and "
           "the Phoenix series",
           "using a hydrocarbon surface emissive power for hydrogen "
           "overstates the radiation by this much, and the Yellow Book "
           "has no hydrogen entry to prevent the substitution")

    S2 = "Yellow Book fragment treatment; Baker energy partition"
    t = FR.fragment_throw(1.54e8, 9200.0, 4)
    record("fragments.range_low_m", t.range_low_m, "ENGINEERING_JUDGEMENT",
           S2, "4 tonne LH2 tank at design pressure, ductile end of the "
               "energy partition")
    record("fragments.range_high_m", t.range_high_m,
           "ENGINEERING_JUDGEMENT", S2, "brittle end; a jacket at "
           "cryogenic temperature is the brittle case")

    S3 = "Purple Book equations 4.5 and 4.6, two points on the class 10 curve"
    record("blast.decay_exponent", float(B.DECAY_B),
           "PUBLISHED_VALIDATED", S3,
           "determined by the two anchors rather than imposed, and it "
           "lands between the near-field and far-field asymptotes of an "
           "ideal blast wave")
    b = B.tank_rupture_blast(72.4e-3, 34.3e6)
    for lab, p in (("0p30barg", 0.30e5), ("0p10barg", 0.10e5)):
        d = b.distance_to_overpressure(p)
        if d:
            record(f"blast.distance_to_{lab}_m", d,
                   "PUBLISHED_UNVALIDATED", S3,
                   "stand-alone tank test case")

    S4 = "mass balance with the Morton, Taylor & Turner length scale"
    room = IN.Enclosure(500.0, 100.0, 5.0)
    for lab, q, dm in (("small", 1e-5, 0.001), ("large", 1e-2, 0.010)):
        res = IN.accumulate(q, room, dm)
        record(f"indoor.{lab}_leak_regime",
               0.0 if res.regime is IN.MixingRegime.STRATIFIED else 1.0,
               "ENGINEERING_JUDGEMENT", S4,
               "0 stratified, 1 well mixed. A source Richardson number on "
               "the hole diameter gave 1e-7 for every case and never "
               "fired; the Morton length against ceiling height does")
        record(f"indoor.{lab}_leak_morton_length_m",
               IN.morton_length(q, dm), "ENGINEERING_JUDGEMENT", S4,
               "distance over which the release stops being a jet")


def external_validation() -> None:
    """The new phenomena against independently published numbers."""
    import blast as B
    import fireball as FB
    import spill_fire as SF
    G = "MEASURED"
    S = ("Kashkarov, Li & Molkov, ICHS 2019, hazard distance nomograms; "
         "same methodology and same coefficients as blast.py")
    b = B.tank_rupture_blast(0.300, 1000e5, 293.15)
    for lab, pa, ref in (("100kPa", 100e3, 7.0), ("23kPa", 23e3, 19.3),
                         ("16p5kPa", 16.5e3, 24.0),
                         ("4p8kPa", 4.8e3, 59.3)):
        d = b.distance_to_overpressure(pa)
        if d:
            record(f"validation.blast.{lab}_ratio", d / ref, G, S,
                   f"hazard distance here over theirs for a 300 L tank at "
                   f"1000 bar; they publish {ref} m")
    near, far = b.valid_distance_range()
    record("validation.blast.checked_range_far_m", far, G, S,
           "beyond this the single decay exponent runs 25% low, because "
           "their own points show the local exponent falling from 1.83 "
           "near field to 1.36 far field toward the acoustic limit")

    S2 = "Jahanbakhsh (2025), consequence analysis of a hydrogen tank explosion"
    record("validation.fireball.100kg_conservative_m",
           FB.gh2_tank_rupture_fireball(100.0).size_m,
           "PUBLISHED_UNVALIDATED", S2,
           "against a published 25 to 50 m for 10 to 100 kg; the "
           "conservative correlation sits above that band by design and "
           "the theoretical one lands inside it")
    record("validation.fireball.100kg_theoretical_m",
           FB.gh2_tank_rupture_fireball(100.0, conservative=False).size_m,
           "PUBLISHED_UNVALIDATED", S2, "the theoretical hemispherical value")

    sf = SF.spill_fire(6.08, 50.0)
    d5 = SF.burn_back_distance_to_flux(sf, 5e3)
    if d5:
        record("validation.spill_fire.5kW_distance_m", d5,
               "PUBLISHED_UNVALIDATED", S2,
               "against a published 15 to 30 m for 5 kW/m2; this is the "
               "conservative branch of a measured radiative fraction band")


def gh2_validation_matrix() -> None:
    """Coverage map for the independent GH2 dispersion and flame evidence."""
    import validation_matrix as V

    source = V.SANDIA_REPORT
    record("validation.gh2.evidence_rows", len(V.EVIDENCE),
           "PUBLISHED_UNVALIDATED", source,
           "independent evidence sources mapped to quantity, conditions, "
           "known bias, status, and next action")
    joint_lfl = sum(V.dispersion_joint_coverage(*case) == "JOINT_LFL_RANGE"
                    for case in V.DESIGN_CASES)
    joint_flame_statuses = {
        "PROUST_JOINT_RANGE", "EKOTO_JOINT_RANGE", "MOGI_JOINT_RANGE",
        "ROYLE_JOINT_RANGE_SOURCE_INCOMPLETE",
    }
    joint_flame = sum(
        V.flame_joint_coverage(*case) in joint_flame_statuses
        for case in V.DESIGN_CASES
    )
    record("validation.gh2.design_cases_joint_lfl_covered", joint_lfl,
           "PUBLISHED_UNVALIDATED", source,
           "number of four design cases jointly inside a published LFL-"
           "distance diameter-pressure test range; zero is the main "
           "dispersion-validation gap")
    record("validation.gh2.design_cases_joint_flame_covered", joint_flame,
           "PUBLISHED_UNVALIDATED", source,
           "number of four design cases jointly inside an identified flame "
           "test range; only the 3 mm case overlaps")
    for label, ratio in V.ekoto_hyram_ratios().items():
        record(f"validation.gh2.ekoto_hyram_{label}_ratio", ratio,
               "MEASURED", source,
               "published HyRAM+ prediction divided by the measured Ekoto "
               "value; contextual benchmark, not validation of this code")


def implementation_versus_model_choice() -> None:
    """Separating implementation error from model disagreement.

    Running the SAME correlation as an independent implementation returns
    the same numbers; running a different one returns different numbers.
    The distinction matters because agreement with another code is
    routinely reported as validation, and it is not: it shows the two
    implement the same thing."""
    import fire as F
    from hyram.phys import api
    from source_term import discharge
    G = "MEASURED"
    S = "same-condition run against an independent implementation"
    for d_mm, p_bar in ((6.0, 350.0), (12.0, 450.0)):
        d = d_mm / 1000.0
        r_ = discharge(p_bar * 1e5, 288.15, "Hydrogen", d)
        rho = r_.mass_flux_kg_m2s / max(r_.velocity_m_s, 1e-9)
        nz = F.notional_nozzle(r_.rate_kg_s, r_.throat_pressure_pa,
                               r_.velocity_m_s, rho, d)
        same = F.flame_length(r_.rate_kg_s, nz, model="delichatsios")
        diff = F.flame_length(r_.rate_kg_s, nz, hole_diameter_m=d,
                              model="molkov")
        f = api.Flame(api.Fluid(species="hydrogen", T=288.15, P=p_bar * 1e5),
                      api.Orifice(d),
                      api.Fluid(species="air", T=288.15, P=101325.0),
                      nn_conserve_momentum=True, nn_T="solve_energy",
                      verbose=False)
        f.solve()
        h = float(f.length())
        k = f"{d_mm:g}mm_{p_bar:g}bar"
        record(f"crosscheck.same_correlation.{k}", same.length_m / h, G, S,
               "same correlation as the independent implementation: the "
               "numbers agree, which shows the implementation is right "
               "and says nothing about the correlation")
        record(f"crosscheck.different_correlation.{k}",
               diff.length_m / h, G, S,
               "hydrogen-specific correlation instead: the difference is "
               "model choice, not implementation error")


def gating_experiment() -> None:
    """What refusing is worth. The main differentiator, measured."""
    import gating_experiment as GE
    G = "MEASURED"
    S = "gating_experiment.py, same site with and without the premise gate"
    cs = GE.probe_quantities()
    for c in cs:
        if c.forced is None:
            continue
        record(f"gating.forced.{c.quantity}", c.forced, G, S,
               "what the model returns outside its premise, kept only so "
               "that refusing can be compared against not refusing")
        if c.bound:
            record(f"gating.forced_over_bound.{c.quantity}",
                   c.ratio_to_bound, G, S,
                   "forced value over the premise edge, which is the last "
                   "place the model was inside its own assumptions. Below "
                   "one means forcing UNDER-predicts, so the gate is "
                   "protecting the answer rather than costing conservatism")


def release_height() -> None:
    """Height was accepted on every component and used nowhere."""
    import fire as F
    from source_term import discharge
    G = "MEASURED"
    S = "own calculation; EIGA Doc 06/19 5.1.2 and 5.1.7 for why it matters"
    r_ = discharge(3e5, 250.0, "Hydrogen", 0.05)
    rho = r_.mass_flux_kg_m2s / max(r_.velocity_m_s, 1e-9)
    nz = F.notional_nozzle(r_.rate_kg_s, r_.throat_pressure_pa,
                           r_.velocity_m_s, rho, 0.05)
    fl = F.flame_length(r_.rate_kg_s, nz, hole_diameter_m=0.05,
                        model="molkov")
    for h in (0.0, 3.0, 6.0):
        d = F.distance_to_flux(fl, 4e3, orientation="VERTICAL",
                               source_height_m=h)
        record(f"height.4kW_distance_at_{h:g}m", d if d else 0.0, G, S,
               "ground-level distance to 4 kW/m2 from a vent flame at "
               "this stack height; zero means the threshold is never "
               "reached at ground level, which is what a stack is for")


def equipment_damage_criteria() -> None:
    """API RP 581 thresholds, and the band they sit in."""
    import equipment_damage as ED
    G = "PUBLISHED_UNVALIDATED"
    S = "API RP 581 second edition (2008) section 5.8.2.3"
    for k, v in (("component_damage_overpressure_pa",
                  ED.DAMAGE_OVERPRESSURE_PA),
                 ("component_damage_heat_flux_w_m2",
                  ED.DAMAGE_HEAT_FLUX_W_M2),
                 ("personnel_injury_overpressure_pa",
                  ED.INJURY_OVERPRESSURE_PA),
                 ("personnel_injury_heat_flux_w_m2",
                  ED.INJURY_HEAT_FLUX_W_M2)):
        record(f"eqdamage.{k}", v, G, S,
               "API states these criteria are subject to intensive "
               "scientific debate and that the results were intended to "
               "produce a relative risk ranking")
    lo, hi = ED.STRUCTURAL_BANDS["wall construction 50-70% destroyed"]
    record("eqdamage.wall_destruction_band_low_pa", lo, G,
           "Assael & Kakosimos, Fires Explosions and Toxic Gas "
           "Dispersions, Table C3.6",
           "API's single threshold of 34.5 kPa sits at the bottom of this "
           "band, so the two sources agree: API takes the point at which "
           "damage becomes likely rather than certain")
    record("eqdamage.wall_destruction_band_high_pa", hi, G,
           "same table", "the top of the same band")


def transient_release() -> None:
    """Time-dependent release: blowdown and self-pressurisation."""
    import pipeline as PL
    import transient as TR
    from taxonomy import (ComponentSpec, Position, Primitive, Section,
                          Service, Site)
    G = "ENGINEERING_JUDGEMENT"
    S = "transient.py, mass and energy balance with CoolProp properties"
    p = TR.gas_blowdown(0.010, 100e5, 288.15, 0.006)
    record("transient.blowdown.peak_over_mean", p.constant_rate_error(),
           G, S,
           "how much a constant-rate treatment over-states a blowdown. "
           "The ratio is the same whatever the hole, because the shape "
           "of the decay is set by the vessel rather than the hole")
    record("transient.blowdown.released_kg", p.released_kg, G, S,
           "10 L at 100 bar through 6 mm, isentropic")
    p.validate()
    record("transient.coupling.screening_rate_kg_s",
           p.representative_rate(TR.RateBasis.PEAK), G, S,
           "peak-rate reduction selected by the explicit screening-envelope "
           "policy")
    record("transient.coupling.mass_equivalent_rate_kg_s",
           p.representative_rate(TR.RateBasis.MASS_EQUIVALENT_MEAN), G, S,
           "released mass divided by duration, selected by the explicit "
           "mass-equivalent policy")

    # Exact geometry match: the 6 mm blowdown hole is the 10% scenario of
    # a 60 mm GH2 vessel connection. Only that scenario receives the
    # profile; all other scenarios retain their ordinary blocking branches.
    coupling_site = Site(
        name="blowdown-coupling-reference",
        sections=[Section(id="V", inventory_kg=p.initial_mass_kg,
                          isolation_time_s=120.0, service=Service.GH2)],
        components=[ComponentSpec(
            primitive=Primitive.VESSEL, service=Service.GH2, count=1,
            tag="V-1", nominal_diameter_m=0.060, pressure_pa=100e5,
            temperature_k=288.15, position=Position(x=0.0, y=0.0),
            section_id="V")])
    coupling_cases = {"S000-10%": [
        PL.TransientCase("isentropic-blowdown", p),
    ]}
    screening = PL.run(
        coupling_site, half_extent_m=100.0, cell_size_m=50.0,
        transient_cases=coupling_cases,
        transient_policy=PL.TRANSIENT_SCREENING_ENVELOPE)
    equivalent = PL.run(
        coupling_site, half_extent_m=100.0, cell_size_m=50.0,
        transient_cases=coupling_cases,
        transient_policy=PL.TRANSIENT_MASS_EQUIVALENT)
    def scenario_ir(result):
        return sum(c.delta_ir for c in result.contributions
                   if c.loc_id == "S000-10%")
    ir_screening = scenario_ir(screening)
    ir_equivalent = scenario_ir(equivalent)
    CS = ("pipeline.py transient coupling reference: 10 L GH2 vessel at "
          "100 bar, 6 mm release, isentropic profile")
    record("transient.coupling.screening_scenario_ir_per_year",
           ir_screening, G, CS,
           "10% scenario IR contribution when dispersion, ignition and fire "
           "all use the peak profile rate")
    record("transient.coupling.mass_equivalent_scenario_ir_per_year",
           ir_equivalent, G, CS,
           "same scenario and released mass when all steady consequence "
           "models use the mass-equivalent time-mean rate")
    record("transient.coupling.screening_over_mass_equivalent_ir",
           ir_screening / ir_equivalent, G, CS,
           "policy sensitivity, not a validation error: the downstream "
           "models are steady rather than time-resolved")
    i = TR.gas_blowdown(0.010, 100e5, 288.15, 0.006, isothermal=True)
    record("transient.blowdown.isothermal_over_isentropic",
           i.released_kg / p.released_kg, G, S,
           "the band that wall heat transfer sits in; the isothermal "
           "wall holds the pressure up and releases more")

    h = TR.HIAD58
    v = TR.loss_of_vacuum(h["inventory_kg"], h["volume_m3"],
                          TR.HIAD58_HEAT_LEAK_W, h["relief_pressure_pa"],
                          0.0064, max_time_s=40000.0, dt_s=20.0)
    S2 = ("transient.py against HIAD event 58, LH2 rail tanker, "
          "Italy 1991")
    record("transient.hiad58.heat_leak_w", TR.HIAD58_HEAT_LEAK_W, G, S2,
           "back-solved from the recorded boil-off rate, "
           "0.10 kg/s x 445.6 kJ/kg, not fitted to the profile")
    record("transient.hiad58.model_released_kg", v.released_kg, G, S2,
           f"against a recorded {h['recorded_released_kg']:.0f} kg")
    record("transient.hiad58.model_duration_s", v.duration_s, G, S2,
           f"against a recorded {h['recorded_duration_s']:.0f} s")
    record("transient.hiad58.model_mean_rate_kg_s", v.mean_rate_kg_s(),
           G, S2, f"against a recorded {h['recorded_rate_kg_s']:.2f} kg/s; "
           "that the profile follows from an independently obtained heat "
           "leak is a check, not a validation")


def sensitivity_ranking() -> None:
    """Which unresolved items actually move the answer, on the reference
    site. Sensitivity is not error: an item that moves nothing here is
    unimportant to THIS component mix, not correct."""
    import sensitivity as S
    site = S.reference_site()
    results = S.run(site)
    G = "MEASURED"
    SRC = "sensitivity.py, reference site, one item at a time"
    shares = S.outcome_shares(site)
    for k, v in shares.items():
        record(f"sens.outcome_share.{k}", v, G, SRC,
               "which outcome types carry the risk here; an item that only "
               "affects an absent outcome cannot move anything, and that "
               "is a property of the site")
    for r_ in results:
        record(f"sens.{r_.key}.max_ir_ratio", r_.ratio, G, SRC, r_.question)
        record(f"sens.{r_.key}.integrated_ratio", r_.integrated_ratio,
               G, SRC,
               "integrated over the grid; the maximum alone misses an item "
               "that changes a distant contour")


def end_to_end() -> None:
    from ignition import IgnitionScheme
    import decision as dec
    import pipeline
    import uncertainty as U
    from taxonomy import (ComponentSpec, Position, Primitive, Section,
                          Service, Site)

    site = Site(
        name="reference case",
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
            ComponentSpec(primitive=Primitive.HOSE, service=Service.LH2,
                          count=2, tag="HS", nominal_diameter_m=0.05,
                          pressure_pa=6e5, temperature_k=22,
                          position=Position(x=20, y=0), section_id="TR"),
            ComponentSpec(primitive=Primitive.VALVE, service=Service.GH2,
                          count=12, tag="HV", nominal_diameter_m=0.012,
                          pressure_pa=4.5e7, temperature_k=288,
                          position=Position(x=60, y=0), section_id="HP")])

    S = "this pipeline, reference case"
    r = pipeline.run(site, half_extent_m=150, cell_size_m=25,
                     ignition_scheme=IgnitionScheme.HYRAM)
    G = r.grade.value
    record("e2e.n_scenarios", r.n_scenarios, "MEASURED", S,
           "scenarios enumerated from the component list")
    record("e2e.max_ir_point", r.max_ir, G, S,
           "engineering-screening maximum on this grid, medians throughout; "
           "not a validated facility risk")
    record("e2e.grade", r.grade.value, "MEASURED", S,
           "weakest link in the chain")
    record("e2e.coverage_fraction", r.coverage.evaluated_fraction, "MEASURED",
           S, "fraction of enumerated LOC frequency actually evaluated")

    iv = U.propagate_linear(r.contributions, n=5000)
    record("e2e.max_ir_median", iv.median, G, S,
           "median of the spatial maximum recomputed for each of 5000 "
           "frequency draws; not the sum over receptor cells")
    record("e2e.max_ir_p05", iv.p05, G, S, "5th percentile of spatial maximum")
    record("e2e.max_ir_p95", iv.p95, G, S, "95th percentile of spatial maximum")
    record("e2e.max_ir_span", iv.span, G, S,
           "frequency-only uncertainty; excludes physical-model discrepancy")
    record("e2e.supported_significant_figures", iv.significant_figures(),
           "MEASURED", S, "algorithmic precision diagnostic using frequency "
           "spread only; not evidence of experimentally supported precision")

    flame_results = {r.flame_model.value: r}
    for model in (pipeline.FlameModel.MOLKOV_FIT,
                  pipeline.FlameModel.DELICHATSIOS):
        flame_results[model.value] = pipeline.run(
            site, half_extent_m=150, cell_size_m=25,
            ignition_scheme=IgnitionScheme.HYRAM, flame_model=model)
    flame_envelope = U.flame_model_envelope(flame_results)
    for model, value in flame_envelope.max_ir_by_model.items():
        record(f"e2e.flame_model.{model}.max_ir", value,
               "PUBLISHED_UNVALIDATED", S,
               "same site and inputs with only the GH2 jet-flame model "
               "changed; an epistemic alternative, not a random draw")
    for model, value in flame_envelope.integrated_ir_by_model.items():
        record(f"e2e.flame_model.{model}.integrated_ir", value,
               "PUBLISHED_UNVALIDATED", S,
               "area-integrated risk for the separate jet-flame model form")
    record("e2e.flame_model.max_ir_span", flame_envelope.max_ir_span,
           "PUBLISHED_UNVALIDATED", S,
           "non-probabilistic max-IR envelope across Molkov conservative, "
           "Molkov best fit, and Delichatsios")

    for name, lim in [("1e-6", 1e-6), ("1e-5", 1e-5), ("1e-4", 1e-4)]:
        with_iv = dec.check_individual_risk(r.max_ir, r.coverage, lim, name,
                                            interval=iv)
        without = dec.check_individual_risk(r.max_ir, r.coverage, lim, name)
        record(f"e2e.verdict_{name}_with_interval", with_iv.verdict.value,
               "MEASURED", S, "numerical criterion comparison using the "
               "interval; facility acceptance remains withheld")
        record(f"e2e.verdict_{name}_point_only", without.verdict.value,
               "MEASURED", S,
               "numerical criterion comparison using the point estimate "
               "alone; not a compliance or facility-acceptance decision")

    a = pipeline.run(site, half_extent_m=150, cell_size_m=25,
                     ignition_scheme=IgnitionScheme.PURPLE)
    record("e2e.ignition_scheme_ratio", a.max_ir / r.max_ir,
           "PUBLISHED_UNVALIDATED", S,
           "PURPLE over HYRAM at the level of individual risk; larger than "
           "any physics model in the chain")


# --------------------------------------------------------------------------

def main() -> int:
    RESULTS.clear()
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against results.json instead of writing it")
    default_results = Path(__file__).resolve().parent.parent / "results.json"
    ap.add_argument("--path", default=str(default_results))
    args = ap.parse_args()

    for step in (purple_book_6b, red_book_104, source_terms, fire,
                 damage_figures, fireballs, cold_hydrogen, blast_wave,
                 dispersion,
                 frequencies, ignition, empirical_ignition,
                 incident_comparison, new_phenomena,
                 external_validation, gh2_validation_matrix,
                 gating_experiment, release_height,
                 equipment_damage_criteria, transient_release,
                 implementation_versus_model_choice,
                 sensitivity_ranking,
                 end_to_end):
        step()

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_results": len(RESULTS),
        "note": ("Every number claimed in a document should be read from "
                 "here rather than typed. Entries at PLACEHOLDER grade or "
                 "from a calibration are included deliberately."),
        "results": RESULTS,
    }

    if not args.check:
        with open(args.path, "w") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        print(f"wrote {args.path}: {len(RESULTS)} results")
        by_grade: dict[str, int] = {}
        for v in RESULTS.values():
            by_grade[v["grade"]] = by_grade.get(v["grade"], 0) + 1
        for g, n in sorted(by_grade.items()):
            print(f"  {g:24s} {n}")
        return 0

    try:
        with open(args.path) as f:
            old = json.load(f)["results"]
    except FileNotFoundError:
        print(f"{args.path} not found; run without --check first")
        return 2

    drift = differences(RESULTS, old)

    if drift:
        print(f"{len(drift)} differences:")
        for d in drift:
            print("  " + d)
        return 1
    print(f"no drift across {len(RESULTS)} results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
