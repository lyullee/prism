"""
Golden tests.

Every number this project has verified against a published source, plus
regressions for source-reading defects and explicit refusal boundaries.
Unresolved model choices are compared and reported rather than converted
into a passing implementation test.

Run with:  python3 -m pytest test_golden.py -v
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent

warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------
# Purple Book Appendix 6.B -- the only fully worked example in the book
# --------------------------------------------------------------------------

class TestPurpleBook6B:
    """Reproduces the sample individual-risk calculation at a grid point.

    This validates the bookkeeping -- summation, effective cloud width,
    wind sector geometry, probit conversion -- and not the hydrogen
    consequence path, because 6.B is a toxic case."""

    F_S = 5e-7
    C_AXIS = 21300.0        # mg/m3, from the book's dispersion step
    T_EXP = 30.0            # minutes
    R = 361.0
    NWS = 12

    def test_weather_probability(self):
        from risk import WeatherSector
        w = WeatherSector("D 5.0", (196.0, 225.0), p_day=0.0376,
                          p_night=0.0362)
        assert w.pm_pphi == pytest.approx(0.0368, abs=1e-4)

    def test_distance(self):
        assert math.hypot(200, 300) == pytest.approx(361, abs=1)

    def test_probit(self):
        from risk import CO_PROBIT
        assert CO_PROBIT.probit(self.C_AXIS, self.T_EXP) == pytest.approx(
            5.97, abs=0.01)

    def test_centreline_lethality(self):
        from risk import CO_PROBIT, probit_to_probability
        pr = CO_PROBIT.probit(self.C_AXIS, self.T_EXP)
        assert probit_to_probability(pr) == pytest.approx(0.835, abs=0.003)

    def test_probability_integral_and_sigma_y(self):
        """The book does not print sigma_y; it is recovered from PI = 72 m.

        Recording it gives the eventual Gaussian plume implementation
        something to hit: at 361 m, class D 5.0 m/s, z0 = 0.1 m."""
        from risk import CO_PROBIT, gaussian_lateral_pi
        pr = CO_PROBIT.probit(self.C_AXIS, self.T_EXP)
        lo, hi = 1.0, 500.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            lo, hi = ((mid, hi) if gaussian_lateral_pi(pr, mid) < 72.0
                      else (lo, mid))
        sigma_y = 0.5 * (lo + hi)
        assert sigma_y == pytest.approx(28.8, abs=0.2)
        assert gaussian_lateral_pi(pr, sigma_y) == pytest.approx(72.0, abs=0.1)

    def test_delta_ir(self):
        from risk import (CO_PROBIT, PdRoute, RiskContribution,
                          WeatherSector, effective_cloud_width,
                          probability_covered, probit_to_probability)
        pr = CO_PROBIT.probit(self.C_AXIS, self.T_EXP)
        pcl = probit_to_probability(pr)
        ecw = effective_cloud_width(72.0, pcl)
        pd = pcl * probability_covered(ecw, self.R, self.NWS)
        assert pd == pytest.approx(0.381, rel=0.01)
        w = WeatherSector("D 5.0", (196.0, 225.0), 0.0376, 0.0362)
        c = RiskContribution(
            loc_id="pipe rupture", weather_class="D 5.0",
            sector_deg=(196, 225), ignition_event=None, pm_pphi=w.pm_pphi,
            p_ignition=1.0, p_death=pd, frequency_per_year=self.F_S,
            route=PdRoute.TOXIC)
        assert c.delta_ir == pytest.approx(7.0e-9, rel=0.02)

    def test_pci_is_not_clipped(self):
        """Appendix 6.A shows the relation stays valid past Pci = 1, the
        surplus being the neighbouring sectors' contribution. Clipping
        discards real risk."""
        from risk import probability_covered
        assert probability_covered(500.0, 10.0, 12) > 1.0


# --------------------------------------------------------------------------
# Red Book 10.4 -- and the arithmetic error in it
# --------------------------------------------------------------------------

class TestRedBook104:
    PA, PB, PC, PD = 5.0e-7, 0.7, 0.7, 0.1

    def outcomes(self):
        return {
            "safe": self.PA * (1 - self.PB) * (1 - self.PC),
            "flash": self.PA * (1 - self.PB) * self.PC * (1 - self.PD),
            "uvce": self.PA * (1 - self.PB) * self.PC * self.PD,
            "bleve": self.PA * self.PB,
        }

    @pytest.mark.parametrize("key,book", [
        ("safe", 4.5e-8), ("uvce", 1.05e-8), ("bleve", 3.5e-7)])
    def test_matches_book(self, key, book):
        assert self.outcomes()[key] == pytest.approx(book, rel=0.02)

    def test_closure(self):
        """The book states this closure as the check on an event tree."""
        assert sum(self.outcomes().values()) == pytest.approx(self.PA, rel=1e-12)

    def test_book_flash_fire_is_wrong(self):
        """The book prints 9.8e-8; the value is 9.45e-8.

        Not a tolerance question: with 9.8e-8 the outcomes sum to 5.035e-7
        against an initiating frequency of 5.0e-7, so the book's own
        closure criterion rejects its own number."""
        assert self.outcomes()["flash"] == pytest.approx(9.45e-8, rel=1e-3)
        book_total = 4.5e-8 + 9.8e-8 + 1.05e-8 + 3.5e-7
        assert not math.isclose(book_total, self.PA, rel_tol=1e-6)


# --------------------------------------------------------------------------
# ignition trees
# --------------------------------------------------------------------------

class TestIgnition:
    def test_all_trees_close(self):
        """Every scheme, every release type, every band. PURPLE_SOURCES
        needs a delayed probability supplied, so it is swept over one as
        well rather than skipped."""
        from ignition import (IgnitionScheme, ReleaseType,
                              build_ignition_tree)
        n = 0
        for sch in IgnitionScheme:
            dcs = ([0.0, 0.1, 0.5, 1.0]
                   if sch is IgnitionScheme.PURPLE_SOURCES else [None])
            for dc in dcs:
                for rel in ReleaseType:
                    for mag in [0.05, 5.0, 50.0, 500.0, 5000.0, 50000.0]:
                        for pool in [False, True]:
                            if rel is ReleaseType.INSTANTANEOUS and pool:
                                continue
                            r = build_ignition_tree(
                                rel, mag, sch, forms_pool=pool,
                                delayed_conditional=dc)
                            total = sum(e.probability for e in r.events)
                            assert total == pytest.approx(1.0, abs=1e-9)
                            n += 1
        assert n == 108

    def test_purple_has_no_no_ignition_branch(self):
        """Delayed ignition for a stationary unit is (1 - direct), so a
        release always ignites eventually. Conservative, and a modelling
        convenience the book's own commentary questions."""
        from ignition import (IgnitionScheme, Outcome, ReleaseType,
                              build_ignition_tree)
        t = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                                IgnitionScheme.PURPLE)
        assert t.by_outcome(Outcome.NO_IGNITION) == 0.0

    def test_free_field_bound_is_far_above_hyram(self):
        """PURPLE is method B read without its escape clause and is kept
        as a bound, not as the recommended calculation."""
        from ignition import (IgnitionScheme, ReleaseType,
                              build_ignition_tree)
        a = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                                IgnitionScheme.PURPLE).p_ignited
        b = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                                IgnitionScheme.HYRAM).p_ignited
        assert a / b > 10.0

    def test_method_a_closes_most_of_the_gap(self):
        """Purple Book 4.7.2 method A on a quiet site lands within a
        factor of a few of the hydrogen-specific set. The fifty-fold
        divergence was mostly a misreading of the book, not a
        disagreement about hydrogen."""
        from ignition import (IgnitionScheme, ReleaseType,
                              build_ignition_tree)
        quiet = build_ignition_tree(
            ReleaseType.CONTINUOUS, 6.08, IgnitionScheme.PURPLE_SOURCES,
            delayed_conditional=0.10).p_ignited
        hyram = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                                    IgnitionScheme.HYRAM).p_ignited
        assert quiet / hyram < 5.0

    def test_method_a_requires_the_sources(self):
        """An empty source list means nobody surveyed, not that there is
        nothing to ignite the cloud."""
        from ignition import (IgnitionScheme, ReleaseType,
                              build_ignition_tree)
        with pytest.raises(ValueError):
            build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                                IgnitionScheme.PURPLE_SOURCES)

    def test_liquid_direct_ignition_is_not_halved_or_lost(self):
        from ignition import (IgnitionScheme, Outcome, ReleaseType,
                              build_ignition_tree)
        tree = build_ignition_tree(
            ReleaseType.CONTINUOUS, 0.1, IgnitionScheme.HYRAM,
            forms_pool=True)
        assert tree.by_outcome(Outcome.POOL_FIRE) == pytest.approx(
            tree.probabilities.direct)
        assert tree.by_outcome(Outcome.JET_FIRE) == 0.0

    @pytest.mark.parametrize("bad", [float("nan"), -0.1, 1.1])
    def test_invalid_bleve_probability_is_rejected(self, bad):
        from ignition import (IgnitionScheme, ReleaseType,
                              build_ignition_tree)
        with pytest.raises(ValueError, match="p_bleve"):
            build_ignition_tree(
                ReleaseType.INSTANTANEOUS, 10.0, IgnitionScheme.HYRAM,
                p_bleve=bad)

    @pytest.mark.parametrize("bad", [float("nan"), -0.1, 1.1])
    def test_invalid_delayed_probability_is_rejected(self, bad):
        from ignition import (IgnitionScheme, ReleaseType,
                              build_ignition_tree)
        with pytest.raises(ValueError, match="delayed ignition"):
            build_ignition_tree(
                ReleaseType.CONTINUOUS, 1.0,
                IgnitionScheme.PURPLE_SOURCES,
                delayed_conditional=bad)


class TestIgnitionSources:
    """Purple Book Appendix 4.A, Table 4.A.1."""

    @pytest.mark.parametrize("name,p", [
        ("flare", 1.0), ("motor vehicle", 0.4),
        ("indoor boiler", 0.23), ("pleasure craft", 0.1)])
    def test_one_minute_probability_is_recovered(self, name, p):
        """P(t) = P_present (1 - exp(-omega t)) with omega back-solved
        from the table must return the table value at 60 s."""
        import ignition_sources as IS
        s = IS.IgnitionSource(name, IS.SourceKind.POINT)
        assert s.probability(60.0) == pytest.approx(p, abs=1e-9)

    def test_probability_grows_with_exposure(self):
        import ignition_sources as IS
        s = IS.IgnitionSource("motor vehicle", IS.SourceKind.POINT)
        vals = [s.probability(t) for t in (10, 30, 60, 300)]
        assert all(a < b for a, b in zip(vals, vals[1:]))
        assert vals[-1] > 0.9

    def test_sources_out_of_reach_do_not_ignite(self):
        import ignition_sources as IS
        g = IS.IgnitionSourceSet(
            [IS.IgnitionSource("flare", IS.SourceKind.POINT, x=500)]
        ).delayed_probability(60.0, cloud_radius_m=100.0)
        assert g.value == 0.0

    def test_empty_source_list_is_refused(self):
        import ignition_sources as IS
        from gating import RefusedError
        g = IS.IgnitionSourceSet([]).delayed_probability(60.0)
        with pytest.raises(RefusedError):
            _ = g.value

    def test_method_b_has_an_escape_clause(self):
        """4.7.2 B: if the LFL contour does not leave the establishment
        and nothing there ignites it, ignition is assumed not to take
        place. The earlier implementation dropped this."""
        import ignition_sources as IS
        assert IS.free_field_delayed_probability(True).value == 1.0
        assert IS.free_field_delayed_probability(False).value == 0.0
        assert IS.free_field_delayed_probability(
            False, ignited_at_site=True).value == 1.0


# --------------------------------------------------------------------------
# source term
# --------------------------------------------------------------------------

class TestSourceTerm:
    @pytest.mark.parametrize("d_mm,p_bar,expected", [
        (3.0, 100.0, 0.0441), (6.0, 350.0, 0.5988),
        (12.0, 450.0, 3.0411), (25.0, 700.0, 19.8963)])
    def test_matches_independent_implementation(self, d_mm, p_bar, expected):
        from source_term import discharge
        r = discharge(p_bar * 1e5, 288.15, "Hydrogen", d_mm / 1000.0)
        assert r.rate_kg_s == pytest.approx(expected, rel=1e-3)

    def test_real_gas_matters_for_density_not_much_for_rate(self):
        """Z = 1.30 at 450 bar, yet the ideal-gas rate is only 5% off:
        the density error and the expansion behaviour partly cancel. Real
        gas matters for the expanded jet state, not for the rate."""
        from source_term import discharge, ideal_gas_choked
        r = discharge(4.5e7, 288.15, "Hydrogen", 0.012)
        q_ideal = ideal_gas_choked(4.5e7, 288.15, 0.012)
        assert r.z_stagnation == pytest.approx(1.30, abs=0.02)
        assert abs(q_ideal / r.rate_kg_s - 1.0) < 0.08

    def test_no_outward_flow_below_ambient(self):
        """The isentrope is scanned from ambient up to the stagnation
        pressure, so below ambient the range inverts and the scan returns
        a flow in the wrong direction. At 0.5 bar absolute it gave
        5.8e-5 kg/s outward, which is air flowing in."""
        from source_term import discharge
        for p in (5e4, 101325.0):
            assert discharge(p, 288.15, "Hydrogen", 0.006).rate_kg_s == 0.0
        assert discharge(1.2e5, 288.15, "Hydrogen", 0.006).rate_kg_s > 0

    def test_lh2_flashes_at_the_throat(self):
        from source_term import discharge
        r = discharge(6e5, None, "ParaHydrogen", 0.05, saturated_liquid=True)
        assert r.choked
        assert 0.0 < r.throat_quality < 0.2

    def test_released_mass_records_binding_constraint(self):
        from source_term import released_mass
        assert released_mass(0.06, 80.0, 30.0).limited_by == "ISOLATION"
        assert released_mass(6.08, 80.0, 30.0).limited_by == "INVENTORY"


# --------------------------------------------------------------------------
# fire
# --------------------------------------------------------------------------

class TestFire:
    def flame(self, d_mm, p_bar, model="delichatsios", conservative=True):
        import fire as F
        from source_term import discharge
        d = d_mm / 1000.0
        r = discharge(p_bar * 1e5, 288.15, "Hydrogen", d)
        rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
        nz = F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                               r.velocity_m_s, rho, d)
        return r, F.flame_length(r.rate_kg_s, nz, hole_diameter_m=d,
                                 model=model, conservative=conservative)

    def test_molkov_reproduces_the_papers_own_experiment(self):
        """A 4.76 mm nozzle at Re = 2870 reconstructs to Fr = 87,800
        against the 92,000 the paper quotes. The best fit then gives
        L/D = 101 where the measurements are 134 and 147, and the
        conservative line gives 154, bracketing them. A best fit sitting
        below the data is what a best fit does; a separation distance
        should not be taken from one."""
        import fire as F
        d, mu, rho = 4.76e-3, 8.9e-6, 0.0838
        u = 2870 * mu / (rho * d)
        mdot = rho * u * math.pi * d * d / 4.0
        assert u * u / (9.81 * d) == pytest.approx(92000, rel=0.06)
        fit = F.molkov_flame_length(mdot, d, conservative=False) / d
        cons = F.molkov_flame_length(mdot, d, conservative=True) / d
        assert fit == pytest.approx(101, rel=0.05)
        assert 134 <= cons <= 160

    def test_same_correlation_reproduces_the_other_implementation(self):
        """The distinction that matters. Running the SAME correlation as
        an independent implementation returns the same numbers to within
        1%; running a different one returns different numbers. Agreement
        with another code is routinely reported as validation and it is
        not -- it shows the two implement the same thing."""
        import numpy as np
        from hyram.phys import api
        import fire as F
        from source_term import discharge
        for d_mm, p_bar in ((6.0, 350.0), (12.0, 450.0),
                            (25.0, 700.0)):
            d = d_mm / 1000.0
            r = discharge(p_bar * 1e5, 288.15, "Hydrogen", d)
            rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
            nz = F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                                   r.velocity_m_s, rho, d)
            mine = F.flame_length(r.rate_kg_s, nz, model="delichatsios")
            f = api.Flame(
                api.Fluid(species="hydrogen", T=288.15, P=p_bar * 1e5),
                api.Orifice(d),
                api.Fluid(species="air", T=288.15, P=101325.0),
                nn_conserve_momentum=True, nn_T="solve_energy",
                verbose=False)
            f.solve()
            assert mine.length_m / float(f.length()) == pytest.approx(
                1.0, abs=0.02)
            assert mine.radiant_power_w / float(
                np.atleast_1d(f.get_srad())[0]) == pytest.approx(
                    1.0, abs=0.02)

    def test_molkov_and_delichatsios_disagree(self):
        """Not a transcription question. Molkov is hydrogen-specific and
        says Froude-only correlations are deficient for under-expanded
        jets; Delichatsios is Froude-only and is what HyRAM implements.
        Agreeing with HyRAM means having implemented the same
        correlation."""
        _, m = self.flame(12.0, 450.0, model="molkov", conservative=False)
        _, dl = self.flame(12.0, 450.0, model="delichatsios")
        assert 0.7 < m.length_m / dl.length_m < 0.85

    def test_molkov_needs_the_actual_leak_diameter(self):
        """The correlation is in terms of the real hole, not the notional
        nozzle. Silently passing the notional one would be wrong by the
        expansion ratio."""
        import fire as F
        from source_term import discharge
        r = discharge(3.5e7, 288.15, "Hydrogen", 0.006)
        rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
        nz = F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                               r.velocity_m_s, rho, 0.006)
        with pytest.raises(ValueError):
            F.flame_length(r.rate_kg_s, nz, model="molkov")

    @pytest.mark.parametrize("d_mm,p_bar,expected", [
        (3.0, 100.0, 3.82), (6.0, 350.0, 13.73),
        (12.0, 450.0, 30.65), (25.0, 700.0, 68.61)])
    def test_flame_length(self, d_mm, p_bar, expected):
        _, fl = self.flame(d_mm, p_bar)
        assert fl.length_m == pytest.approx(expected, rel=0.03)

    def test_flame_froude_uses_temperature_rise_not_jet_density_difference(self):
        """Delichatsios eq.8a and HyRAM+ eq.107 use
        (T_ad-T_amb)/T_amb. Substituting the unburned jet-to-air density
        difference put the 25 mm case on the wrong side of Fr=5 and made
        its flame 13% too long."""
        _, fl = self.flame(25.0, 700.0)
        assert fl.froude == pytest.approx(4.43, rel=0.02)
        assert fl.regime == "buoyancy"

    @pytest.mark.parametrize("d_mm,p_bar,expected_mw", [
        (3.0, 100.0, 0.26), (6.0, 350.0, 6.38), (12.0, 450.0, 46.81)])
    def test_radiant_power(self, d_mm, p_bar, expected_mw):
        _, fl = self.flame(d_mm, p_bar)
        assert fl.radiant_power_w / 1e6 == pytest.approx(expected_mw, rel=0.02)

    def test_radiant_fraction_rises_with_rate(self):
        """X_rad = 9.45e-9 (tau a_p T_ad^4)^0.47: not a constant. A constant
        0.15 was 1.69x high at one rate and would have been low at another."""
        _, small = self.flame(2.0, 50.0)
        _, large = self.flame(25.0, 700.0)
        assert small.radiant_fraction < 0.05
        assert large.radiant_fraction > 0.15

    def test_receptor_inside_the_flame_is_not_a_flux(self):
        import fire as F
        _, fl = self.flame(6.0, 350.0)
        assert F.heat_flux(fl, 1.0, 1.0, bearing_deg=0.0) == F.ENGULFED

    def test_flame_width_and_radius_are_separate(self):
        """0.17 L is the flame WIDTH. One constant serving as both width
        and radius made the exclusion zone twice its size."""
        import fire as F
        assert float(F.FLAME_RADIUS_RATIO) == pytest.approx(
            float(F.FLAME_WIDTH_RATIO) / 2.0)

    def test_hankinson_weighting(self):
        """Equation 15 with n = 0.75N: linear rise to a peak three
        quarters along, linear fall to w1 at the tip."""
        import fire as F
        for n in (15, 20, 40):
            w = F.weights_hankinson(n)
            assert sum(w) == pytest.approx(1.0, abs=1e-12)
            peak = max(range(n), key=lambda i: w[i])
            assert 0.68 <= (peak + 0.5) / n <= 0.78
            assert w[0] < w[peak] and w[-1] < w[peak]

    def test_35kw_contour_can_lie_inside_the_flame(self):
        """For hydrogen the flux just past the tip is already below
        35 kW/m2 in small releases, so that contour does not exist
        outside the flame and None is the answer."""
        import fire as F
        _, small = self.flame(2.0, 50.0)
        assert F.distance_to_flux(small, 35e3, bearing_deg=0.0) is None
        _, mid = self.flame(6.0, 350.0)
        d = F.distance_to_flux(mid, 35e3, bearing_deg=0.0)
        assert d is not None and d == pytest.approx(14.0, rel=0.05)

    def test_absorption_coefficient_read_from_the_correlations_own_paper(self):
        """Molina Table 2 gives 0.23 1/m for the hydrogen flames the
        correlation was fitted to. A correlation and the coefficient it
        was fitted against travel together, so that is the value used."""
        import fire as F
        assert float(F.A_P_MOLINA_H2) == 0.23

    def test_independent_route_gives_a_different_absorption_coefficient(self):
        """Chmielewski & Gieras from HITEMP gives 0.126, a factor of 1.8
        below Molina's RADCAL value. Their paper reports HITEMP and RADCAL
        diverging for several species, so this is a disagreement between
        databases rather than a transcription error. A calibrated 177 had
        stood here, which was neither."""
        import fire as F
        assert F.planck_mean_absorption() == pytest.approx(0.126, abs=0.005)
        assert 1.5 < float(F.A_P_MOLINA_H2) / F.planck_mean_absorption() < 2.2

    def test_releases_modelled_here_sit_below_molinas_fitted_range(self):
        """Molina's data spans about 5e13 to 1e16 on tau a_p T_ad^4.
        These releases land near 1e12, so the correlation is being
        extrapolated below its whole range whichever form is used."""
        import fire as F
        _, fl = self.flame(6.0, 350.0)
        from source_term import discharge
        r = discharge(3.5e7, 288.15, "Hydrogen", 0.006)
        tau = F.residence_time(r.rate_kg_s, fl.length_m)
        group = tau * float(F.A_P_MOLINA_H2) * float(F.T_ADIABATIC_H2) ** 4
        assert group < 5e13

    def test_log_form_is_out_of_range_here(self):
        """The same paper is cited as a power law and as a logarithm. With
        a_p computed rather than calibrated, the group lands near 5e11,
        where the logarithm has already gone negative. Returning zero is
        the honest report of a correlation evaluated outside its range;
        scaling it back up would be a second guess on top of the first."""
        import fire as F
        from source_term import discharge
        r = discharge(4.5e7, 288.15, "Hydrogen", 0.012)
        _, fl = self.flame(12.0, 450.0)
        assert F.radiant_fraction(r.rate_kg_s, fl.length_m,
                                  form="power") > 0.1
        assert F.radiant_fraction(r.rate_kg_s, fl.length_m,
                                  form="log") == 0.0

    def test_direction_changes_the_answer_by_an_order_of_magnitude(self):
        """The Purple Book event tree does not treat discharge direction."""
        import fire as F
        _, fl = self.flame(6.0, 350.0)
        head_on = F.heat_flux(fl, 15.0, 1.0, bearing_deg=0.0)
        across = F.heat_flux(fl, 15.0, 1.0, bearing_deg=90.0)
        assert head_on / across > 5.0

    def test_dpe_converges_to_the_multipoint_model_far_away(self):
        """Both degenerate to a point source in the far field. Near in
        they do not, and that is the whole reason for the DPE model:
        Hankinson & Lowesmith find it the only one of six that works at
        both ranges without adjusting the fraction of heat radiated."""
        import dpe
        import fire as F
        _, fl = self.flame(6.0, 350.0, model="molkov")
        near = (dpe.dpe_heat_flux(fl, 3.0, bearing_deg=90.0)
                / F.heat_flux(fl, 3.0, 1.0, bearing_deg=90.0))
        far = (dpe.dpe_heat_flux(fl, 100.0, bearing_deg=90.0)
               / F.heat_flux(fl, 100.0, 1.0, bearing_deg=90.0))
        assert near > 1.2
        assert far == pytest.approx(1.0, abs=0.03)

    def test_dpe_surface_weights_are_area_fractions(self):
        import dpe
        _, fl = self.flame(6.0, 350.0, model="molkov")
        s = dpe.ellipsoid_surface(fl.length_m)
        assert s.weights.sum() == pytest.approx(1.0, abs=1e-9)
        assert len(s.points) > 100

    def test_flux_falls_monotonically(self):
        import fire as F
        _, fl = self.flame(6.0, 350.0)
        xs = [5.0, 10.0, 20.0, 40.0, 80.0]
        q = [F.heat_flux(fl, x, 1.0, orientation="VERTICAL") for x in xs]
        assert all(a > b for a, b in zip(q, q[1:]))


# --------------------------------------------------------------------------
# dispersion
# --------------------------------------------------------------------------

class TestGH2Jet:
    def result(self, d_mm, p_bar):
        import gh2_jet as G
        from source_term import discharge
        d = d_mm / 1000.0
        r = discharge(p_bar * 1e5, 288.15, "Hydrogen", d)
        rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
        return G.dispersion(r.rate_kg_s, 5.0,
                            throat_pressure_pa=r.throat_pressure_pa,
                            throat_velocity_m_s=r.velocity_m_s,
                            throat_density_kg_m3=rho, hole_diameter_m=d)

    def test_flammable_cloud_is_longer_than_the_flame(self):
        """The coherence check that selected the mass-fraction form. A
        flame burns inside the flammable envelope and cannot outrun it."""
        import fire as F
        from source_term import discharge
        for d_mm, p_bar in [(3.0, 100.0), (6.0, 350.0), (12.0, 450.0)]:
            d = d_mm / 1000.0
            r = discharge(p_bar * 1e5, 288.15, "Hydrogen", d)
            rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
            nz = F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                                   r.velocity_m_s, rho, d)
            # Checked against every flame model, because the coherence
            # argument is what selected the mass-fraction decay form and
            # it has to survive a change of flame correlation.
            for model, cons in (("molkov", True), ("molkov", False),
                                ("delichatsios", True)):
                fl = F.flame_length(r.rate_kg_s, nz, hole_diameter_m=d,
                                    model=model, conservative=cons)
                lfl = self.result(d_mm, p_bar).lfl_distance_m.value
                assert lfl > fl.length_m

    def test_equation_10_is_radial_spreading_not_mole_decay(self):
        """Schefer eq.10 defines L_1/2, the radial location where mass
        fraction is half its centreline value. It is not a second
        centreline decay equation for mole fraction. Its far-field slope
        agrees with the Gaussian radial profile in eq.11."""
        import gh2_jet as G
        expected_slope = math.sqrt(math.log(2.0) / float(G.RADIAL_DECAY))
        assert float(G.C2_HALF_RADIUS) == pytest.approx(
            expected_slope, rel=0.06)

    def test_equations_10_and_11_close_in_the_far_field(self):
        import fire as F
        import gh2_jet as G
        rho_h2 = F.P_AMB * F.M_H2 / (F.R_U * F.T_AMB)
        nozzle = F.NotionalNozzle(
            diameter_m=0.00191, velocity_m_s=134.0,
            density_kg_m3=rho_h2, temperature_k=F.T_AMB,
            expansion_ratio=1.0)
        x = 1000.0 * nozzle.diameter_m
        radius = G.mass_fraction_half_radius(x, nozzle)
        ratio = (G.radial_mass_fraction(x, radius, nozzle)
                 / G.centreline_mass_fraction(x, nozzle))
        # Independent fits: C2=0.103 +/-0.01 and the eq.11 Gaussian
        # implies 0.108. Their 5% difference is inside C2's uncertainty.
        assert ratio == pytest.approx(0.5, rel=0.06)

    def test_mixture_density_closes_at_pure_components(self):
        import fire as F
        import gh2_jet as G
        rho_air = F.P_AMB * F.M_AIR / (F.R_U * F.T_AMB)
        rho_h2 = F.P_AMB * F.M_H2 / (F.R_U * F.T_AMB)
        assert G.mixture_density_kg_m3(0.0) == pytest.approx(rho_air)
        assert G.mixture_density_kg_m3(1.0) == pytest.approx(rho_h2)

    def test_flammable_mass_uses_local_mixture_density(self):
        result = self.result(6.0, 350.0)
        assert result.flammable_mass_kg.value == pytest.approx(
            0.66560, rel=2e-4)
        # The former ambient-density approximation was 0.71375 kg.
        assert result.flammable_mass_kg.value < 0.71375

    def test_high_pressure_jets_are_always_momentum_dominated(self):
        """So the buoyancy gate never fires in this scope. Kept because a
        low-pressure vent or a boil-off release would trip it."""
        for d_mm, p_bar in [(1.0, 10.0), (25.0, 700.0)]:
            assert self.result(d_mm, p_bar).status == "VALID"


class TestGH2ValidationMatrix:
    def test_matrix_separates_identified_data_from_numeric_benchmarks(self):
        import validation_matrix as V
        statuses = {row.status for row in V.EVIDENCE}
        assert "DATASET_IDENTIFIED" in statuses
        assert any(status.startswith("NUMERIC_") for status in statuses)
        assert "KNOWN_MODEL_LIMIT" in statuses

    def test_design_cases_expose_joint_validation_gap(self):
        import validation_matrix as V
        assert all(V.dispersion_joint_coverage(*case) != "JOINT_LFL_RANGE"
                   for case in V.DESIGN_CASES)
        flame = [V.flame_joint_coverage(*case) for case in V.DESIGN_CASES]
        assert flame.count("PROUST_JOINT_RANGE") == 1
        assert flame.count("ROYLE_DIAMETER_ONLY_PRESSURE_OUTSIDE") == 1
        assert flame.count("EKOTO_DIAMETER_ONLY_PRESSURE_OUTSIDE") == 1
        assert flame.count("AXES_ONLY_NO_JOINT_POINT") == 1

    def test_published_ekoto_ratios_are_conservative(self):
        import validation_matrix as V
        assert all(value > 1.0 for value in V.ekoto_hyram_ratios().values())


class TestValidationMetrics:
    def test_metrics_are_exact_for_a_small_known_set(self):
        import validation_metrics as V
        rows = [
            V.Observation("a", "length", 10.0, 12.0, "m", model_low=9.0,
                          model_high=13.0),
            V.Observation("b", "length", 20.0, 18.0, "m", model_low=15.0,
                          model_high=19.0),
        ]
        result = V.metrics(rows)
        assert result.mean_bias == pytest.approx(0.0)
        assert result.mae == pytest.approx(2.0)
        assert result.rmse == pytest.approx(2.0)
        assert result.fraction_within_factor_two == 1.0
        assert result.model_envelope_coverage == 0.5

    def test_observation_csv_rejects_half_an_envelope(self, tmp_path):
        import validation_metrics as V
        path = tmp_path / "observations.csv"
        path.write_text(
            ",".join(V.COLUMNS) + "\n"
            "A,length,10,11,m,1,8,,source,note\n",
            encoding="utf-8")
        with pytest.raises(ValueError, match="both model_low and model_high"):
            V.read_observations(path)

    def test_zero_prediction_counts_as_outside_factor_two(self):
        import validation_metrics as V
        rows = [
            V.Observation("zero", "length", 10.0, 0.0, "m"),
            V.Observation("good", "length", 10.0, 10.0, "m"),
        ]
        result = V.metrics(rows)
        assert result.fraction_within_factor_two == 0.5
        assert result.geometric_mean_bias == 0.0

    @pytest.mark.parametrize("problem", ["duplicate", "mixed-unit"])
    def test_observation_csv_rejects_ambiguous_rows(self, tmp_path, problem):
        import validation_metrics as V
        second = (
            "A,length,12,11,m,1,8,13,source,note\n"
            if problem == "duplicate"
            else "B,length,12,11,ft,1,8,13,source,note\n"
        )
        path = tmp_path / "observations.csv"
        path.write_text(
            ",".join(V.COLUMNS) + "\n"
            "A,length,10,11,m,1,8,13,source,note\n" + second,
            encoding="utf-8")
        with pytest.raises(ValueError):
            V.read_observations(path)


class TestFireball:
    """Makarov et al. (2021), reproduced against the experiments in it."""

    def test_gh2_hemispherical_matches_the_papers_values(self):
        import fireball as FB
        # Tamura 1.367 kg: paper's theoretical value 10.9-11.0 m
        f = FB.gh2_tank_rupture_fireball(1.367, conservative=False)
        assert f.size_m == pytest.approx(10.95, abs=0.15)
        # Shen 3.9 kg released instantaneously: paper says 15.4 m
        g = FB.gh2_tank_rupture_fireball(3.9, conservative=False)
        assert g.size_m == pytest.approx(15.4, abs=0.1)

    def test_conservative_matches_the_calibration_experiment(self):
        """Equation 8 is calibrated to the 24 m under-vehicle fireball."""
        import fireball as FB
        assert FB.gh2_tank_rupture_fireball(1.87).size_m == pytest.approx(
            24.0, abs=0.1)

    def test_pancake_shape_recovers_the_measured_sizes(self):
        """The paper explains the large measured fireballs by flattening:
        24 m at 1.87 kg needs D/H = 22.6, and 18 m at 1.367 kg needs 12."""
        import fireball as FB
        a = FB.gh2_tank_rupture_fireball(1.87, width_to_height=22.6)
        b = FB.gh2_tank_rupture_fireball(1.367, width_to_height=12.0)
        assert a.size_m == pytest.approx(24.0, rel=0.03)
        assert b.size_m == pytest.approx(18.0, rel=0.05)

    def test_lh2_conservative_sits_above_the_best_fit(self):
        """Equation 12 raises equation 11's coefficient from 8.16 to 10 so
        that no Zabetakis point is under-predicted, the binding one being
        stated as 10.37 m from 1.06 kg.

        With the published coefficient this gives 10.27 at 1.06 kg, 1%
        below the quoted 10.37. Table 2 was not visible in the retrieved
        text, so the mass at that point cannot be confirmed and the
        published coefficient is kept rather than adjusted to close a 1%
        gap against a number that may pair with a different mass."""
        import fireball as FB
        cons = FB.lh2_spill_fireball(1.06).size_m
        best = FB.lh2_spill_fireball(1.06, False).size_m
        assert cons > best
        assert cons == pytest.approx(10.37, rel=0.02)
        assert cons / best == pytest.approx(10.0 / 8.16, rel=1e-6)

    def test_lh2_scales_differently_from_tank_rupture(self):
        """0.45 against 1/3: an LH2 spill burns subsonically and buoyancy
        shapes it, so the even three-dimensional expansion behind the
        one-third scaling does not hold."""
        import fireball as FB
        small = (FB.lh2_spill_fireball(1.0).size_m
                 / FB.gh2_tank_rupture_fireball(1.0).size_m)
        large = (FB.lh2_spill_fireball(1000.0).size_m
                 / FB.gh2_tank_rupture_fireball(1000.0).size_m)
        assert large > small

    def test_extrapolation_beyond_zabetakis_is_flagged(self):
        """Fitted over 0.2 to 6.3 kg. A storage tank is three orders
        beyond, and that is declared rather than clipped."""
        import fireball as FB
        from taxonomy import Grade
        assert not FB.lh2_spill_fireball(2.0).extrapolated
        big = FB.lh2_spill_fireball(5000.0)
        assert big.extrapolated
        assert big.provenance.grade is Grade.PUBLISHED_UNVALIDATED

    def test_hydrocarbon_correlation_is_far_too_small(self):
        """Yellow Book r = 3.24 m^0.325 against the hydrogen correlations.
        The paper states hydrocarbon fireball correlations do not apply to
        hydrogen; at storage scale the error is a factor of three to four
        in the unsafe direction."""
        import fireball as FB
        yb = 2 * 3.24 * 5000.0 ** 0.325
        assert FB.gh2_tank_rupture_fireball(5000.0).size_m / yb > 3.0
        assert FB.lh2_spill_fireball(5000.0).size_m / yb > 4.0

    def test_absorption_coefficient_third_independent_route(self):
        """Yan et al. via Makarov gives 0.220 at 2390 K, against Molina's
        0.23. Two routes within 5% settles the constant; the factor of
        thirty in the radiant fraction chain is elsewhere."""
        import fireball as FB
        import fire as F
        assert FB.planck_absorption_yan() == pytest.approx(0.220, abs=0.005)
        assert FB.planck_absorption_yan() == pytest.approx(
            float(F.A_P_MOLINA_H2), rel=0.06)


class TestBlast:
    """Molkov & Kashkarov (2015), against the paper's worked examples."""

    def test_stand_alone_tank_energies(self):
        import blast as B
        b = B.tank_rupture_blast(72.4e-3, 34.3e6, 300.15)
        assert b.mass_kg == pytest.approx(1.654, abs=0.002)
        assert b.mechanical_energy_j / 1e6 == pytest.approx(5.23, rel=0.01)
        assert b.chemical_energy_j / 1e6 == pytest.approx(198.0, rel=0.01)
        assert b.products_radius_m == pytest.approx(5.88, abs=0.02)
        assert b.vessel_radius_m == pytest.approx(0.26, abs=0.005)

    def test_refuelling_station_tank(self):
        import blast as B
        c = B.tank_rupture_blast(10.0, 100e6, 300.15)
        assert c.mass_kg == pytest.approx(505.5, rel=0.02)
        assert c.mechanical_energy_j / 1e9 == pytest.approx(1.566, rel=0.02)
        assert c.products_radius_m == pytest.approx(39.6, rel=0.01)

    def test_starting_shock_solved_not_read_off_a_chart(self):
        """The paper reads P_st from a log-log figure and gets 52 and 110.
        Solving the shock-tube relation numerically gives 50.9 and 114,
        within the width of a chart line."""
        import blast as B
        assert B.starting_shock(34.3e6, 300.15) == pytest.approx(52, rel=0.05)
        assert B.starting_shock(100e6, 300.15) == pytest.approx(110, rel=0.05)

    def test_real_gas_matters_for_stored_energy(self):
        """Ideal gas over-states the mass by 18% at 34.3 MPa. Unlike the
        discharge rate, where the errors partly cancelled, here it goes
        straight into the blast energy."""
        import blast as B
        real = B.hydrogen_mass_abel_noble(72.4e-3, 34.3e6, 300.15)
        ideal = 34.3e6 * 72.4e-3 / ((8.314 / 2.016e-3) * 300.15)
        assert ideal / real == pytest.approx(1.18, rel=0.03)

    def test_combustion_dominates_under_a_vehicle(self):
        """Thirty times the mechanical energy that reaches the blast,
        because most of the mechanical energy went into throwing the
        vehicle 22 m. The prevailing view had been that combustion cannot
        contribute at all."""
        import blast as B
        stand = B.tank_rupture_blast(72.4e-3, 34.3e6, 300.15)
        under = B.tank_rupture_blast(88e-3, 31.8e6, 306.15,
                                     under_vehicle=True)
        assert 1.0 < stand.chemical_to_mechanical < 2.0
        assert under.chemical_to_mechanical > 20.0

    def test_chemical_term_saturates_at_the_products_radius(self):
        """It grows with the swept volume and stops once the shock passes
        r_b, which is what reproduces the measured pressure plateau."""
        import blast as B
        b = B.tank_rupture_blast(88e-3, 31.8e6, 306.15, under_vehicle=True)
        rb = b.products_radius_m
        assert b.scaled_energy(rb * 0.5) < b.scaled_energy(rb)
        assert b.scaled_energy(rb * 2) == pytest.approx(
            b.scaled_energy(rb), rel=1e-12)

    def test_decay_uses_the_anchors_the_book_prints(self):
        """This assertion has been rewritten. It previously required the
        decay to be refused outright, because the Baker charts and Yellow
        Book Figure 5.8 are both figures that select a curve by strength
        class.

        Purple Book equations 4.5 and 4.6 give TWO POINTS on the class 10
        curve in closed form, and a power law through them is determined.
        So the decay is answered between the anchors, flagged outside
        them, and refused beyond a factor of three either way, where a
        two-point fit carries no information about curvature."""
        import blast as B
        from gating import RefusedError
        b = B.tank_rupture_blast(72.4e-3, 34.3e6)
        assert not b.overpressure(10.0).refused
        with pytest.raises(RefusedError):
            b.overpressure(1000.0).value

    def test_pressure_impulse_needs_both(self):
        """The reason this module exists. Purple Book 5.2.4 has only the
        peak, which is why it excludes detonation."""
        import blast as B
        t = [x for x in B.HUMAN_PI if x.name.startswith("eardrum rupture")][0]
        assert t.exceeded(40e3, 60.0)
        assert not t.exceeded(40e3, 10.0)       # high peak, no impulse
        assert not t.exceeded(20e3, 60.0)       # impulse, low peak

    def test_worst_effect_orders_by_severity(self):
        import blast as B
        assert B.worst_human_effect(1.0e3, 0.5) is None
        assert B.worst_human_effect(2.0e3, 5.0) is not None
        severe = B.worst_human_effect(200e3, 5000.0)
        assert "translation" in severe

    def test_lung_haemorrhage_interpolation(self):
        import blast as B
        assert B.fatality_probability(50e3) == 0.0
        assert B.fatality_probability(100e3) == pytest.approx(0.01)
        assert B.fatality_probability(140e3) == pytest.approx(0.50)
        assert B.fatality_probability(200e3) == pytest.approx(0.99, abs=0.02)


class TestSiteIO:
    SECTIONS = ("section_id,service,inventory_kg,isolation_time_s\n"
                "TK,LH2,5000,1800\nHP,GH2,120,15\n")
    COMPONENTS = (
        "tag,primitive,service,count,diameter_mm,pressure_barg,"
        "temperature_k,orientation,x_m,y_m,z_m,section_id\n"
        "TK-101,VESSEL,LH2,1,50,5,22,HORIZONTAL,0,0,0,TK\n"
        "HV-301,VALVE,GH2,12,12,450,288,HORIZONTAL,80,0,0,HP\n")

    def test_round_trip(self):
        import siteio
        site = siteio.load_site("t", self.SECTIONS, self.COMPONENTS)
        assert len(site.sections) == 2
        assert len(site.components) == 2
        v = [c for c in site.components if c.primitive.value == "VESSEL"][0]
        assert v.nominal_diameter_m == pytest.approx(0.05)
        assert v.pressure_pa == pytest.approx(5e5 + 101325.0)

    def test_optional_release_azimuth_reaches_component(self):
        import siteio
        text = self.COMPONENTS.replace(
            "orientation,x_m", "orientation,release_azimuth_deg,x_m")
        text = text.replace("HORIZONTAL,", "HORIZONTAL,90,")
        site = siteio.load_site("t", self.SECTIONS, text)
        assert all(c.release_azimuth_deg == 90.0 for c in site.components)

    def test_release_azimuth_range_is_checked(self):
        import siteio
        text = self.COMPONENTS.replace(
            "orientation,x_m", "orientation,release_azimuth_deg,x_m")
        text = text.replace("HORIZONTAL,", "HORIZONTAL,360,")
        with pytest.raises(siteio.SheetErrors, match="less than 360"):
            siteio.load_site("t", self.SECTIONS, text)

    def test_gauge_pressure_is_converted(self):
        """The column says barg. Reading it as Pa would be out by 100,000
        and nothing in a spreadsheet would complain."""
        import siteio
        site = siteio.load_site("t", self.SECTIONS, self.COMPONENTS)
        hp = [c for c in site.components if c.service.value == "GH2"][0]
        assert hp.pressure_pa == pytest.approx(450e5 + 101325.0)

    def test_zero_gauge_pressure_is_valid(self):
        import siteio
        text = self.COMPONENTS.replace(",50,5,22,", ",50,0,22,")
        site = siteio.load_site("t", self.SECTIONS, text)
        assert site.components[0].pressure_pa == pytest.approx(101325.0)

    @pytest.mark.parametrize("replacement,reason", [
        (",LH2,1.5,50,", "whole number"),
        (",LH2,nan,50,", "finite"),
    ])
    def test_component_count_must_be_a_finite_integer(
            self, replacement, reason):
        import siteio
        text = self.COMPONENTS.replace(",LH2,1,50,", replacement)
        with pytest.raises(siteio.SheetErrors, match=reason):
            siteio.load_site("t", self.SECTIONS, text)

    def test_errors_are_collected_with_row_and_reason(self):
        import siteio
        bad = self.COMPONENTS.replace("VESSEL", "VESEL").replace(
            ",50,5,22,HORIZONTAL", ",abc,5,22,HORIZONTAL")
        with pytest.raises(siteio.SheetErrors) as ei:
            siteio.load_site("t", self.SECTIONS, bad)
        errs = ei.value.errors
        assert len(errs) >= 2
        assert all(e.row >= 2 for e in errs)
        assert any("VESEL" in str(e) for e in errs)

    def test_unknown_section_is_rejected_with_the_reason(self):
        import siteio
        bad = self.COMPONENTS.replace(",TK\n", ",NOSUCH\n")
        with pytest.raises(siteio.SheetErrors) as ei:
            siteio.load_site("t", self.SECTIONS, bad)
        assert any("no section with this id" in str(e)
                   for e in ei.value.errors)

    def test_csv_text_is_not_mistaken_for_a_path(self):
        """Passing a sheet to Path().exists() raises 'file name too long',
        which says nothing useful."""
        import siteio
        assert len(siteio.read_rows(self.SECTIONS)) == 2
        with pytest.raises(FileNotFoundError):
            siteio.read_rows("no_such_file.csv")

    def test_templates_cover_every_column(self):
        import siteio
        for sheet, cols in [("sections", siteio.SECTION_COLUMNS),
                            ("components", siteio.COMPONENT_COLUMNS),
                            ("assemblies", siteio.ASSEMBLY_COLUMNS)]:
            head = siteio.template(sheet).splitlines()[0]
            assert head.split(",") == cols

    def test_equipment_tags_are_nonempty_and_unique(self):
        import siteio
        blank = self.COMPONENTS.replace("TK-101,VESSEL", ",VESSEL")
        with pytest.raises(siteio.SheetErrors, match="must not be empty"):
            siteio.load_site("t", self.SECTIONS, blank)
        duplicate = self.COMPONENTS.replace("HV-301,VALVE", "TK-101,VALVE")
        with pytest.raises(siteio.SheetErrors, match="duplicated"):
            siteio.load_site("t", self.SECTIONS, duplicate)

class TestExport:
    @staticmethod
    @pytest.fixture(scope="class")
    def result():
        from ignition import IgnitionScheme
        import pipeline
        import siteio
        site = siteio.load_site("t", TestSiteIO.SECTIONS,
                                TestSiteIO.COMPONENTS)
        return pipeline.run(site, half_extent_m=400, cell_size_m=50,
                            ignition_scheme=IgnitionScheme.HYRAM)

    def test_geojson_is_plain_json(self, result):
        """numpy scalars serialise by luck, not by contract."""
        import json
        import export
        gj = export.ir_geojson(result, 126.978, 37.567)
        json.dumps(gj)
        c = gj["features"][0]["geometry"]["coordinates"][0]
        assert all(type(v) is float for v in c)

    def test_contours_carry_the_grade_and_coverage(self, result):
        """A GeoJSON handed on loses every caveat unless they are in it."""
        import export
        gj = export.ir_geojson(result)
        for f in gj["features"]:
            p = f["properties"]
            assert p["grade"]
            assert "coverage_complete" in p
            assert "individual_risk_per_year" in p

    def test_contour_levels_are_nested(self, result):
        """A higher risk contour must lie inside a lower one."""
        import export
        cs = export.contours(result.grid)
        if len(cs) < 2:
            pytest.skip("only one level present")
        radii = {}
        for lv, lines in cs.items():
            radii[lv] = max(math.hypot(px, py)
                            for line in lines for px, py in line)
        ordered = sorted(radii)
        for a, b in zip(ordered, ordered[1:]):
            assert radii[a] >= radii[b]

    def test_export_bundle_has_the_caveats(self, result):
        import decision as dec
        import export
        import uncertainty as U
        iv = U.propagate_linear(result.contributions, n=500)
        out = export.export(result, interval=iv,
                            report=dec.build_report(result, interval=iv))
        assert out["uncertainty"]["not_propagated"]
        assert out["summary"]["flame_model"] == "molkov-conservative"
        assert "LOWER BOUND" in out["summary"]["coverage_statement"] or \
               out["summary"]["coverage_fraction"] == 1.0
        assert out["decision"]["verdict"]


class TestCLI:
    def test_ignition_scheme_has_no_default(self):
        """It moves the answer by fifty. Defaulting it would hide the
        single largest choice in the system."""
        import qra
        with pytest.raises(SystemExit):
            qra.main(["run", "--name", "t", "--sections", "x.csv"])

    def test_bad_input_exits_two_not_traceback(self, tmp_path):
        import qra
        s = tmp_path / "s.csv"
        s.write_text("section_id,service,inventory_kg,isolation_time_s\n"
                     "TK,NOTAFUEL,5000,1800\n")
        code = qra.main(["run", "--name", "t", "--sections", str(s),
                         "--ignition", "hyram", "--samples", "0",
                         "--out", str(tmp_path / "o.json")])
        assert code == 2


class TestSensitivity:
    """Which unresolved items move the answer, and which perturbations
    never happened."""

    @pytest.fixture(scope="class")
    @staticmethod
    def results():
        import sensitivity as S
        return S.run(S.reference_site())

    def test_every_perturbation_is_exercised(self, results):
        """A clean ratio of 1.00 is ambiguous: the item may not matter, or
        the path may never have run. Three perturbations here failed
        silently at first -- one patched a constant that was already bound
        as a default argument, one changed a label where both branches
        route to the same physics, and one was masked by a memoised
        dispersion result. All three read as insensitivity."""
        untouched = [r.key for r in results if r.untouched]
        assert untouched == [], (
            f"these perturbations moved nothing on any metric and are "
            f"probably not being applied: {untouched}")

    def test_the_dominant_items_are_frequency_not_physics(self, results):
        """The risk here is dominated by flash fire, so flame length and
        radiant fraction cannot move it whatever their state.

        This assertion has been rewritten once. It previously required
        the joint anomaly and the vacuum-jacketed release probability to
        dominate, and they did -- because the relief release was being
        computed at the line bore and as saturated liquid, sixty-one times
        the one recorded rate.
        Fixing that dropped both to about 0.95 and raised the cryogenic
        pump, which is what two independent published QRAs say dominates.
        A sensitivity ranking is a property of the model as well as of
        the site, and it moves when the model is corrected."""
        by = {r.key: r for r in results}

        def dev(key):
            return max(by[key].ratio, 1.0 / max(by[key].ratio, 1e-12))

        assert dev("ignition_scheme") > 10.0
        assert dev("pump_seal_frequency") > 1.2
        assert dev("molina_residual") < 1.2
        assert dev("lh2_fireball_branch") < 1.2

    def test_joint_result_is_not_an_artefact_of_the_perturbation(self):
        """A first version dropped the full-bore bin by 36,700 and
        reported a sixfold effect. Shrinking the perturbation to 76,
        which is the actual size of the anomaly, gives 0.18 against 0.17:
        the response has saturated, so the result is the anomaly and not
        the perturbation."""
        import taxonomy as T
        j = T.FREQUENCY_LIBRARY[(T.Primitive.JOINT, T.Fuel.LH2)]
        # published as rising with leak size, which nothing else does
        assert j.medians[4] > j.medians[0]
        for p in (T.Primitive.VALVE, T.Primitive.FLANGE, T.Primitive.PIPE):
            e = T.FREQUENCY_LIBRARY[(p, T.Fuel.LH2)]
            assert e.medians[4] < e.medians[0]

    def test_one_metric_is_not_enough(self, results):
        """The LH2 safety factor cuts the contour area by a third while
        barely touching the maximum. Reporting only the maximum would
        have called it insensitive."""
        by = {r.key: r for r in results}
        sf = by["lfl_safety_factor"]
        assert sf.area_ratio < 0.8
        assert sf.area_ratio < sf.ratio


class TestInvariants:
    """Properties that must hold whatever the inputs, checked because a
    result can be wrong without any individual model being wrong."""

    def test_choked_flow_scales_with_area(self):
        from source_term import discharge
        a = discharge(4.5e7, 288.15, "Hydrogen", 0.006).rate_kg_s
        b = discharge(4.5e7, 288.15, "Hydrogen", 0.012).rate_kg_s
        assert b / a == pytest.approx(4.0, rel=0.01)

    def test_fireball_exponents(self):
        import fireball as FB
        r = (FB.gh2_tank_rupture_fireball(1000.0).size_m
             / FB.gh2_tank_rupture_fireball(1.0).size_m)
        assert math.log(r) / math.log(1000) == pytest.approx(1 / 3, abs=1e-9)
        r2 = (FB.lh2_spill_fireball(1000.0).size_m
              / FB.lh2_spill_fireball(1.0).size_m)
        assert math.log(r2) / math.log(1000) == pytest.approx(0.45, abs=1e-9)

    def test_far_field_radiation_is_inverse_square(self):
        import fire as F
        from source_term import discharge
        r = discharge(3.5e7, 288.15, "Hydrogen", 0.006)
        rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
        fl = F.flame_length(
            r.rate_kg_s,
            F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                              r.velocity_m_s, rho, 0.006),
            hole_diameter_m=0.006, model="molkov")
        a = F.heat_flux(fl, 200.0, 1.0, orientation="VERTICAL")
        b = F.heat_flux(fl, 400.0, 1.0, orientation="VERTICAL")
        assert 3.5 < a / b < 4.5

    def test_pipeline_is_deterministic(self):
        import dispersion_cache as dc
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        site = S.reference_site()
        a = pipeline.run(site, half_extent_m=200, cell_size_m=100,
                         ignition_scheme=IgnitionScheme.HYRAM).max_ir
        dc.clear()
        b = pipeline.run(site, half_extent_m=200, cell_size_m=100,
                         ignition_scheme=IgnitionScheme.HYRAM).max_ir
        assert a == b

    def test_grid_extent_does_not_change_the_maximum(self):
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        site = S.reference_site()
        a = pipeline.run(site, half_extent_m=200, cell_size_m=100,
                         ignition_scheme=IgnitionScheme.HYRAM).max_ir
        b = pipeline.run(site, half_extent_m=600, cell_size_m=100,
                         ignition_scheme=IgnitionScheme.HYRAM).max_ir
        assert a == pytest.approx(b, rel=1e-9)

    def test_contributions_sum_to_the_grid(self):
        import numpy as np
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        r = pipeline.run(S.reference_site(), half_extent_m=200,
                         cell_size_m=100,
                         ignition_scheme=IgnitionScheme.HYRAM)
        s = sum(c.delta_ir for c in r.contributions)
        assert s == pytest.approx(float(np.asarray(r.grid.values).sum()),
                                  rel=1e-9)

    def test_grid_values_are_finite_and_non_negative(self):
        import numpy as np
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        g = np.asarray(pipeline.run(
            S.reference_site(), half_extent_m=200, cell_size_m=100,
            ignition_scheme=IgnitionScheme.HYRAM).grid.values)
        assert np.isfinite(g).all()
        assert (g >= 0).all()

    def test_area_integral_is_resolution_independent(self):
        """The maximum is not: it rises about 12% from 25 m cells to
        12.5 m and settles there. A bare cell sum is worse still, moving
        three orders across the same range because it scales with the
        number of cells. Multiplying by cell area gives a quantity that
        holds within 15% from 200 m down to 6.25 m."""
        import export
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        site = S.reference_site()
        vals = []
        for c in (200.0, 50.0, 25.0):
            r = pipeline.run(site, half_extent_m=300, cell_size_m=c,
                             ignition_scheme=IgnitionScheme.HYRAM)
            vals.append(export.risk_integral(r))
        assert max(vals) / min(vals) < 1.2

    def test_no_dead_damage_mapping_remains(self):
        """_damage_at was the pre-vectorisation scalar mapping. It had no
        caller and sent BLEVE to the jet flame branch, so a fireball
        would have been evaluated as radiation from a flame. Dead code
        that is also wrong is worse than dead code."""
        import pipeline
        assert not hasattr(pipeline, "_damage_at")


class TestBlocking:
    """Purple Book 4.4.1, and the monotonicity it has to produce."""

    def test_defaults_match_the_book(self):
        import blocking as BL
        a = BL.BLOCKING_DEFAULTS[BL.BlockingSystem.AUTOMATIC]
        assert a.closing_time_s == 120.0
        assert a.failure_on_demand == 0.001
        assert BL.BLOCKING_DEFAULTS[
            BL.BlockingSystem.REMOTE].closing_time_s == 600.0
        assert BL.BLOCKING_DEFAULTS[
            BL.BlockingSystem.HAND].closing_time_s == 1800.0

    def test_thirty_seconds_was_faster_than_the_book_allows(self):
        """The old default. The book's fastest grade, a fully automatic
        system needing no operator action, closes in 120 s."""
        import blocking as BL
        assert BL.BLOCKING_DEFAULTS[
            BL.BlockingSystem.AUTOMATIC].closing_time_s > 30.0

    def test_weather_probabilities_close(self):
        """Every hour of the year falls in exactly one class and one
        sector. The default set used 0.0368 per sector, which is the
        Appendix 6.B value for ONE class and ONE sector, and twelve of
        those sum to 0.4416 — so every result was under-counted by 2.26."""
        import pipeline
        w = pipeline.rotterdam_like()
        total = sum(s.pm_pphi for c in w for s in c.sectors)
        assert total == pytest.approx(1.0, abs=1e-12)

    def test_a_weather_set_that_does_not_close_raises(self):
        import pipeline
        bad = [pipeline.Weather(
            label="x", wind_m_s=5.0, stability="D",
            sectors=[pipeline.WeatherSector("x", (0, 180), 0.1, 0.1)])]
        with pytest.raises(ValueError):
            pipeline.check_weather_closes(bad)

    def test_weather_units_are_checked(self):
        import pipeline
        sector = [pipeline.WeatherSector("x", (0, 360), 0.5, 0.5)]
        with pytest.raises(ValueError, match="humidity"):
            pipeline.check_weather_closes([
                pipeline.Weather("x", 5.0, "D", sector,
                                 relative_humidity=1.5e2)])
        with pytest.raises(ValueError, match="wind"):
            pipeline.check_weather_closes([
                pipeline.Weather("x", 0.0, "D", sector)])

    @pytest.mark.parametrize("kwargs", [
        {"half_extent_m": 0.0},
        {"cell_size_m": 0.0},
        {"half_extent_m": 10.0, "cell_size_m": 25.0},
        {"population_per_cell": -1.0},
        {"isolation_s": 0.0},
    ])
    def test_pipeline_rejects_invalid_numerical_inputs(self, kwargs):
        import pipeline
        import sensitivity as S
        with pytest.raises(ValueError):
            pipeline.run(S.reference_site(), **kwargs)

    def test_flammable_averaging_is_capped(self):
        """SLAB averages concentration over the window it is given, so a
        longer release dilutes the reported value through meander. Right
        for a toxic dose, wrong for a flammable cloud, which ignites at
        its momentary extent — 4.7.2 B asks for the MAXIMUM footprint.

        Uncapped, a site with no blocking system came out 3% safer than
        one with an automatic system, monotonically."""
        import slabx_adapter as SX
        assert SX.FLAMMABLE_AVERAGING_S <= 30.0

    def test_slabx_humidity_default_is_percent(self):
        """The SLAB Atmosphere API takes percent, whereas the fire models
        take a fraction. A default of 0.5 here meant 0.5%, not 50%."""
        import inspect
        import slabx_adapter as SX
        default = inspect.signature(SX.dispersion).parameters[
            "relative_humidity"].default
        assert default == 50.0

    def test_blocking_affects_duration_dependent_outcomes(self):
        """Isolation reduces the duration-dependent area integral. A BLEVE
        is an instantaneous vessel rupture and therefore cannot be credited
        to a downstream valve; its contribution must remain unchanged."""
        import blocking as BL
        import export
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        site = S.reference_site()
        out = {}
        for k in (BL.BlockingSystem.AUTOMATIC, BL.BlockingSystem.NONE):
            r = pipeline.run(site, half_extent_m=300, cell_size_m=50,
                             ignition_scheme=IgnitionScheme.HYRAM,
                             blocking=k)
            bleve = sum(c.delta_ir for c in r.contributions
                        if c.ignition_event == "BLEVE")
            out[k] = (export.risk_integral(r), bleve)
        assert out[BL.BlockingSystem.NONE][0] > \
            out[BL.BlockingSystem.AUTOMATIC][0]
        assert out[BL.BlockingSystem.NONE][1] == pytest.approx(
            out[BL.BlockingSystem.AUTOMATIC][1])

    def test_worse_blocking_never_lowers_the_risk(self):
        """It did, by a factor of four, and three separate defects had to
        be found to fix it.

        The dispersion duration was taken as the isolation time, so with
        no blocking system infinity was passed to a model that averages
        concentration over that window; the LFL distance collapsed from
        62 m to 7 m and removing the safety system made the site safer.
        The released mass was also read before it was assigned. Finally,
        averaging blocking-branch mass before nonlinear consequences did
        not represent either event-tree branch."""
        import blocking as BL
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        site = S.reference_site()
        order = [BL.BlockingSystem.AUTOMATIC, BL.BlockingSystem.REMOTE,
                 BL.BlockingSystem.HAND, BL.BlockingSystem.NONE]
        irs = [pipeline.run(site, half_extent_m=300, cell_size_m=50,
                            ignition_scheme=IgnitionScheme.HYRAM,
                            blocking=k).max_ir for k in order]
        # Directional footprint subsampling changes the summation order
        # between event-tree branches. Treat roundoff at about 1e-15
        # relative as equality; the failed comparison differed by 6e-20/yr.
        assert all(a <= b + max(1e-18, abs(b) * 1e-12)
                   for a, b in zip(irs, irs[1:])), irs

    def test_dispersion_duration_is_bounded(self):
        """An unbounded isolation time is not an unbounded release."""
        import pipeline
        assert pipeline.DISPERSION_MAX_S <= 3600.0

    def test_hyram_isolation_factor_is_not_also_applied(self):
        """HyRAM removes the outcome with a 0.9; the Purple Book shortens
        the release. Applying both credits the same valves twice."""
        import blocking as BL
        assert "twice" in BL.DOUBLE_COUNTING_WARNING


class TestHIAD:
    """Empirical conditional ignition rates, HIAD 2.2, 1,142 events."""

    def test_lh2_ignites_about_half_as_often_as_gh2(self):
        """The finding that survives the reporting bias, because whatever
        bias applies to one phase applies to the other. Neither ignition
        scheme in use represents it: both are indexed on release rate
        alone."""
        import hiad
        assert hiad.LH2.rate == pytest.approx(0.355, abs=0.01)
        assert hiad.GH2.rate == pytest.approx(0.790, abs=0.01)
        assert hiad.lh2_over_gh2() < 0.55
        assert hiad.lh2_over_gh2(high_quality=True) < 0.75

    def test_rate_rises_with_quality_grade(self):
        """Evidence of reporting bias, and the reason the LH2 figure is
        carried as a range rather than a point. Better documented events
        are more often ignited ones."""
        import hiad
        rates = [hiad.LH2_BY_QUALITY[q].rate for q in (2, 3, 4, 5)]
        assert rates[0] < rates[-1]
        lo, hi = hiad.lh2_range()
        assert lo == pytest.approx(0.288, abs=0.01)
        assert hi == pytest.approx(0.636, abs=0.01)

    def test_free_field_bound_is_not_supported(self):
        """The Purple Book branch that takes ignition as certain reaches
        1.000 only by dropping the escape clause the book gives. The
        largest recorded unignited LH2 release is 145 tonnes."""
        import hiad
        assert hiad.LH2.rate < 0.5
        assert max(m for m, _ in hiad.RELEASES_THAT_DID_NOT_IGNITE) > 100_000

    def test_vent_paths_are_well_represented(self):
        """Vent stacks were added to the taxonomy after a retrospective
        check found the Emeryville incident unenumerable. HIAD has 142
        vent and relief events, 59 of them liquid hydrogen."""
        import hiad
        assert hiad.VENT_RELATED.n > 100
        assert hiad.VENT_RELATED_LH2.n > 40

    def test_schemes_are_compared_not_corrected(self):
        """The obvious move is to scale a scheme by the recorded
        LH2-to-GH2 ratio. It is not done: the recorded figures are
        conditional on a release being REPORTED and a scheme's
        probability on a release OCCURRING, and a single ratio would
        assume the rate dependence is the same in both phases."""
        import hiad
        assert "not done" in hiad.WHY_NOT_A_CORRECTION
        c = hiad.check_scheme("HYRAM", 0.35, "LH2")
        assert c.within_recorded_range
        assert hiad.check_scheme("PURPLE", 1.0, "LH2").within_recorded_range \
            is False
        assert hiad.check_scheme("HYRAM", 0.012, "LH2") \
            .within_recorded_range is False

    def test_every_scheme_sits_outside_the_recorded_range_somewhere(self):
        """HyRAM's largest band lands inside it and its smaller bands are
        an order below; the free field bound is above it everywhere. No
        scheme in use matches the record across its whole range."""
        from ignition import (IgnitionScheme, ReleaseType,
                              build_ignition_tree)
        import hiad
        small = build_ignition_tree(ReleaseType.CONTINUOUS, 0.06,
                                    IgnitionScheme.HYRAM).p_ignited
        large = build_ignition_tree(ReleaseType.CONTINUOUS, 60.0,
                                    IgnitionScheme.HYRAM).p_ignited
        assert not hiad.check_scheme("h", small, "LH2").within_recorded_range
        assert hiad.check_scheme("h", large, "LH2").within_recorded_range
        purple = build_ignition_tree(ReleaseType.CONTINUOUS, 6.08,
                                     IgnitionScheme.PURPLE).p_ignited
        assert hiad.check_scheme("p", purple, "LH2").scheme_probability > \
            hiad.lh2_range()[1]

    def test_comparison_travels_with_the_result(self):
        """A caveat delivered separately is a caveat lost."""
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        r = pipeline.run(S.reference_site(), half_extent_m=200,
                         cell_size_m=100,
                         ignition_scheme=IgnitionScheme.HYRAM)
        assert r.ignition_checks
        assert any(not c.within_recorded_range for c in r.ignition_checks)

    def test_it_is_not_a_frequency(self):
        import hiad
        assert "an ignition frequency" in hiad.HIAD_PROV.not_claimable_as
        from taxonomy import Grade
        assert hiad.HIAD_PROV.grade is Grade.MEASURED


class TestSpillFire:
    """An ignited LH2 spill is not a hydrocarbon pool fire."""

    def test_measured_radiative_fraction(self):
        import spill_fire as SF
        assert float(SF.XRAD_SPILL_LOW) == 0.06
        assert float(SF.XRAD_SPILL_HIGH) == 0.12

    def test_hydrogen_sep_is_an_order_below_hydrocarbon(self):
        """7 to 15 kW/m2 measured at large scale against 100 to 286 for a
        hydrocarbon pool. The Yellow Book has no hydrogen entry, so the
        substitution is easy to make and wrong by ten to twenty times."""
        import spill_fire as SF
        assert SF.SEP_HYDROCARBON_POOL / float(SF.SEP_H2_HIGH) > 6.0

    def test_geometry_is_not_modelled(self):
        import spill_fire as SF
        assert "not modelled" in SF.WHY_NOT_A_POOL_FIRE

    def test_secondary_explosion_does_not_contradict_air_condensation(self):
        """HSL saw air condense on the cold GROUND; the project's own
        result is about air leaving the gas phase INSIDE the cloud. Both
        hold."""
        import spill_fire as SF
        assert "Different place" in SF.SECONDARY_EXPLOSION_NOTE
        assert "is not a frequency" in SF.SECONDARY_EXPLOSION_NOTE

    def test_pool_branch_is_reachable_in_the_pipeline(self):
        """The ignition tree only reaches it when forms_pool is set, and
        the pipeline was not setting it, so the model was unreachable for
        the service it was written for."""
        import collections
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        r = pipeline.run(S.reference_site(), half_extent_m=300,
                         cell_size_m=50,
                         ignition_scheme=IgnitionScheme.HYRAM)
        kinds = collections.Counter(c.ignition_event
                                    for c in r.contributions)
        assert kinds.get("POOL_FIRE", 0) > 0


class TestFragments:
    def test_range_scales_with_energy(self):
        import fragments as FR
        a = FR.fragment_throw(1e8, 5000.0)
        b = FR.fragment_throw(1e9, 5000.0)
        assert b.range_high_m > a.range_high_m

    def test_drag_matters(self):
        """Without drag the range is v^2 sin(2t)/g, which for a light
        fragment at high speed is wrong by a large factor -- exactly the
        case a thin cryogenic outer shell produces."""
        import fragments as FR
        with_drag = FR.ballistic_range(150.0, 100.0, 1.5, 45.0, drag=True)
        without = FR.ballistic_range(150.0, 100.0, 1.5, 45.0, drag=False)
        assert without > with_drag * 1.5

    def test_lethality_is_refused(self):
        """Range is modelled; lethality needs a hit probability and an
        angular distribution, and the Purple Book gives no fragment
        lethality relation."""
        import fragments as FR
        from gating import RefusedError
        t = FR.fragment_throw(1e8, 5000.0)
        with pytest.raises(RefusedError):
            FR.lethality(50.0, t).value

    def test_pipeline_reports_a_throw_for_vessel_rupture(self):
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        r = pipeline.run(S.reference_site(), half_extent_m=300,
                         cell_size_m=50,
                         ignition_scheme=IgnitionScheme.HYRAM)
        assert r.fragment_throws
        assert r.fragment_throws[0].range_high_m > 10.0


class TestBlastDecay:
    def test_anchors_are_reproduced(self):
        """The power law is determined by Purple Book equations 4.5 and
        4.6, which give 0.3 barg at a scaled distance of 1.5 and 0.1 barg
        at 3.0. It has to return those."""
        import blast as B
        a, b = float(B.DECAY_A), float(B.DECAY_B)
        assert a * 1.5 ** -b * B.P_AMB == pytest.approx(0.30e5, rel=0.01)
        assert a * 3.0 ** -b * B.P_AMB == pytest.approx(0.10e5, rel=0.01)

    def test_exponent_is_between_the_asymptotes(self):
        """Not imposed: it falls out of the two anchors, and it lands
        between the near-field and far-field behaviour of an ideal blast
        wave. That is a check, not a derivation."""
        import blast as B
        assert 1.0 < float(B.DECAY_B) < 3.0

    def test_far_extrapolation_is_refused(self):
        """A two-point fit says nothing about curvature."""
        import blast as B
        from gating import RefusedError
        b = B.tank_rupture_blast(72.4e-3, 34.3e6)
        near = b.overpressure(10.0)
        assert not near.refused
        with pytest.raises(RefusedError):
            b.overpressure(500.0).value

    def test_distance_to_overpressure_inverts(self):
        import blast as B
        b = B.tank_rupture_blast(72.4e-3, 34.3e6)
        d = b.distance_to_overpressure(0.10e5)
        assert d is not None
        assert b.overpressure(d)._value == pytest.approx(0.10e5, rel=0.02)

    def test_against_published_hazard_distances(self):
        """Kashkarov, Li & Molkov (ICHS 2019) publish hazard distances
        from the same methodology and the same coefficients. Within the
        checked range this reproduces them to about 10%."""
        import blast as B
        b = B.tank_rupture_blast(0.300, 1000e5, 293.15)
        for pa, ref in ((100e3, 7.0), (23e3, 19.3), (16.5e3, 24.0),
                        (4.8e3, 59.3)):
            d = b.distance_to_overpressure(pa)
            assert d is not None
            assert 0.95 <= d / ref <= 1.15, (pa, d, ref)

    def test_far_field_is_refused_because_it_was_wrong(self):
        """Their 1.35 kPa evacuation perimeter is 145 m and a single
        exponent gives 109, which is 25% low on a safety distance. The
        local exponent in their own points falls from 1.83 to 1.36, and
        one exponent cannot follow that, so the far field is refused."""
        import blast as B
        b = B.tank_rupture_blast(0.300, 1000e5, 293.15)
        assert b.distance_to_overpressure(1.35e3) is None

    def test_inverse_search_distinguishes_refusal_from_zero(self):
        """A first version treated a refusal as zero overpressure, so the
        search stopped at the near edge of the valid range and returned
        60 m where the answer was outside the range entirely."""
        import blast as B
        b = B.tank_rupture_blast(0.300, 1000e5, 293.15)
        near, far = b.valid_distance_range()
        assert near < far
        assert not b.overpressure(near).refused
        assert not b.overpressure(far).refused


class TestIndoor:
    def test_criterion_actually_fires(self):
        """A first version used a Richardson number on the hole diameter
        and came out near 1e-7 for every case, because a small hole gives
        a fast jet whatever the leak rate. Every enclosure came back well
        mixed and the criterion was useless."""
        import indoor as IN
        room = IN.Enclosure(500.0, 100.0, 5.0)
        small = IN.accumulate(1e-6, room, 0.0005)
        large = IN.accumulate(1e-2, room, 0.010)
        assert small.regime is IN.MixingRegime.STRATIFIED
        assert large.regime is IN.MixingRegime.WELL_MIXED

    def test_morton_length_ordering(self):
        import indoor as IN
        assert (IN.morton_length(1e-2, 0.010)
                > IN.morton_length(1e-5, 0.001))

    def test_ventilation_suppresses_the_layer(self):
        import indoor as IN
        no_vent = IN.accumulate(1e-5, IN.Enclosure(500.0, 100.0, 5.0, 0.0),
                                0.001)
        vented = IN.accumulate(1e-5, IN.Enclosure(500.0, 100.0, 5.0, 2.0),
                               0.001)
        assert no_vent.layer_depth_m.value > vented.layer_depth_m.value

    def test_layer_depth_needs_a_time(self):
        """A depth without a duration means nothing: the layer deepens
        for as long as the leak runs."""
        import indoor as IN
        room = IN.Enclosure(500.0, 100.0, 5.0)
        a = IN.accumulate(1e-5, room, 0.001, duration_s=600.0)
        b = IN.accumulate(1e-5, room, 0.001, duration_s=3600.0)
        assert b.layer_depth_m.value > a.layer_depth_m.value

    def test_confined_explosion_is_refused(self):
        import indoor as IN
        from gating import RefusedError
        r = IN.accumulate(1e-3, IN.Enclosure(500.0, 100.0, 5.0), 0.005)
        with pytest.raises(RefusedError):
            IN.confined_explosion(r).value

    def test_outdoor_models_do_not_transfer(self):
        import indoor as IN
        assert "buoyancy" in IN.WHY_OUTDOOR_MODELS_FAIL_INDOORS


class TestOperatingConditions:
    """Conditions must reach the source term.

    They did not for most of this project's life: `_source` hardcoded
    6 barg for liquid and 450 barg for gas whatever the spreadsheet said,
    and `Scenario` did not carry pressure or temperature at all. On the
    reference site those were coincidentally the right numbers, which is
    why it went unnoticed."""

    def test_scenario_carries_conditions(self):
        import taxonomy as T
        assert "pressure_pa" in T.Scenario.model_fields
        assert "temperature_k" in T.Scenario.model_fields

    def test_conditions_reach_the_discharge(self):
        import taxonomy as T
        site = T.Site(
            name="c",
            sections=[T.Section(id="A", inventory_kg=100,
                                isolation_time_s=120,
                                service=T.Service.GH2)],
            components=[
                T.ComponentSpec(primitive=T.Primitive.VALVE,
                                service=T.Service.GH2, tag="LOW",
                                nominal_diameter_m=0.012,
                                pressure_pa=20e5 + 101325,
                                temperature_k=250.0,
                                position=T.Position(x=0, y=0),
                                section_id="A"),
                T.ComponentSpec(primitive=T.Primitive.VALVE,
                                service=T.Service.GH2, tag="HIGH",
                                nominal_diameter_m=0.012,
                                pressure_pa=450e5 + 101325,
                                temperature_k=288.15,
                                position=T.Position(x=0, y=0),
                                section_id="A")])
        sc = {s.tag: s for s in T.enumerate_scenarios(site)
              if s.bin_label == "100%"}
        assert sc["LOW"].pressure_pa < sc["HIGH"].pressure_pa
        assert sc["LOW"].temperature_k == 250.0

    def test_a_low_pressure_component_gives_a_low_rate(self):
        """The vaporizer on the first real drawing runs at 20 barg and
        was being computed at 450, twenty times too large."""
        import pipeline
        import taxonomy as T
        site = T.Site(
            name="c",
            sections=[T.Section(id="A", inventory_kg=100,
                                isolation_time_s=120,
                                service=T.Service.GH2)],
            components=[T.ComponentSpec(
                primitive=T.Primitive.VALVE, service=T.Service.GH2,
                tag="V", nominal_diameter_m=0.012,
                pressure_pa=20e5 + 101325, temperature_k=250.0,
                position=T.Position(x=0, y=0), section_id="A")])
        sc = [s for s in T.enumerate_scenarios(site)
              if s.bin_label == "100%"][0]
        d, _ = pipeline._source(sc, 120.0)
        assert d.rate_kg_s < 0.5

    def test_orientation_reaches_the_radiation_field(self):
        """A jet pointing up does not put its flame across the ground.
        The orientation was carried on the scenario and never used."""
        import copy
        from ignition import IgnitionScheme
        import pipeline
        import sensitivity as S
        import taxonomy as T
        site = S.reference_site()
        up = copy.deepcopy(site)
        for c in up.components:
            c.orientation = T.Orientation.UP
        a = pipeline.run(site, half_extent_m=300, cell_size_m=50,
                         ignition_scheme=IgnitionScheme.HYRAM).max_ir
        b = pipeline.run(up, half_extent_m=300, cell_size_m=50,
                         ignition_scheme=IgnitionScheme.HYRAM).max_ir
        assert a != b


class TestUnquantifiedCoverage:
    """A scenario with no frequency at all must still be visible.

    The guard required the frequency to be finite before recording it,
    which is backwards: a component with no published frequency has an
    INFINITE one in the library, so the branch never fired. Coverage read
    100% on a site whose ambient vaporizer was never evaluated."""

    def test_no_frequency_is_recorded_not_dropped(self):
        from ignition import IgnitionScheme
        import pipeline
        import taxonomy as T
        site = T.Site(
            name="v",
            sections=[T.Section(id="A", inventory_kg=100,
                                isolation_time_s=120,
                                service=T.Service.GH2)],
            components=[T.ComponentSpec(
                primitive=T.Primitive.VAPORIZER, service=T.Service.GH2,
                tag="VAP", nominal_diameter_m=0.05,
                pressure_pa=20e5 + 101325, temperature_k=250.0,
                position=T.Position(x=0, y=0), section_id="A")])
        r = pipeline.run(site, half_extent_m=100, cell_size_m=50,
                         ignition_scheme=IgnitionScheme.HYRAM)
        assert r.coverage.unquantified
        assert not r.coverage.complete
        assert "NO frequency at all" in r.coverage.statement()

    def test_statement_names_the_component(self):
        from gating import Coverage
        c = Coverage()
        c.record_evaluated(1e-3)
        c.record_unquantified("S012-100%", "VAP-1101")
        assert not c.complete
        assert "VAP-1101" in c.statement()


class TestGatingExperiment:
    """What refusing is worth, measured rather than asserted."""

    def test_force_policy_exists_and_is_labelled(self):
        from gating import Gated, RefusePolicy, RefusedError
        g = Gated.refuse("x", "outside premise", forced_value=42.0)
        assert g.resolve(RefusePolicy.EXCLUDE) is None
        assert g.resolve(RefusePolicy.FORCE) == 42.0
        h = Gated.refuse("y", "never computed")
        with pytest.raises(RefusedError):
            h.resolve(RefusePolicy.FORCE)

    def test_premise_verdict_does_not_depend_on_truncation(self):
        """The check took the maximum rise-to-advection ratio over the
        WHOLE trajectory, which runs thousands of metres past x_max. The
        ratio is near zero where the cold cloud is dense and grows only
        far downwind, so the verdict depended on how far the integration
        happened to run: nothing failed at x_max 300 and everything did
        at 2000, for the same physical case."""
        import dispersion_cache as dc
        import slabx_adapter as SX
        verdicts = []
        for xm, nps in ((300.0, 40), (1000.0, 120)):
            dc.clear()
            r = SX.dispersion(3.0, 1.5, duration_s=600.0, stability="F",
                              liquid_fraction=0.0, x_max=xm,
                              n_puff_steps=nps)
            verdicts.append(r.status)
        assert len(set(verdicts)) == 1, verdicts

    def test_the_gate_actually_fires_somewhere(self):
        """A gate that never fires is not a gate. It fires for SMALL
        releases in NEAR-STILL air, where there is too little advection
        to compete with the rise -- the opposite of the large-release
        case first assumed."""
        import dispersion_cache as dc
        import slabx_adapter as SX
        dc.clear()
        r = SX.dispersion(0.1, 0.3, duration_s=600.0, stability="F",
                          liquid_fraction=0.0)
        assert r.status == "OUT_OF_SCOPE"
        assert r.lfl_distance_m.refused

    def test_forcing_is_not_conservative(self):
        """The result of the experiment. Forcing an answer outside the
        premise gives a SHORTER flammable distance than the model's own
        premise edge, so refusing protects against under-prediction
        rather than costing conservatism."""
        import gating_experiment as GE
        cs = GE.probe_quantities()
        lfl = [c for c in cs if c.quantity == "lfl_distance_m"]
        assert lfl, "the gate did not fire at the probe condition"
        c = lfl[0]
        assert c.forced is not None and c.bound is not None
        assert c.forced < c.bound


class TestReleaseHeight:
    """Height was accepted on every component and used nowhere."""

    def test_source_height_reduces_ground_level_flux(self):
        """A flame on a stack radiates less to the ground than one at
        ground level. EIGA lists vent stacks first among the points a
        safety distance is measured from, precisely because of height."""
        import fire as F
        from source_term import discharge
        r = discharge(3e5, 250.0, "Hydrogen", 0.05)
        rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
        nz = F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                               r.velocity_m_s, rho, 0.05)
        fl = F.flame_length(r.rate_kg_s, nz, hole_diameter_m=0.05,
                            model="molkov")
        ground = F.distance_to_flux(fl, 4e3, orientation="VERTICAL",
                                    source_height_m=0.0)
        raised = F.distance_to_flux(fl, 4e3, orientation="VERTICAL",
                                    source_height_m=6.0)
        assert ground is not None
        assert raised is None or raised < ground

    def test_dispersion_is_keyed_on_height(self):
        """An elevated vent and a ground-level leak at the same rate
        shared a cache slot, so whichever computed first decided both."""
        import dispersion_cache as dc
        a = dc.key_of(1.0, 5.0, "D", 15.0, 50.0, 300.0, 0.5)
        b = dc.key_of(1.0, 5.0, "D", 15.0, 50.0, 300.0, 8.0)
        assert a != b

    def test_release_height_changes_the_lfl_extent(self):
        import dispersion_cache as dc
        import slabx_adapter as SX
        dc.clear()
        low = SX.dispersion(0.4, 1.5, duration_s=600.0, stability="F",
                            height_m=0.5).lfl_distance_m
        dc.clear()
        high = SX.dispersion(0.4, 1.5, duration_s=600.0, stability="F",
                             height_m=10.0).lfl_distance_m
        assert not low.refused and not high.refused
        assert low._value != high._value

    def test_upward_vent_puts_no_flammable_cloud_on_the_ground(self):
        """The Schefer correlation is a free jet and knows nothing about
        the ground. For an upward vent the envelope runs from the outlet
        upward, and once the momentum decays the hydrogen is buoyant and
        keeps rising. Jet fire radiation still applies."""
        import taxonomy as T
        from ignition import IgnitionScheme
        import pipeline
        import siteio
        base = (HERE / "site_a19101" / "assemblies.csv").read_text()
        out = {}
        for z in (0, 8):
            asm = base.replace(",10,25,8,VENT_HDR", f",10,25,{z},VENT_HDR")
            site = siteio.load_site(
                "A", (HERE / "site_a19101" / "sections.csv").read_text(),
                (HERE / "site_a19101" / "components.csv").read_text(), asm)
            vid = {s.scenario_id for s in T.enumerate_scenarios(site)
                   if "VENT" in s.tag}
            r = pipeline.run(site, half_extent_m=400, cell_size_m=50,
                             ignition_scheme=IgnitionScheme.HYRAM)
            out[z] = sum(x.delta_ir for x in r.contributions
                         if x.loc_id in vid)
        assert out[8] < out[0]
        assert out[8] == 0.0, (
            "an elevated upward vent must put NO flammable cloud on the "
            "ground; a first version assigned the zeroed footprint to a "
            "local nothing read afterwards")


class TestEquipmentDamage:
    """API RP 581 5.8.2.3 thresholds, read from the document."""

    def test_api581_thresholds(self):
        import equipment_damage as ED
        assert ED.DAMAGE_OVERPRESSURE_PA == 34.5e3
        assert ED.DAMAGE_HEAT_FLUX_W_M2 == 37.8e3
        assert ED.INJURY_OVERPRESSURE_PA == 20.7e3
        assert ED.INJURY_HEAT_FLUX_W_M2 == 12.6e3

    def test_api_sits_at_the_bottom_of_the_structural_band(self):
        """Assael & Kakosimos Table C3.6 puts wall destruction at 35 to
        80 kPa. API's 34.5 kPa is at the bottom of that band, so the two
        are consistent: API takes the point at which damage becomes
        likely rather than certain."""
        import equipment_damage as ED
        lo, hi = ED.STRUCTURAL_BANDS["wall construction 50-70% destroyed"]
        assert lo <= ED.DAMAGE_OVERPRESSURE_PA * 1.05
        assert ED.DAMAGE_OVERPRESSURE_PA < hi

    def test_three_states_not_a_probability(self):
        """Thresholds do not give a probability, and a band does not give
        a curve. Fitting one would invent its shape."""
        import equipment_damage as ED
        from taxonomy import Primitive, Service
        cases = [(45e3, 0.0, ED.DamageVerdict.AFFECTED),
                 (20e3, 0.0, ED.DamageVerdict.POTENTIALLY_AFFECTED),
                 (5e3, 0.0, ED.DamageVerdict.NOT_AFFECTED),
                 (0.0, 40e3, ED.DamageVerdict.AFFECTED),
                 (0.0, 25e3, ED.DamageVerdict.POTENTIALLY_AFFECTED)]
        for q, p, want in cases:
            e = ED.Exposure(heat_flux_w_m2=q, overpressure_pa=p,
                            distance_m=30.0)
            got = ED.assess("S", "T", e, Primitive.COMPRESSOR,
                            Service.GH2).verdict
            assert got is want, (q, p, got)

    def test_cryogenic_targets_are_not_evaluated(self):
        """A vacuum-jacketed vessel loses its vacuum to thermal shock
        long before it ruptures from overpressure, and no published
        threshold gives the flux or duration at which that happens. HIAD
        1224 records the crack; nothing records the criterion."""
        import equipment_damage as ED
        from taxonomy import Primitive, Service
        e = ED.Exposure(heat_flux_w_m2=200e3, overpressure_pa=200e3,
                        distance_m=5.0)
        a = ED.assess("S", "T", e, Primitive.PIPE, Service.LH2)
        assert a.verdict is ED.DamageVerdict.NOT_EVALUATED

    def test_it_is_not_claimable_as_a_fragility_curve(self):
        import equipment_damage as ED
        assert "a fragility curve" in ED.DAMAGE_PROV.not_claimable_as
        assert "applicable to cryogenic equipment" in \
            ED.DAMAGE_PROV.not_claimable_as


class TestEscalation:
    """One step, no edge probabilities."""

    def test_graph_has_no_edge_probabilities(self):
        """A second step needs P(target releases | damaged), which does
        not exist for hydrogen equipment. A multi-step graph built on an
        invented one would compound the invention at every hop."""
        import equipment_damage as ED
        assert "does not exist" in ED.WHY_ONE_STEP
        e = ED.Exposure(heat_flux_w_m2=45e3, distance_m=10.0)
        from taxonomy import Primitive, Service
        a = ED.assess("S", "T", e, Primitive.COMPRESSOR, Service.GH2)
        assert not hasattr(a, "probability")

    def test_pipeline_builds_a_graph_on_the_real_facility(self):
        from ignition import IgnitionScheme
        import pipeline
        import siteio
        site = siteio.load_site(
            "A", (HERE / "site_a19101" / "sections.csv").read_text(),
            (HERE / "site_a19101" / "components.csv").read_text(),
            (HERE / "site_a19101" / "assemblies.csv").read_text())
        r = pipeline.run(site, half_extent_m=400, cell_size_m=100,
                         ignition_scheme=IgnitionScheme.HYRAM)
        assert r.escalation is not None
        assert r.escalation.edges
        assert r.escalation.not_evaluated, (
            "every LH2 target should come back NOT_EVALUATED")
        assert r.escalation.most_exposed()


class TestTransient:
    """Time-dependent release."""

    def test_blowdown_conserves_mass(self):
        import CoolProp.CoolProp as CP
        import transient as TR
        m0 = CP.PropsSI("D", "P", 100e5, "T", 288.15, "Hydrogen") * 0.010
        for d_mm in (3.0, 12.0):
            p = TR.gas_blowdown(0.010, 100e5, 288.15, d_mm / 1000.0)
            assert p.released_kg <= m0 + 1e-9
            assert p.released_kg > 0.9 * m0

    def test_constant_rate_overstates_the_release(self):
        """A vessel emptying through a hole loses pressure as it empties.
        Taking the initial rate for the whole release over-states it by a
        factor that is the same whatever the hole, because the shape of
        the decay is set by the vessel rather than the hole."""
        import transient as TR
        ratios = [TR.gas_blowdown(0.010, 100e5, 288.15,
                                  d / 1000.0).constant_rate_error()
                  for d in (3.0, 12.0)]
        assert all(r > 3.0 for r in ratios)
        assert max(ratios) / min(ratios) < 1.1

    def test_duration_scales_inversely_with_hole_area(self):
        import transient as TR
        a = TR.gas_blowdown(0.010, 100e5, 288.15, 0.006).duration_s
        b = TR.gas_blowdown(0.010, 100e5, 288.15, 0.012).duration_s
        assert a / b == pytest.approx(4.0, rel=0.15)

    def test_isothermal_releases_more_than_isentropic(self):
        """Wall heat transfer is not modelled, so the two branches bound
        it. The isentropic gas cools as it expands and its pressure falls
        faster, so it releases LESS; the isothermal wall keeps the
        pressure up and it releases more, over a longer time.

        A first version of this asserted the isothermal case would be
        SHORTER, which is backwards: holding the pressure up keeps the
        flow going."""
        import transient as TR
        s = TR.gas_blowdown(0.010, 100e5, 288.15, 0.006, isothermal=False)
        i = TR.gas_blowdown(0.010, 100e5, 288.15, 0.006, isothermal=True)
        assert i.released_kg > s.released_kg
        assert i.duration_s >= s.duration_s

    def test_isolation_stops_the_release(self):
        import transient as TR
        free = TR.gas_blowdown(0.010, 100e5, 288.15, 0.006)
        cut = TR.gas_blowdown(0.010, 100e5, 288.15, 0.006,
                              isolation_time_s=0.3)
        assert cut.released_kg < free.released_kg
        assert "isolation" in cut.limited_by

    def test_loss_of_vacuum_reproduces_hiad58(self):
        """The heat leak is back-solved from the recorded boil-off rate,
        Q = 0.10 kg/s x 445.6 kJ/kg = 45 kW, and the profile then follows.
        A check, not a validation: one case cannot validate a model, and
        the heat leak after a loss of vacuum is not published for any
        real vessel."""
        import transient as TR
        h = TR.HIAD58
        p = TR.loss_of_vacuum(h["inventory_kg"], h["volume_m3"],
                              TR.HIAD58_HEAT_LEAK_W,
                              h["relief_pressure_pa"], 0.0064,
                              max_time_s=40000.0, dt_s=20.0)
        assert p.released_kg == pytest.approx(h["recorded_released_kg"],
                                              rel=0.10)
        # A mass-conserving ullage model retains the vapour accumulated
        # before lift and therefore runs about 18% longer than the incident
        # summary. That is within a deliberately loose check, not validation.
        assert p.duration_s == pytest.approx(h["recorded_duration_s"],
                                             rel=0.20)
        assert p.mean_rate_kg_s() == pytest.approx(
            h["recorded_rate_kg_s"], rel=0.15)

    def test_pressure_rises_before_the_relief_lifts(self):
        """The opposite of a blowdown. Heat leaks in, liquid boils, and
        the pressure RISES until the relief opens -- which is how a
        vessel with a 1 bar design pressure reached 13 bar."""
        import transient as TR
        p = TR.loss_of_vacuum(2600.0, 42.0, 45e3, 12e5, 0.0064,
                              max_time_s=40000.0, dt_s=20.0)
        early = [s for s in p.steps if s.t_s < 500.0]
        assert early[-1].pressure_pa > early[0].pressure_pa
        assert p.peak_pressure_pa == pytest.approx(12e5, rel=0.01)

    def test_loss_of_vacuum_conserves_mass(self):
        import transient as TR
        initial = 2600.0
        p = TR.loss_of_vacuum(initial, 42.0, 45e3, 12e5, 0.0064,
                              max_time_s=40000.0, dt_s=20.0)
        for step in p.steps:
            assert step.released_kg + step.remaining_kg == pytest.approx(
                initial, rel=0.0, abs=1e-6)

    def test_profile_validation_rejects_mass_creation(self):
        import transient as TR
        p = TR.Profile(
            steps=[
                TR.Step(0.0, 10e5, 288.0, 0.1, 0.0, 1.0,
                        TR.Phase.GAS, TR.IsolationState.OPEN),
                TR.Step(10.0, 5e5, 270.0, 0.05, 0.6, 0.6,
                        TR.Phase.GAS, TR.IsolationState.OPEN),
            ],
            limited_by="synthetic invalid profile",
            provenance=TR.BLOWDOWN_PROV)
        with pytest.raises(ValueError, match="mass conservation"):
            p.validate()

    def test_profile_rate_reduction_is_explicit(self):
        import transient as TR
        p = TR.Profile(
            steps=[
                TR.Step(0.0, 10e5, 288.0, 0.03, 0.0, 1.0,
                        TR.Phase.GAS, TR.IsolationState.OPEN),
                TR.Step(20.0, 2e5, 250.0, 0.01, 0.4, 0.6,
                        TR.Phase.GAS, TR.IsolationState.OPEN),
            ],
            limited_by="synthetic valid profile",
            provenance=TR.BLOWDOWN_PROV)
        p.validate()
        assert p.representative_rate(TR.RateBasis.PEAK) == 0.03
        assert p.representative_rate(
            TR.RateBasis.MASS_EQUIVALENT_MEAN) == pytest.approx(0.02)

    def test_profile_validation_rejects_rate_integral_mismatch(self):
        import transient as TR
        p = TR.Profile(
            steps=[
                TR.Step(0.0, 10e5, 288.0, 0.1, 0.0, 1.0,
                        TR.Phase.GAS, TR.IsolationState.OPEN),
                TR.Step(20.0, 2e5, 250.0, 0.01, 0.4, 0.6,
                        TR.Phase.GAS, TR.IsolationState.OPEN),
            ],
            limited_by="inconsistent supplied profile",
            provenance=TR.BLOWDOWN_PROV)
        with pytest.raises(ValueError, match="rate integral"):
            p.validate()

    @pytest.mark.parametrize("dt", [0.0, -1.0, float("nan")])
    def test_loss_of_vacuum_rejects_invalid_time_step(self, dt):
        import transient as TR
        with pytest.raises(ValueError, match="dt_s"):
            TR.loss_of_vacuum(10.0, 1.0, 100.0, 5e5, 0.006,
                              dt_s=dt)

    def test_undersized_relief_does_not_pin_the_pressure(self):
        import transient as TR
        p = TR.loss_of_vacuum(2600.0, 42.0, 200e3, 12e5, 0.0005,
                              max_time_s=4000.0, dt_s=20.0)
        assert p.peak_pressure_pa > 12e5
        assert "over-pressures" in p.limited_by

    def test_a_bigger_heat_leak_opens_the_relief_sooner(self):
        import transient as TR
        def onset(q):
            p = TR.loss_of_vacuum(2600.0, 42.0, q, 12e5, 0.0064,
                                  max_time_s=40000.0, dt_s=20.0)
            return next((s.t_s for s in p.steps if s.rate_kg_s > 0),
                        float("inf"))
        assert onset(100e3) < onset(45e3) < onset(20e3)


class TestGating:
    def test_a_refused_value_cannot_be_read(self):
        from gating import Gated, RefusedError
        g = Gated.refuse("x", "outside premise")
        with pytest.raises(RefusedError):
            _ = g.value

    def test_bound_policy_refuses_when_no_bound_is_defined(self):
        """An undefined bound is not a conservative one."""
        from gating import Gated, RefusePolicy, RefusedError
        g = Gated.refuse("cloud_top_height_m", "rise unresolved")
        with pytest.raises(RefusedError):
            g.resolve(RefusePolicy.BOUND)

    def test_coverage_reports_partial_as_a_lower_bound(self):
        from gating import Coverage
        c = Coverage()
        c.record_evaluated(1e-4)
        c.record_refused(1e-3, "lfl_distance_m", "S001-100%")
        assert not c.complete
        assert "LOWER BOUND" in c.statement()


# --------------------------------------------------------------------------
# damage
# --------------------------------------------------------------------------

class TestDamage:
    def test_ignition_threshold_is_35_kw(self):
        """Q^2 t = 2.5e4 kW^2 m^-4 s at the 20 s exposure cap."""
        import damage as D
        assert D.Q_IGNITION_W_M2 / 1e3 == pytest.approx(35.4, abs=0.5)

    def test_indoor_protection_is_a_step(self):
        import damage as D
        assert D.heat_radiation(30e3, 20).fe_in == 0.0
        assert D.heat_radiation(40e3, 20).fe_in == 1.0

    def test_figure_5_4_below_threshold(self):
        """PE is the individual quantity and FE the population one; the
        route does not change either. Read from Figure 5.4."""
        import damage as D
        r = D.heat_radiation(25e3, 20)
        assert r.pe == pytest.approx(0.80, abs=0.02)
        assert r.fe_in == 0.0
        assert r.fe_out == pytest.approx(D.CLOTHING_FACTOR * r.pe, rel=1e-12)

    def test_route_does_not_change_the_values(self):
        import damage as D
        a = D.heat_radiation(25e3, 20, D.RiskRoute.INDIVIDUAL)
        b = D.heat_radiation(25e3, 20, D.RiskRoute.SOCIETAL)
        assert (a.pe, a.fe_in, a.fe_out) == (b.pe, b.fe_in, b.fe_out)

    def test_figure_5_5_overpressure_zones(self):
        """Read from the figure. PE is zero in the middle band while
        FE_in is not: what kills there is the building, not the blast."""
        import damage as D
        hi = D.overpressure(0.35)
        assert (hi.pe, hi.fe_in, hi.fe_out) == (1.0, 1.0, 1.0)
        mid = D.overpressure(0.15)
        assert (mid.pe, mid.fe_in, mid.fe_out) == (0.0, 0.025, 0.0)
        lo = D.overpressure(0.05)
        assert (lo.pe, lo.fe_in, lo.fe_out) == (0.0, 0.0, 0.0)

    def test_pi_route_is_valid_for_detonation(self):
        """The reason it exists. The peak-only route is deflagration only
        because 5.2.4 says so, and hydrogen DDT is credible."""
        import damage as D
        a = D.overpressure_pi(150e3, 500.0)
        assert a.mechanism == "OVERPRESSURE_PI"
        assert 0.4 < a.pe < 0.8

    def test_pi_and_zone_routes_are_not_the_same_quantity(self):
        """Purple Book gives PE = 1 at 0.35 barg; the pressure-impulse
        route needs about 2 barg for the same. One is building collapse
        on an indoor population, the other is direct pressure on a person,
        and adding them would double count."""
        import damage as D
        assert D.overpressure(0.35).pe == 1.0
        assert D.overpressure_pi(35e3, 500.0).pe < 0.05
        assert D.overpressure_pi(200e3, 5000.0).pe == pytest.approx(1.0,
                                                                    abs=0.02)

    def test_cell_coverage_is_graded(self):
        """6.2.6 note 1: grade partly covered cells by area so IR and SR
        do not jump between 0 and 1."""
        import damage as D
        f = D.cell_coverage_fraction(25.0, 0.0, 25.0, 25.0)
        assert 0.0 < f < 1.0


# --------------------------------------------------------------------------
# frequency library
# --------------------------------------------------------------------------

class TestFrequencies:
    def test_everything_published_is_read_from_a_report(self):
        import taxonomy as T
        stale = [e for e in T.FREQUENCY_LIBRARY.values()
                 if e.provenance.transcription
                 is T.TranscriptionSource.CODE_INSPECTION]
        assert stale == []

    @pytest.mark.parametrize("prim,bin_i,expected", [
        ("COMPRESSOR", 0, 9.97e-2), ("VESSEL", 4, 2.33e-7),
        ("VALVE", 2, 5.44e-5), ("PIPE", 0, 8.02e-6)])
    def test_gh2_matches_sand_table_1_1(self, prim, bin_i, expected):
        import taxonomy as T
        e = T.FREQUENCY_LIBRARY[(T.Primitive[prim], T.Fuel.GH2)]
        assert e.medians[bin_i] == pytest.approx(expected, rel=1e-3)

    def test_filter_uses_the_superseding_table(self):
        """SAND2024-06491 exists to replace this row. Table 1-1 has
        4.39e-3 at full bore; Table 4-1 has 4.79e-5."""
        import taxonomy as T
        e = T.FREQUENCY_LIBRARY[(T.Primitive.FILTER, T.Fuel.GH2)]
        assert e.medians[4] == pytest.approx(4.79e-5, rel=1e-3)

    @pytest.mark.parametrize("prim,bin_i,expected", [
        ("VESSEL", 0, 6.5e-4), ("VESSEL", 4, 1.2e-6),
        ("HOSE", 2, 1.2e-4), ("VALVE", 0, 1.2e-4)])
    def test_lh2_matches_brooks_table_2(self, prim, bin_i, expected):
        import taxonomy as T
        e = T.FREQUENCY_LIBRARY[(T.Primitive[prim], T.Fuel.LH2)]
        assert e.medians[bin_i] == pytest.approx(expected, rel=1e-2)

    def test_lh2_is_not_gh2_copied_across(self):
        """An earlier reading of this project had it that way. The vessel
        is 464x the gaseous value at 0.01% and the valve is 0.04x."""
        import taxonomy as T
        v_lh2 = T.FREQUENCY_LIBRARY[(T.Primitive.VESSEL, T.Fuel.LH2)]
        v_gh2 = T.FREQUENCY_LIBRARY[(T.Primitive.VESSEL, T.Fuel.GH2)]
        assert v_lh2.medians[0] / v_gh2.medians[0] > 400
        a_lh2 = T.FREQUENCY_LIBRARY[(T.Primitive.VALVE, T.Fuel.LH2)]
        a_gh2 = T.FREQUENCY_LIBRARY[(T.Primitive.VALVE, T.Fuel.GH2)]
        assert a_lh2.medians[0] / a_gh2.medians[0] < 0.1

    def test_hose_and_joint_rise_with_leak_size(self):
        """Published as such. The authors say they cannot tell whether it
        is physical or an artefact; it is transcribed, not smoothed."""
        import taxonomy as T
        for p in (T.Primitive.HOSE, T.Primitive.JOINT):
            e = T.FREQUENCY_LIBRARY[(T.Primitive[p.value], T.Fuel.LH2)]
            assert e.medians[4] > e.medians[0] * 0.5

    def test_proxy_chain_degrades_grade_rather_than_refusing(self):
        import taxonomy as T
        r = T.resolve_frequency(T.Primitive.PUMP_SEAL, T.Service.LH2)
        assert r.fuel_used is T.Fuel.OANDG
        assert r.provenance.grade is T.Grade.ENGINEERING_JUDGEMENT

    def test_no_invented_conservatism_factor(self):
        """The literature says a cryogenic hydrogen pump leaks more than
        the oil and gas proxy. It does not say how much more. A factor of
        ten stood here; an unsourced number times an invented factor
        looks more deliberate than the unsourced number alone."""
        import taxonomy as T
        for e in T.FREQUENCY_LIBRARY.values():
            assert e.conservatism_factor == 1.0

    def test_relief_release_is_rate_limited_by_the_relief_not_the_bore(self):
        """HIAD event 58: a 42,000 litre LH2 rail tanker lost its
        interspace vacuum to a micro-crack in the outer wall, rose to the
        13 bar relief setting against a 1 bar design pressure, and vented
        2,500 kg over seven hours at 0.10 kg/s through the safety valves.
        Nothing ignited.

        Modelling that as a full-bore saturated-liquid release of the 50 mm
        line gave 6.1 kg/s, sixty-one times the recorded rate. At the
        recorded high-vapour state the same-bore error is still about 34x,
        and those errors were
        making the vacuum-jacketed line the dominant risk contributor on
        the reference site."""
        from source_term import discharge
        import taxonomy as T
        site = T.Site(
            name="v",
            sections=[T.Section(id="TR", inventory_kg=2600,
                                isolation_time_s=25000,
                                service=T.Service.LH2)],
            assemblies=[T.AssemblySpec(
                assembly=T.Assembly.VJ_LINE, service=T.Service.LH2,
                tag="VJ", nominal_diameter_m=0.05, pressure_pa=6e5,
                temperature_k=22, position=T.Position(x=0, y=0),
                section_id="TR")])
        full = [s for s in T.enumerate_scenarios(site)
                if s.bin_label == "100%"
                and s.release_path is T.ReleasePath.VIA_RELIEF]
        assert full
        for s in full:
            q = discharge(6e5, None, "ParaHydrogen", s.hole_diameter_m,
                          stagnation_quality=(
                              T.VJ_RELIEF_VAPOUR_QUALITY_MIN)).rate_kg_s
            assert q == pytest.approx(0.10, rel=0.05)

    def test_flanges_outside_the_jacket_keep_the_line_bore(self):
        """The relief limit applies to what leaves through the relief. An
        end connection outside the jacket is an ordinary release."""
        import taxonomy as T
        site = T.Site(
            name="v",
            sections=[T.Section(id="TR", inventory_kg=80,
                                isolation_time_s=30,
                                service=T.Service.LH2)],
            assemblies=[T.AssemblySpec(
                assembly=T.Assembly.VJ_LINE, service=T.Service.LH2,
                tag="VJ", nominal_diameter_m=0.05, pressure_pa=6e5,
                temperature_k=22, position=T.Position(x=0, y=0),
                section_id="TR")])
        direct = [s for s in T.enumerate_scenarios(site)
                  if s.bin_label == "100%"
                  and s.release_path is T.ReleasePath.DIRECT]
        assert direct
        assert all(s.hole_diameter_m == pytest.approx(0.05)
                   for s in direct)

    def test_vj_line_releases_through_relief_as_cold_vapour(self):
        """Not a jacket rupture at an invented probability. The jacket
        carries its own relief, the vacuum plug lifts near 0.5 barg, and
        the hydrogen leaves as high-vapour two-phase flow handled by the
        LH2 adapter with an explicit liquid fraction."""
        import taxonomy as T
        site = T.Site(
            name="vj",
            sections=[T.Section(id="TR", inventory_kg=80,
                                isolation_time_s=30, service=T.Service.LH2)],
            assemblies=[T.AssemblySpec(
                assembly=T.Assembly.VJ_LINE, service=T.Service.LH2, tag="VJ",
                nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
                position=T.Position(x=0, y=0), section_id="TR")])
        sc = T.enumerate_scenarios(site)
        inner = [s for s in sc if s.release_path is T.ReleasePath.VIA_RELIEF]
        assert inner, "the inner line should release through the relief"
        # Two-phase at a high vapour fraction, which slabx takes as a
        # parameter. It was refused as COLD_GH2 until the recorded
        # incident showed it is expressible in a model already present.
        assert all(s.physics_route is T.PhysicsRoute.SLABX_LH2
                   for s in inner)
        ends = [s for s in sc if s.release_path is T.ReleasePath.DIRECT]
        assert all(s.physics_route is T.PhysicsRoute.SLABX_LH2 for s in ends)

    def test_vent_system_closes_a_real_incident_gap(self):
        """Sakamoto et al. (2016): the Emeryville incident began with a
        pressure relief valve nozzle failing, releasing ~30 kg of hydrogen
        in the first minute through the vent, which premixed inside the
        tube, detonated, then burned as a jet flame at the outlet. Nothing
        in this taxonomy could enumerate that before. EIGA Doc 06/19 5.1.7
        requires every relief device to be connected to a vent stack and
        5.1.2 lists vent stacks first among the points a safety distance
        is measured from."""
        import taxonomy as T
        site = T.Site(
            name="v",
            sections=[T.Section(id="TK", inventory_kg=700,
                                isolation_time_s=1800,
                                service=T.Service.LH2)],
            assemblies=[T.AssemblySpec(
                assembly=T.Assembly.VENT_SYSTEM, service=T.Service.GH2,
                tag="VENT-1", nominal_diameter_m=0.05, pressure_pa=3e5,
                temperature_k=250, position=T.Position(x=0, y=0, z=6),
                section_id="TK")])
        sc = T.enumerate_scenarios(site)
        assert sc
        assert all(s.release_path is T.ReleasePath.VIA_VENT for s in sc)
        assert all(s.orientation is T.Orientation.UP for s in sc)
        assert all(s.physics_route is T.PhysicsRoute.GH2_JET for s in sc)
        assert all(s.computable for s in sc)

    def test_vent_records_what_it_does_not_cover(self):
        """The jet at the outlet is modelled; the premixing INSIDE the
        vent tube that produced Emeryville's initial loud boom is not, and saying so
        is the point."""
        import taxonomy as T
        site = T.Site(
            name="v",
            sections=[T.Section(id="TK", inventory_kg=700,
                                isolation_time_s=1800,
                                service=T.Service.LH2)],
            assemblies=[T.AssemblySpec(
                assembly=T.Assembly.VENT_SYSTEM, service=T.Service.GH2,
                tag="V", nominal_diameter_m=0.05, pressure_pa=3e5,
                temperature_k=250, position=T.Position(x=0, y=0, z=6),
                section_id="TK")])
        note = " ".join(p.note for s in T.enumerate_scenarios(site)
                        for p in s.provenance)
        assert "premixing" in note
        assert "detonation" in note

    def test_vent_stack_itself_has_no_frequency(self):
        """Decomposed into the relief devices that feed it. The stack is
        kept as a no-data primitive so its absence stays visible rather
        than being covered over by the decomposition."""
        import taxonomy as T
        assert T.Primitive.VENT_STACK in T.NO_DATA
        r = T.resolve_frequency(T.Primitive.VENT_STACK, T.Service.GH2)
        assert r.provenance.grade is T.Grade.PLACEHOLDER

    def test_pump_seal_records_that_it_dominates_elsewhere(self):
        """Two independent published LH2 station QRAs name the cryogenic
        pump as the dominant risk unit, and it is the only unsourced row
        in the library. The component most likely to dominate carries the
        weakest evidence, and the note has to say so."""
        import taxonomy as T
        e = T.FREQUENCY_LIBRARY[(T.Primitive.PUMP_SEAL, T.Fuel.OANDG)]
        assert "dominant" in e.provenance.note
        assert e.conservatism_factor == 1.0

    def test_components_with_no_data_stay_refused(self):
        import taxonomy as T
        for p in T.NO_DATA:
            r = T.resolve_frequency(p, T.Service.LH2)
            assert r.provenance.grade is T.Grade.PLACEHOLDER


# --------------------------------------------------------------------------
# uncertainty
# --------------------------------------------------------------------------

class TestUncertainty:
    def test_median_draw_reproduces_the_point_values(self):
        import random
        import numpy as np
        import taxonomy as T
        import uncertainty as U

        class Zero(random.Random):
            def gauss(self, mu, sigma):
                return 0.0

        lib = U.sample_library(Zero())
        for key, e in T.FREQUENCY_LIBRARY.items():
            if e.mu is None:
                continue
            expected = [math.exp(m) * e.conservatism_factor for m in e.mu]
            assert np.allclose(lib[key], expected, rtol=1e-9)

    def test_bins_share_a_draw(self):
        """The source model is a regression across leak size, so a
        component that leaks more than expected does so at every size.
        Independent draws would let the 100% bin exceed the 0.01% bin."""
        import random
        import taxonomy as T
        import uncertainty as U
        rng = random.Random(1)
        for _ in range(50):
            lib = U.sample_library(rng)
            v = lib[(T.Primitive.VESSEL, T.Fuel.LH2)]
            assert all(a >= b for a, b in zip(v, v[1:]))

    def test_significant_figures_shrink_as_the_span_grows(self):
        from uncertainty import Interval
        assert Interval(1e-5, 8e-6, 1.2e-5, 100).significant_figures() == 2
        assert Interval(1e-5, 5e-6, 2e-5, 100).significant_figures() == 1
        assert Interval(1e-5, 1e-6, 1e-4, 100).significant_figures() == 0

    def test_published_spans_are_extreme(self):
        """Not a defect: the LH2 hose at the 1% bin spans six orders."""
        import taxonomy as T
        e = T.FREQUENCY_LIBRARY[(T.Primitive.HOSE, T.Fuel.LH2)]
        span = e.percentile(0.95)[2] / e.percentile(0.05)[2]
        assert span > 1e6

    def test_flame_model_form_is_an_envelope_not_a_distribution(self):
        from types import SimpleNamespace
        import numpy as np
        import uncertainty as U

        def result(max_ir, values):
            return SimpleNamespace(
                max_ir=max_ir,
                grid=SimpleNamespace(values=np.asarray(values),
                                     cell_size_m=10.0))

        envelope = U.flame_model_envelope({
            "molkov-conservative": result(1.2e-5, [1.2e-5, 2e-6]),
            "molkov-fit": result(0.9e-5, [0.9e-5, 1e-6]),
            "delichatsios": result(1.0e-5, [1.0e-5, 1.5e-6]),
        })
        assert envelope.max_ir_low == pytest.approx(0.9e-5)
        assert envelope.max_ir_high == pytest.approx(1.2e-5)
        assert envelope.max_ir_span == pytest.approx(4.0 / 3.0)
        assert envelope.integrated_span > 1.0
        assert "no probabilities assigned" in envelope.statement()


class TestAcceptance:
    def test_interval_decides_when_it_exists(self):
        """A point estimate of 7.2e-6 against a limit of 1e-5 reads as
        compliant, while its 5th percentile of 2.3e-5 does not. The
        interval has to be consulted first or compliance is decided by a
        number the data does not support."""
        import decision as dec
        from uncertainty import Interval
        iv = Interval(1.8e-4, 2.3e-5, 4.7e-2, 5000)
        with_iv = dec.check_individual_risk(7.19e-6, None, 1e-5,
                                            "test", interval=iv)
        without = dec.check_individual_risk(7.19e-6, None, 1e-5, "test")
        assert with_iv.verdict is dec.Verdict.EXCEEDS
        assert without.verdict is dec.Verdict.WITHIN

    def test_straddling_is_its_own_verdict(self):
        import decision as dec
        from uncertainty import Interval
        iv = Interval(1.8e-4, 2.3e-5, 4.7e-2, 5000)
        r = dec.check_individual_risk(1.8e-4, None, 1e-3, "test", interval=iv)
        assert r.verdict is dec.Verdict.STRADDLES

    def test_partial_coverage_cannot_yield_a_pass(self):
        import decision as dec
        from gating import Coverage
        c = Coverage()
        c.record_evaluated(1e-6)
        c.record_refused(1e-5, "lfl_distance_m", "S001")
        r = dec.check_individual_risk(1e-9, c, 1e-6, "test")
        assert r.verdict is dec.Verdict.NOT_SHOWN_TO_EXCEED


# --------------------------------------------------------------------------
# vectorisation
# --------------------------------------------------------------------------

class TestField:
    def test_matches_the_scalar_implementation(self):
        """The scalar version is the reference: it is the one written from
        the papers."""
        import numpy as np
        import field as FD
        import fire as F
        from source_term import discharge
        r = discharge(3.5e7, 288.15, "Hydrogen", 0.006)
        rho = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
        fl = F.flame_length(
            r.rate_kg_s,
            F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa,
                              r.velocity_m_s, rho, 0.006),
            hole_diameter_m=0.006, model="molkov")
        xs = np.array([5.0, 10.0, 15.0, 20.0, 30.0, 50.0])
        mean, _ = FD.flux_field(fl, xs, np.zeros_like(xs))
        for i, x in enumerate(xs):
            scalar, _, _ = F.heat_flux_direction_averaged(fl, float(x), 1.0)
            assert mean[i] == pytest.approx(scalar, rel=1e-9)

    def test_transmissivity_implementations_agree(self):
        """Two copies of one equation is how the last regression happened:
        the scalar version was corrected against the source and the
        vectorised one was not, leaving the field 25% high. Pinned at the
        level of the function, not of one call site."""
        import numpy as np
        import field as FD
        import fire as F
        for path in [0.5, 2.0, 10.0, 50.0, 200.0]:
            for rh in [0.1, 0.5, 0.9]:
                a = F.transmissivity(path, rh)
                b = float(FD._transmissivity(np.array([path]), rh, F.T_AMB)[0])
                assert a == pytest.approx(b, rel=1e-12)

    def test_coverage_field_matches_scalar(self):
        import numpy as np
        import damage as D
        import field as FD
        gx = np.array([0.0, 12.0, 25.0, 40.0])
        cv = FD.coverage_field(gx, np.zeros_like(gx), 25.0, 25.0)
        for i, x in enumerate(gx):
            assert cv[i] == pytest.approx(
                D.cell_coverage_fraction(float(x), 0.0, 25.0, 25.0), abs=1e-12)

    def test_directional_footprint_rotates_with_release_azimuth(self):
        import numpy as np
        import field as FD
        axial = np.array([0.0, 10.0])
        radii = np.array([1.0, 0.0])
        x = np.array([5.0, 0.0, -5.0])
        y = np.array([0.0, 5.0, 0.0])
        east = FD.directional_footprint_field(
            x, y, 0.1, axial, radii, azimuth_deg=0.0, n_sub=1)
        north = FD.directional_footprint_field(
            x, y, 0.1, axial, radii, azimuth_deg=90.0, n_sub=1)
        assert list(east) == [1.0, 0.0, 0.0]
        assert list(north) == [0.0, 1.0, 0.0]

    def test_directional_grid_area_matches_profile_integral(self):
        import numpy as np
        import field as FD
        axial = np.array([0.0, 10.0])
        radii = np.array([1.0, 0.0])
        step = 0.1
        gx, gy = np.meshgrid(
            np.arange(-2.0, 12.0 + step, step),
            np.arange(-2.0, 2.0 + step, step))
        coverage = FD.directional_footprint_field(
            gx, gy, step, axial, radii, azimuth_deg=0.0, n_sub=1)
        # 2 * integral_0^10 (1 - x/10) dx = 10 m2.
        assert coverage.sum() * step * step == pytest.approx(10.0, rel=0.03)

    def test_unknown_bearing_is_averaged_for_risk_but_bounded_for_equipment(self):
        import numpy as np
        import field as FD
        axial = np.array([0.0, 10.0])
        radii = np.array([1.0, 0.0])
        coverage = FD.directional_footprint_field(
            np.array([5.0, 0.0]), np.array([0.0, 5.0]), 0.1,
            axial, radii, azimuth_deg=None, n_sub=1)
        assert coverage[0] == pytest.approx(coverage[1])
        assert FD.point_in_directional_footprint(
            3.0, 4.0, axial, radii, None)


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def small_site():
    from taxonomy import (ComponentSpec, Position, Primitive, Section,
                          Service, Site)
    return Site(
        name="test",
        sections=[
            Section(id="TR", inventory_kg=80, isolation_time_s=30,
                    service=Service.LH2),
            Section(id="HP", inventory_kg=120, isolation_time_s=15,
                    service=Service.GH2)],
        components=[
            ComponentSpec(primitive=Primitive.VALVE, service=Service.LH2,
                          count=4, tag="LV", nominal_diameter_m=0.05,
                          pressure_pa=6e5, temperature_k=22,
                          position=Position(x=0, y=0), section_id="TR"),
            ComponentSpec(primitive=Primitive.VALVE, service=Service.GH2,
                          count=12, tag="HV", nominal_diameter_m=0.012,
                          pressure_pa=4.5e7, temperature_k=288,
                          position=Position(x=50, y=0), section_id="HP")])


class TestPipeline:
    def test_runs_and_reports_a_grade(self, small_site):
        from ignition import IgnitionScheme
        import pipeline
        from taxonomy import Grade
        r = pipeline.run(small_site, half_extent_m=100, cell_size_m=50,
                         ignition_scheme=IgnitionScheme.HYRAM)
        assert r.max_ir > 0
        assert r.grade is not Grade.PLACEHOLDER
        assert r.coverage.complete

    @staticmethod
    def _transient_site_and_profile():
        import transient as TR
        from taxonomy import (ComponentSpec, Position, Primitive, Section,
                              Service, Site)
        site = Site(
            name="transient-coupling",
            sections=[Section(id="HP", inventory_kg=20,
                              isolation_time_s=15,
                              service=Service.GH2)],
            components=[ComponentSpec(
                primitive=Primitive.VALVE, service=Service.GH2,
                count=1, tag="HV-T", nominal_diameter_m=0.012,
                pressure_pa=4.5e7, temperature_k=288,
                position=Position(x=0, y=0), section_id="HP")])
        profile = TR.Profile(
            steps=[
                TR.Step(0.0, 4.5e7, 288.0, 0.05, 0.0, 1.0,
                        TR.Phase.GAS, TR.IsolationState.OPEN),
                TR.Step(10.0, 1.5e7, 260.0, 0.015, 0.25, 0.75,
                        TR.Phase.GAS, TR.IsolationState.CLOSING),
                TR.Step(20.0, 2.0e5, 230.0, 0.0, 0.4, 0.6,
                        TR.Phase.GAS, TR.IsolationState.CLOSED),
            ],
            limited_by="synthetic isolation profile",
            provenance=TR.BLOWDOWN_PROV)
        return site, profile

    def test_transient_cases_require_an_explicit_policy(self):
        import pipeline
        site, profile = self._transient_site_and_profile()
        cases = {"S000-10%": [pipeline.TransientCase("measured", profile)]}
        with pytest.raises(ValueError, match="explicit"):
            pipeline.run(site, half_extent_m=50, cell_size_m=50,
                         transient_cases=cases)

    def test_transient_case_probabilities_must_close(self):
        import pipeline
        site, profile = self._transient_site_and_profile()
        cases = {"S000-10%": [
            pipeline.TransientCase("a", profile, 0.4),
            pipeline.TransientCase("b", profile, 0.5),
        ]}
        with pytest.raises(ValueError, match="sum to"):
            pipeline.run(
                site, half_extent_m=50, cell_size_m=50,
                transient_cases=cases,
                transient_policy=pipeline.TRANSIENT_SCREENING_ENVELOPE)

    def test_transient_profile_replaces_blocking_and_is_audited(self):
        import export
        import pipeline
        from taxonomy import enumerate_scenarios
        site, profile = self._transient_site_and_profile()
        scenario_id = "S000-10%"
        cases = {scenario_id: [
            pipeline.TransientCase("measured", profile),
        ]}
        peak = pipeline.run(
            site, half_extent_m=50, cell_size_m=50,
            transient_cases=cases,
            transient_policy=pipeline.TRANSIENT_SCREENING_ENVELOPE)
        mean = pipeline.run(
            site, half_extent_m=50, cell_size_m=50,
            transient_cases=cases,
            transient_policy=pipeline.TRANSIENT_MASS_EQUIVALENT)

        assert len(peak.transient_audit) == len(mean.transient_audit) == 1
        assert peak.transient_audit[0].dispersion_rate_kg_s == 0.05
        assert mean.transient_audit[0].dispersion_rate_kg_s == \
            pytest.approx(0.02)
        base_frequency = next(
            s.frequency_per_year for s in enumerate_scenarios(site)
            if s.scenario_id == scenario_id)
        target = [c for c in peak.contributions
                  if c.loc_id == scenario_id]
        target_mean = [c for c in mean.contributions
                       if c.loc_id == scenario_id]
        assert target
        assert all(c.frequency_per_year == pytest.approx(base_frequency)
                   for c in target)
        assert sum(c.delta_ir for c in target) > sum(
            c.delta_ir for c in target_mean)
        assert "transient_coupling" in export.export(peak)

    def test_no_placeholder_physics_remains(self):
        import os
        assert not os.path.exists("physics_stub.py")

    def test_catastrophic_vessel_failure_is_instantaneous(self):
        """Only an instantaneous release reaches the BLEVE branch. A
        full-bore hole in a vessel enumerated as continuous made that
        branch unreachable for the largest inventory on the site."""
        from taxonomy import (ComponentSpec, Position, Primitive,
                              ReleaseKind, Section, Service, Site,
                              enumerate_scenarios)
        site = Site(
            name="t",
            sections=[Section(id="TK", inventory_kg=5000,
                              isolation_time_s=1800, service=Service.LH2)],
            components=[ComponentSpec(
                primitive=Primitive.VESSEL, service=Service.LH2, tag="TK",
                nominal_diameter_m=0.05, pressure_pa=6e5,
                temperature_k=22, position=Position(x=0, y=0),
                section_id="TK")])
        sc = enumerate_scenarios(site)
        inst = [s for s in sc
                if s.release_kind is ReleaseKind.INSTANTANEOUS]
        assert len(inst) == 1
        assert inst[0].bin_label == "100%"

    def test_bleve_branch_reaches_the_grid(self):
        from ignition import IgnitionScheme
        import pipeline
        from taxonomy import (ComponentSpec, Position, Primitive, Section,
                              Service, Site)
        site = Site(
            name="t",
            sections=[Section(id="TK", inventory_kg=5000,
                              isolation_time_s=1800, service=Service.LH2)],
            components=[ComponentSpec(
                primitive=Primitive.VESSEL, service=Service.LH2, tag="TK",
                nominal_diameter_m=0.05, pressure_pa=6e5,
                temperature_k=22, position=Position(x=0, y=0),
                section_id="TK")])
        r = pipeline.run(site, half_extent_m=600, cell_size_m=100,
                         ignition_scheme=IgnitionScheme.HYRAM)
        assert any(c.ignition_event == "BLEVE" for c in r.contributions)

    def test_cold_gh2_routes_by_density_not_temperature(self):
        """The jet correlation carries density in d* and its constant is
        reported independent of the ratio, 0.208 for hydrogen against
        0.210 for methane at 0.070 and 0.556. Cold gaseous hydrogen at
        150 K is 0.134 and sits between them, so most of what was
        refused as a temperature band is interpolation."""
        from taxonomy import PhysicsRoute, Service, density_ratio_of, route
        assert density_ratio_of(150.0) == pytest.approx(0.134, abs=0.005)
        for t in (250.0, 150.0, 60.0, 40.0):
            assert route(Service.COLD_GH2, None,
                         density_ratio_of(t)) is PhysicsRoute.GH2_JET

    def test_vapour_denser_than_air_goes_to_the_dense_gas_model(self):
        """Saturated hydrogen vapour near its boiling point is HEAVIER
        than ambient air. A buoyant jet correlation is the wrong branch;
        that is what SLAB is for."""
        from taxonomy import PhysicsRoute, Service, route
        assert route(Service.COLD_GH2, None, 1.6) is PhysicsRoute.SLABX_LH2

    def test_the_narrow_band_stays_refused(self):
        """Between 0.6 and 1.0: too heavy for the jet correlation to be
        interpolation, too light to be a dense gas. Routing it anywhere
        would replace a visible gap with an invisible error."""
        from taxonomy import PhysicsRoute, Service, route
        for dr in (0.7, 0.85, 0.99):
            assert route(Service.COLD_GH2, None, dr) is \
                PhysicsRoute.UNCOVERED

    def test_vj_relief_is_two_phase_not_a_gap(self):
        """The recorded incident put the hydrogen at 80-100% vapour.
        slabx takes liquid_fraction, so the case is a parameter of a
        model already present."""
        from taxonomy import PhysicsRoute, ReleasePath, Service, route
        assert route(Service.LH2, ReleasePath.VIA_RELIEF) is \
            PhysicsRoute.SLABX_LH2

    def test_air_condensation_is_outside_the_flammable_range(self):
        """The main physical objection to treating cold hydrogen with an
        ordinary dispersion model. Onset is 88 to 94 mol% hydrogen and
        the upper flammability limit is 75, so inside the flammable range
        no nitrogen or oxygen has left the gas phase. Measured with no
        free parameters, not assumed."""
        from slabx_lh2 import air_condensation as ac
        assert ac.UFL_HYDROGEN == pytest.approx(75.0, abs=0.5)
        for sp, expected in (("N2", 90.27), ("O2", 88.15)):
            onset = ac.condensation_onset(species=sp)
            assert onset["onset_mol_pct"] == pytest.approx(expected, abs=0.1)
            assert onset["onset_mol_pct"] > ac.UFL_HYDROGEN
            assert onset["inside_flammable_range"] is False

    def test_cold_gh2_fails_loudly(self):
        """A declared gap, not an omission. It must not be filled quietly."""
        from taxonomy import PhysicsRoute, Service, route
        assert route(Service.COLD_GH2) is PhysicsRoute.UNCOVERED

    def test_reproduce_script_is_stable(self):
        """results.json must be regenerable without drift. A claim in a
        document and the code behind it can only stay in step if the
        document quotes the file rather than a typed number."""
        import subprocess
        import sys
        r = subprocess.run([sys.executable, str(HERE / "reproduce.py"),
                            "--check"],
                           capture_output=True, text=True, timeout=1800)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_verification_backlog_regenerates(self):
        """It is generated from the code, so it cannot drift from what the
        code actually contains. Editing it by hand would let the two
        disagree, which is the failure this project exists to avoid."""
        import subprocess
        import sys
        r = subprocess.run([sys.executable, str(HERE / "gen_verification.py")],
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, r.stdout + r.stderr
        text = (HERE / "VERIFICATION.md").read_text(encoding="utf-8")
        assert "PUMP_SEAL" in text
        assert "VENT_STACK" in text

    def test_reproduce_refuses_non_finite_values(self):
        import reproduce
        with pytest.raises(ValueError):
            reproduce.record("test.inf", float("inf"), "MEASURED", "x", "y")

    def test_ignition_scheme_dominates_the_answer(self, small_site):
        """Larger than any physics model in the chain."""
        from ignition import IgnitionScheme
        import pipeline
        a = pipeline.run(small_site, half_extent_m=100, cell_size_m=50,
                         ignition_scheme=IgnitionScheme.PURPLE).max_ir
        b = pipeline.run(small_site, half_extent_m=100, cell_size_m=50,
                         ignition_scheme=IgnitionScheme.HYRAM).max_ir
        assert a / b > 20.0


class TestCorrectnessRegressions:
    """Guards for defects found in the full-source review."""

    def test_ir_grid_never_silently_changes_requested_spacing(self):
        from risk import IRGrid
        with pytest.raises(ValueError, match="divide"):
            IRGrid.square(10.0, 6.0)
        grid = IRGrid.square(10.0, 5.0)
        assert all(b - a == pytest.approx(5.0)
                   for a, b in zip(grid.x, grid.x[1:]))

    def test_fn_curve_aggregates_duplicate_fatality_counts(self):
        from risk import SocietalOutcome, fn_curve
        n, f = fn_curve([
            SocietalOutcome(0.1, 1.0),
            SocietalOutcome(0.2, 1.0),
            SocietalOutcome(0.3, 2.0),
        ])
        assert n.tolist() == [1.0, 2.0]
        assert f.tolist() == pytest.approx([0.6, 0.3])

    def test_zero_uncertainty_interval_has_a_printable_rounding(self):
        from uncertainty import Interval
        assert Interval(0.0, 0.0, 0.0, 0).rounded() == "0"

    def test_structural_band_does_not_depend_on_dict_order(self,
                                                           monkeypatch):
        import equipment_damage as ED
        reordered = dict(reversed(list(ED.STRUCTURAL_BANDS.items())))
        monkeypatch.setattr(ED, "STRUCTURAL_BANDS", reordered)
        expected = max(
            (lower, name)
            for name, (lower, _upper) in reordered.items()
            if 100_000.0 >= lower
        )[1]
        assert ED.structural_band(100_000.0) == expected

    def test_pool_burnback_engulfment_is_fatal_not_zero(self):
        import numpy as np
        import pipeline
        from ignition import Outcome
        fields = {Outcome.POOL_FIRE: np.array([[float("inf"), 0.0]])}
        pe, inside, outside = pipeline._damage_field(
            Outcome.POOL_FIRE, fields, 20.0)
        assert pe[0, 0] == inside[0, 0] == outside[0, 0] == 1.0

    def test_vj_relief_uses_high_vapour_source_and_has_jet_fire(self):
        import pipeline
        import taxonomy as T
        site = T.Site(
            name="vj-regression",
            sections=[T.Section(
                id="TR", inventory_kg=80.0, isolation_time_s=30.0,
                service=T.Service.LH2)],
            assemblies=[T.AssemblySpec(
                assembly=T.Assembly.VJ_LINE, service=T.Service.LH2,
                tag="VJ", nominal_diameter_m=0.05, pressure_pa=6e5,
                temperature_k=22.0, position=T.Position(x=0.0, y=0.0),
                section_id="TR")])
        scenario = next(
            item for item in T.enumerate_scenarios(site)
            if item.release_path is T.ReleasePath.VIA_RELIEF
            and item.bin_label == "100%")
        source = pipeline._scenario_discharge(
            scenario, scenario.pressure_pa, scenario.temperature_k,
            liquid=True)
        assert source.rate_kg_s == pytest.approx(0.10, rel=0.05)
        assert pipeline._flame_for(scenario, source) is not None
        assert pipeline._fireball_for(scenario, 80.0) is None

    def test_failed_rise_fit_refuses_only_height(self, monkeypatch):
        from types import SimpleNamespace
        import numpy as np
        import slabx_adapter as SA
        trajectory = SimpleNamespace(
            z_c=np.array([1.0, 2.0]), h=np.array([2.0, 2.0]))
        monkeypatch.setattr(
            SA, "run_dispersion", lambda *args, **kwargs: (trajectory, None))
        monkeypatch.setattr(
            SA, "applicability", lambda _trajectory: {
                "status": "VALID", "premise_ratio": 0.5, "reason": ""})
        monkeypatch.setattr(
            SA, "flammable_distance", lambda *args, **kwargs: {
                "reached": True, "factored": 12.0, "level": 4.0,
                "heights": [1.0]})
        monkeypatch.setattr(SA, "_footprint", lambda *args: (20.0, 2.0))

        def failed_fit(_trajectory):
            raise ValueError("singular fit")

        monkeypatch.setattr(SA, "rise_scaling", failed_fit)
        result = SA.dispersion(0.1, 5.0)
        assert result.lfl_distance_m.value == pytest.approx(12.0)
        assert result.flammable_mass_kg.value == pytest.approx(2.0)
        assert result.cloud_top_height_m.refused
        assert result.cloud_top_height_m.forced_value == pytest.approx(3.0)

    @pytest.mark.parametrize("diameter,n_scan", [(-0.01, 20), (0.01, 0)])
    def test_source_term_rejects_invalid_geometry_and_scan_count(
            self, diameter, n_scan):
        from source_term import discharge
        with pytest.raises(ValueError):
            discharge(5e6, 288.0, "Hydrogen", diameter, n_scan=n_scan)
