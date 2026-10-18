"""
End to end: a component list becomes an Individual Risk grid.

    Site
      -> enumerate_scenarios          taxonomy   (steps 0, 1, 2)
      -> discharge, released_mass     source_term (step 3a)
      -> dispersion / fire / blast    physics    (step 3b)
      -> build_ignition_tree          ignition   (step 3c)
      -> damage models                damage     (step 3d)
      -> IR accumulation, FN curve    risk       (step 4)

The grade of a result is the grade of its weakest input, so a grid built on
placeholder physics reports itself as placeholder. That is the point of
running the pipeline before the physics exists: it proves the plumbing
without producing a number anyone could mistake for an answer.

Individual Risk follows the free field rule (4.7.2 B): ignition is placed
at maximum cloud extent, and no credit is taken for where ignition sources
actually are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Optional

import numpy as np

import blast as BLAST
import blocking as BL
import hiad as HIAD
import fragments as FRAG
import spill_fire as SF
import damage as dmg
import equipment_damage as eqd
import field as fieldmod
import gh2_jet
import ignition_sources as IS
import fire
import fireball as FB
import dispersion_cache as dcache
import transient as TR
from ignition import (IgnitionScheme, Outcome, ReleaseType,
                      build_ignition_tree, multi_energy_radii)
from gating import Coverage, RefusePolicy, RefusedError
from risk import (IRGrid, PdRoute, RiskContribution, SocietalOutcome,
                  WeatherSector, fn_curve)
from source_term import discharge, line_discharge, released_mass
from taxonomy import (HYRAM_BINS, DischargeCoefficientBasis, Grade,
                       PhysicsRoute, Primitive,
                      Orientation, ReleaseKind, ReleasePath,
                      Scenario, Service, Site, enumerate_scenarios,
                      resolve_frequency, VJ_RELIEF_LIQUID_FRACTION_MAX,
                      VJ_RELIEF_VAPOUR_QUALITY_MIN)

# Longest release window used to find the maximum flammable footprint.
# All default Purple Book isolation branches last at least 120 s. Once that
# window is available, feeding a still longer release to the SLAB meander
# closure reduces its reported *peak* concentration and can make failed
# isolation look safer. Mass and fire duration still use the actual release;
# this cap applies only to the peak flammable-cloud calculation.
DISPERSION_MAX_S = 120.0
P_ATM = 101325.0

_ORDER = [Grade.MEASURED, Grade.PUBLISHED_VALIDATED,
          Grade.PUBLISHED_UNVALIDATED, Grade.ENGINEERING_JUDGEMENT,
          Grade.PLACEHOLDER]


class FlameModel(str, Enum):
    """Explicit model-form branches for GH2 jet-fire consequences."""
    MOLKOV_CONSERVATIVE = "molkov-conservative"
    MOLKOV_FIT = "molkov-fit"
    DELICHATSIOS = "delichatsios"


def weakest(grades: Iterable[Grade]) -> Grade:
    return max(grades, key=_ORDER.index)


# --------------------------------------------------------------------------

@dataclass
class IgnitionEnvironment:
    """The site's ignition sources, for Purple Book method A.

    Empty means not surveyed, and the source model refuses rather than
    returning zero. Societal Risk is required to use this method; the
    free field alternative is a bound, not the recommended calculation."""
    sources: list = field(default_factory=list)
    cloud_residence_s: float = 60.0

    def delayed(self, cloud_radius_m: float, x: float, y: float):
        return IS.IgnitionSourceSet(self.sources).delayed_probability(
            self.cloud_residence_s, cloud_radius_m, x, y)


@dataclass
class Weather:
    """One weather class with its wind sector probabilities."""
    label: str
    wind_m_s: float
    stability: str
    sectors: list[WeatherSector]
    temperature_c: float = 15.0
    relative_humidity: float = 75.0


@dataclass(frozen=True)
class TransientCouplingPolicy:
    """How a time-varying profile is reduced for steady consequence models.

    The downstream models accept one rate. Keeping separate choices for
    dispersion, ignition and fire makes the reduction explicit and lets a
    screening envelope be compared with a mass-equivalent calculation.
    """
    label: str
    dispersion: TR.RateBasis
    ignition: TR.RateBasis
    fire: TR.RateBasis

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("transient coupling policy label must not be empty")
        for name in ("dispersion", "ignition", "fire"):
            value = getattr(self, name)
            try:
                value = TR.RateBasis(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"unknown transient rate basis for {name}: {value!r}") \
                    from exc
            object.__setattr__(self, name, value)


TRANSIENT_SCREENING_ENVELOPE = TransientCouplingPolicy(
    label="screening-envelope",
    dispersion=TR.RateBasis.PEAK,
    ignition=TR.RateBasis.PEAK,
    fire=TR.RateBasis.PEAK)

TRANSIENT_MASS_EQUIVALENT = TransientCouplingPolicy(
    label="mass-equivalent",
    dispersion=TR.RateBasis.MASS_EQUIVALENT_MEAN,
    ignition=TR.RateBasis.MASS_EQUIVALENT_MEAN,
    fire=TR.RateBasis.MASS_EQUIVALENT_MEAN)


@dataclass(frozen=True)
class TransientCase:
    """One mutually exclusive profile branch for an exact scenario ID."""
    label: str
    profile: TR.Profile
    probability: float = 1.0


@dataclass(frozen=True)
class TransientAudit:
    """Trace of every profile reduction that changed a pipeline result."""
    scenario_id: str
    case_label: str
    probability: float
    policy_label: str
    duration_s: float
    initial_mass_kg: float
    released_mass_kg: float
    peak_rate_kg_s: float
    mass_equivalent_mean_rate_kg_s: float
    dispersion_basis: str
    dispersion_rate_kg_s: float
    dispersion_state_time_s: float
    ignition_basis: str
    ignition_rate_kg_s: float
    ignition_state_time_s: float
    fire_basis: str
    fire_rate_kg_s: float
    fire_state_time_s: float
    limited_by: str
    provenance_source: str
    provenance_grade: str


@dataclass(frozen=True)
class _WorkItem:
    scenario: Scenario
    blocking_branch: Optional[BL.IsolationBranch] = None
    transient_case: Optional[TransientCase] = None


def rotterdam_like(n_sectors: int = 12) -> list[Weather]:
    """A placeholder weather set: one class, uniform over sectors. Real work
    needs the Appendix 4.C frequency table for the actual site."""
    if n_sectors <= 0:
        raise ValueError("n_sectors must be positive")
    p = 1.0 / n_sectors
    return [Weather(
        label="D 5.0", wind_m_s=5.0, stability="D",
        sectors=[WeatherSector("D 5.0", (i * 360 / n_sectors,
                                         (i + 1) * 360 / n_sectors),
                               p_day=p, p_night=p)
                 for i in range(n_sectors)])]


def check_weather_closes(weather: list[Weather], *, tolerance: float = 1e-9
                          ) -> None:
    """Require the weather and sector probabilities to cover one year.

    A weather set is a partition of time, not an arbitrary multiplier. A
    set that sums to 0.44 silently scales every risk result by 0.44.
    """
    for item in weather:
        if not math.isfinite(item.wind_m_s) or item.wind_m_s <= 0.0:
            raise ValueError("weather wind speed must be finite and positive")
        if (not math.isfinite(item.temperature_c)
                or item.temperature_c <= -273.15):
            raise ValueError("weather temperature must be above absolute zero")
        if (not math.isfinite(item.relative_humidity)
                or not 0.0 <= item.relative_humidity <= 100.0):
            raise ValueError("relative humidity must be between 0 and 100 percent")
        if str(item.stability).upper() not in {"A", "B", "C", "D", "E", "F"}:
            raise ValueError("weather stability must be a Pasquill class A-F")
    probabilities = [s.pm_pphi for w in weather for s in w.sectors]
    if not probabilities:
        raise ValueError("weather must contain at least one wind sector")
    if any(not math.isfinite(p) or p < 0.0 for p in probabilities):
        raise ValueError("weather probabilities must be finite and non-negative")
    total = sum(probabilities)
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=tolerance):
        raise ValueError(
            f"weather probabilities sum to {total:.12g}, not 1.0")


@dataclass
class PipelineResult:
    grid: IRGrid
    contributions: list[RiskContribution]
    societal: list[SocietalOutcome]
    grade: Grade
    grade_by_route: dict[str, str]
    n_scenarios: int
    n_computed: int
    n_skipped: int
    coverage: Coverage
    refuse_policy: RefusePolicy
    flame_model: FlameModel
    # Fragment ranges for scenarios that rupture a vessel. Ranges only:
    # lethality is refused, see fragments.lethality.
    fragment_throws: list = field(default_factory=list)
    escalation: Optional[eqd.EscalationGraph] = None
    # What the chosen ignition scheme gave, beside what HIAD records for
    # the same medium. Not a correction; see hiad.WHY_NOT_A_CORRECTION.
    ignition_checks: list = field(default_factory=list)
    # Exact record of supplied transient profiles and the single-rate
    # reductions used by consequence models.
    transient_audit: list[TransientAudit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def statement(self) -> str:
        parts = ", ".join(f"{k}={v}" for k, v in
                          sorted(self.grade_by_route.items()))
        return (f"max IR {self.max_ir:.3e}/yr, weakest grade "
                f"{self.grade.value} ({parts}). " + self.coverage.statement())

    @property
    def max_ir(self) -> float:
        return self.grid.max_ir()

    def fn(self):
        return fn_curve(self.societal)

    def claim_boundary(self) -> dict:
        """Publication limits, not an implemented dual-evidence validator.

        Source certificates and QOI benchmark outcomes are not yet joined
        to this runtime. A numerical criterion comparison cannot confer
        facility validation while those interfaces remain disconnected.
        """
        return {
            "status": "ENGINEERING_SCREENING_ONLY",
            "dual_evidence_gate": "NOT_INTEGRATED",
            "facility_validation": "WITHHELD",
            "allowed": ["declared engineering sensitivity",
                        "commissioning-test design"],
            "not_claimable_as": [
                "validated absolute facility risk or facility acceptance",
                "validated radiation or thermal-damage prediction",
                "validated time-resolved release-dispersion-radiation chain",
                "implemented and validated dual-evidence claim gate",
            ],
            "open_model_issues": [
                "radiation power form retains unexplained factor 22.7",
                "notional-nozzle temperature is not a total-energy closure",
                "loss-of-vacuum relief phase and energy closure remain unresolved",
                "Ruggles plot-to-operating-coordinate mapping remains unresolved",
            ],
        }


# --------------------------------------------------------------------------

def _dispersion(sc: Scenario, rate_kg_s: float, wx, duration_s: float,
                disch=None, available_mass_kg: float | None = None):
    """Dispatch with source-state and finite-inventory limits preserved."""
    if sc.physics_route is PhysicsRoute.SLABX_LH2:
        liquid_fraction = (
            VJ_RELIEF_LIQUID_FRACTION_MAX
            if sc.release_path is ReleasePath.VIA_RELIEF
            else 0.0 if sc.service is Service.COLD_GH2 else 0.559)
        return dcache.get(dcache.key_of(
            rate_kg_s, wx.wind_m_s, wx.stability, wx.temperature_c,
            wx.relative_humidity, duration_s,
            max(sc.position.z, 0.5), sc.hole_diameter_m * 1000.0,
            liquid_fraction))
    if sc.physics_route is PhysicsRoute.GH2_JET and disch is not None:
        rho_t = disch.mass_flux_kg_m2s / max(disch.velocity_m_s, 1e-9)
        return gh2_jet.dispersion(
            rate_kg_s, wx.wind_m_s, temperature_c=wx.temperature_c,
            relative_humidity=wx.relative_humidity, duration_s=duration_s,
            stability=wx.stability,
            throat_pressure_pa=disch.throat_pressure_pa,
            throat_velocity_m_s=disch.velocity_m_s,
            throat_density_kg_m3=rho_t,
            hole_diameter_m=sc.hole_diameter_m,
            available_mass_kg=available_mass_kg)
    raise NotImplementedError(
        f"no dispersion model for route {sc.physics_route.value}. "
        f"COLD_GH2 (roughly 30-250 K, the vaporiser band) has no validated "
        f"model in the literature; it is a declared gap, not an omission.")


def _gh2_flammable_profile(sc: Scenario, disch):
    """Schefer equations 9 and 11 as a plan-view axial contour."""
    if (sc.physics_route is not PhysicsRoute.GH2_JET
            or sc.orientation is not Orientation.HORIZONTAL):
        return None
    rho_t = disch.mass_flux_kg_m2s / max(disch.velocity_m_s, 1e-9)
    nozzle = fire.notional_nozzle(
        disch.rate_kg_s, disch.throat_pressure_pa, disch.velocity_m_s,
        rho_t, sc.hole_diameter_m)
    return gh2_jet.flammable_profile(
        gh2_jet.LFL_MASS_FRACTION, nozzle)


def _fireball_for(sc: Scenario, released_kg: float):
    """Hydrogen-specific fireball. Tank rupture for the gas side, LH2
    spill for the cryogenic side; the two scale differently because one
    burns supersonically and the other does not."""
    if (released_kg <= 0.0
            or sc.release_kind is not ReleaseKind.INSTANTANEOUS):
        return None
    if sc.service is Service.GH2:
        return FB.gh2_tank_rupture_fireball(released_kg,
                                            conservative=True)
    if sc.service is Service.LH2:
        return FB.lh2_spill_fireball(released_kg, conservative=True)
    return None


def _flame_for(sc: Scenario, disch,
               flame_model: FlameModel = FlameModel.MOLKOV_CONSERVATIVE):
    """Jet flame for GH2 and a relief stream known to be vapour-rich.

    An ordinary LH2 breach forms a two-phase jet and burn-back region that
    the gas correlation does not cover. The VJ relief route is treated
    separately because its conservative source state is already 55% vapour.
    """
    if (sc.service is not Service.GH2
            and sc.release_path is not ReleasePath.VIA_RELIEF):
        return None
    rho_t = disch.mass_flux_kg_m2s / max(disch.velocity_m_s, 1e-9)
    nz = fire.notional_nozzle(disch.rate_kg_s, disch.throat_pressure_pa,
                              disch.velocity_m_s, rho_t,
                              sc.hole_diameter_m)
    flame_model = FlameModel(flame_model)
    if flame_model is FlameModel.DELICHATSIOS:
        return fire.flame_length(
            disch.rate_kg_s, nz, hole_diameter_m=sc.hole_diameter_m,
            model="delichatsios", conservative=False)
    return fire.flame_length(
        disch.rate_kg_s, nz, hole_diameter_m=sc.hole_diameter_m,
        model="molkov",
        conservative=(flame_model is FlameModel.MOLKOV_CONSERVATIVE))


def sector_weight(wx) -> float:
    """Frequency share this weather class carries, for coverage accounting."""
    return sum(s.pm_pphi for s in wx.sectors)


def _scenario_discharge(sc: Scenario, pressure_pa: float,
                        temperature_k: float, *, liquid: bool = False):
    """Select the configured source path without changing the default one."""
    if sc.upstream_line is not None:
        if liquid:
            raise ValueError(
                f"{sc.scenario_id}: finite upstream-line source covers GH2 "
                "only; two-phase/LH2 flow requires a different model")
        line = sc.upstream_line
        return line_discharge(
            pressure_pa, temperature_k, "Hydrogen", sc.hole_diameter_m,
            line.length_m, line.diameter_m, roughness_m=line.roughness_m,
            minor_loss_k=line.minor_loss_k,
            Cd=sc.discharge_coefficient)
    if sc.release_path is ReleasePath.VIA_RELIEF:
        return discharge(
            pressure_pa, None, "ParaHydrogen", sc.hole_diameter_m,
            Cd=sc.discharge_coefficient,
            stagnation_quality=VJ_RELIEF_VAPOUR_QUALITY_MIN)
    if liquid:
        return discharge(pressure_pa, None, "ParaHydrogen",
                         sc.hole_diameter_m, Cd=sc.discharge_coefficient,
                         saturated_liquid=True)
    return discharge(pressure_pa, temperature_k, "Hydrogen",
                      sc.hole_diameter_m, Cd=sc.discharge_coefficient)


def _source(sc: Scenario, isolation_s: float):
    """Discharge rate and released mass for one scenario."""
    d = _scenario_discharge(
        sc, sc.pressure_pa, sc.temperature_k,
        liquid=(sc.service is Service.LH2))
    rel = released_mass(d.rate_kg_s, sc.available_mass_kg, isolation_s)
    return d, rel


def _profile_discharge(sc: Scenario, profile: TR.Profile,
                       target_rate_kg_s: float):
    """Discharge properties at the profile state nearest a chosen rate.

    Consequence models need throat pressure, velocity and density as well
    as mass rate. Reusing the initial source state for a late-time mean
    would mix two different states. The nearest recorded profile state is
    therefore re-evaluated, then its mass flux is scaled by the small
    residual needed to hit the exact representative rate.
    """
    if not math.isfinite(target_rate_kg_s) or target_rate_kg_s <= 0.0:
        raise ValueError("transient representative rate must be positive")
    candidates = [s for s in profile.steps
                  if s.rate_kg_s > 0.0 and s.pressure_pa > P_ATM]
    if not candidates:
        raise ValueError(
            "transient profile has no positive outward-flow state above "
            "ambient pressure")
    step = min(candidates, key=lambda s: abs(s.rate_kg_s
                                             - target_rate_kg_s))
    d = _scenario_discharge(
        sc, step.pressure_pa, step.temperature_k,
        liquid=(step.phase is not TR.Phase.GAS))
    if d.rate_kg_s <= 0.0:
        raise ValueError(
            "transient representative state produced no outward discharge")
    scale = target_rate_kg_s / d.rate_kg_s
    return replace(
        d, rate_kg_s=target_rate_kg_s,
        mass_flux_kg_m2s=d.mass_flux_kg_m2s * scale,
        note=(d.note + " Transient coupling: throat properties use the "
              f"nearest profile state at t={step.t_s:g} s; mass flux is "
              "scaled to the selected representative rate.")), step


def _validate_transient_cases(
        scenarios: list[Scenario],
        transient_cases: Optional[dict[str, list[TransientCase]]],
        transient_policy: Optional[TransientCouplingPolicy]
        ) -> dict[str, list[TransientCase]]:
    """Validate the explicit scenario-to-profile boundary."""
    cases = transient_cases or {}
    if not cases:
        if transient_policy is not None:
            raise ValueError(
                "transient_policy was supplied without transient_cases")
        return {}
    if transient_policy is None:
        raise ValueError(
            "transient_cases require an explicit TransientCouplingPolicy")

    by_id = {s.scenario_id: s for s in scenarios}
    unknown = sorted(set(cases) - set(by_id))
    if unknown:
        raise ValueError(
            "transient profile references unknown scenario IDs: "
            + ", ".join(unknown))

    for scenario_id, branches in cases.items():
        sc = by_id[scenario_id]
        if not sc.computable or not math.isfinite(sc.frequency_per_year):
            raise ValueError(
                f"transient profile targets non-computable scenario "
                f"{scenario_id}")
        if sc.release_kind is not ReleaseKind.CONTINUOUS:
            raise ValueError(
                f"transient profile cannot replace instantaneous scenario "
                f"{scenario_id}")
        if not branches:
            raise ValueError(
                f"transient scenario {scenario_id} must contain a case")
        labels = [c.label.strip() for c in branches]
        if any(not label for label in labels):
            raise ValueError("transient case labels must not be empty")
        if len(labels) != len(set(labels)):
            raise ValueError(
                f"transient case labels must be unique for {scenario_id}")
        probabilities = [c.probability for c in branches]
        if any(not math.isfinite(p) or p <= 0.0 for p in probabilities):
            raise ValueError(
                "transient case probabilities must be finite and positive")
        total = sum(probabilities)
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"transient case probabilities for {scenario_id} sum to "
                f"{total:.12g}, not 1.0")
        for case in branches:
            case.profile.validate()
            if case.profile.initial_mass_kg > sc.available_mass_kg + max(
                    1e-6, sc.available_mass_kg * 1e-9):
                raise ValueError(
                    f"transient profile {scenario_id}/{case.label} starts "
                    "with more mass than the scenario inventory")
            if case.profile.released_kg > sc.available_mass_kg + max(
                    1e-6, sc.available_mass_kg * 1e-9):
                raise ValueError(
                    f"transient profile {scenario_id}/{case.label} releases "
                    "more mass than the scenario inventory")
    return cases


def _merge_exposure(previous: Optional[eqd.Exposure], current: eqd.Exposure
                    ) -> eqd.Exposure:
    """Combine scenario/weather exposures without inventing probabilities."""
    if previous is None:
        return current
    return eqd.Exposure(
        heat_flux_w_m2=max(previous.heat_flux_w_m2,
                           current.heat_flux_w_m2),
        overpressure_pa=max(previous.overpressure_pa,
                            current.overpressure_pa),
        inside_fireball=(previous.inside_fireball or
                         current.inside_fireball),
        inside_flammable_cloud=(previous.inside_flammable_cloud or
                                current.inside_flammable_cloud),
        within_fragment_range=(previous.within_fragment_range or
                                current.within_fragment_range),
        possible_flame_contact=(previous.possible_flame_contact or
                                current.possible_flame_contact),
        overpressure_is_lower_bound=(previous.overpressure_is_lower_bound or
                                     current.overpressure_is_lower_bound),
        distance_m=current.distance_m)


def _record_equipment_exposures(
        store: dict[tuple[str, str], eqd.Exposure], sc: Scenario,
        targets: list, wx: Weather, lfl_m: float, r03_m: float, r01_m: float,
        flame, spill, fireball, fragment_throw, fire_duration_s: float,
        elevated_upward_vent: bool, flammable_profile=None) -> None:
    """Record worst first-order source-to-equipment exposure.

    This is a screening graph. It carries thresholds and reach, not a
    conditional probability that a damaged target subsequently releases.
    """
    for target in targets:
        if target.tag == sc.tag:
            continue
        dx = target.position.x - sc.position.x
        dy = target.position.y - sc.position.y
        distance = math.hypot(dx, dy)

        heat = 0.0
        possible_contact = False
        if flame is not None:
            fluxes = fieldmod.directional_flux_field(
                flame, np.asarray([dx]), np.asarray([dy]),
                height_m=max(target.position.z, 1.0),
                relative_humidity=wx.relative_humidity / 100.0,
                orientation=sc.orientation.value,
                source_height_m=sc.position.z,
                azimuth_deg=sc.release_azimuth_deg).by_bearing.ravel()
            contact = np.isposinf(fluxes)
            # Equipment screening has no orientation probabilities.
            # Retain possible contact and the worst external flux.
            possible_contact = bool(contact.any() and not contact.all())
            heat = (float("inf") if contact.all() else
                    float(fluxes[~contact].max()))
        if spill is not None:
            heat = max(heat, SF.burn_back_heat_flux(
                spill, max(distance, 1e-6), max(fire_duration_s, 1.0),
                wx.relative_humidity / 100.0, True))

        # The pipeline's multi-energy anchors are 0.30 and 0.10 barg.
        # They support a banded exposure, not interpolation to a fabricated
        # pressure curve.
        overpressure = (
            0.0 if elevated_upward_vent else
            30.0e3 if distance <= r03_m else
            10.0e3 if distance <= r01_m else 0.0)
        inside_cloud = False
        if not elevated_upward_vent:
            if flammable_profile is not None:
                inside_cloud = fieldmod.point_in_directional_footprint(
                    dx, dy, *flammable_profile, sc.release_azimuth_deg)
            else:
                inside_cloud = distance <= lfl_m
        current = eqd.Exposure(
            heat_flux_w_m2=heat,
            overpressure_pa=overpressure,
            inside_fireball=(fireball is not None
                             and distance <= fireball.radius_m),
            inside_flammable_cloud=inside_cloud,
            within_fragment_range=(
                fragment_throw is not None
                and distance <= fragment_throw.range_high_m),
            distance_m=distance)
        current = replace(
            current, possible_flame_contact=possible_contact,
            overpressure_is_lower_bound=(overpressure > 0.0))
        key = (sc.tag, target.tag)
        store[key] = _merge_exposure(store.get(key), current)


def run(site: Site,
        weather: Optional[list[Weather]] = None,
        half_extent_m: float = 200.0,
        cell_size_m: float = 25.0,
        ignition_scheme: IgnitionScheme = IgnitionScheme.HYRAM,
        ignition_environment: Optional[IgnitionEnvironment] = None,
        blocking: BL.BlockingSystem = BL.BlockingSystem.AUTOMATIC,
        isolation_s: Optional[float] = None,
        population_per_cell: float = 0.0,
        refuse_policy: RefusePolicy = RefusePolicy.EXCLUDE,
        transient_cases: Optional[dict[str, list[TransientCase]]] = None,
        transient_policy: Optional[TransientCouplingPolicy] = None,
        flame_model: FlameModel = FlameModel.MOLKOV_CONSERVATIVE,
        ) -> PipelineResult:
    try:
        flame_model = FlameModel(flame_model)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unknown flame model: {flame_model!r}") from exc
    if not math.isfinite(half_extent_m) or half_extent_m <= 0.0:
        raise ValueError("half_extent_m must be finite and positive")
    if not math.isfinite(cell_size_m) or cell_size_m <= 0.0:
        raise ValueError("cell_size_m must be finite and positive")
    if cell_size_m > 2.0 * half_extent_m:
        raise ValueError("cell_size_m cannot exceed the full grid width")
    if not math.isfinite(population_per_cell) or population_per_cell < 0.0:
        raise ValueError("population_per_cell must be finite and non-negative")
    if isolation_s is not None and (
            not math.isfinite(isolation_s) or isolation_s <= 0.0):
        raise ValueError("isolation_s must be finite and positive")
    if ignition_environment is not None and (
            not math.isfinite(ignition_environment.cloud_residence_s)
            or ignition_environment.cloud_residence_s <= 0.0):
        raise ValueError("cloud residence time must be finite and positive")
    if weather is None:
        weather = rotterdam_like()
    check_weather_closes(weather)
    grid = IRGrid.square(half_extent_m, cell_size_m)
    contributions: list[RiskContribution] = []
    societal: list[SocietalOutcome] = []
    grades: list[Grade] = []
    notes: list[str] = []
    transient_audit: list[TransientAudit] = []
    coverage = Coverage()
    ignition_seen: dict = {}
    frag_seen: dict = {}
    footprint_note_seen: set[str] = set()
    route_grades: dict[str, list] = {}

    # Purple Book 4.4.1 credits a blocking system by SHORTENING the
    # release, not by removing the outcome, and its failure on demand is
    # 0.001 for an automatic system. Both branches are carried: on
    # failure the release is not shortened at all and runs to inventory.
    #
    # HyRAM credits the same barrier the other way, with a probability of
    # successful detection and isolation of 0.9 that multiplies the whole
    # outcome away. Applying that here as well would credit the same
    # valves twice.
    #
    # The isolation time also had no source. It defaulted to 30 s, which
    # is four times faster than the 120 s the book allows for its fastest
    # grade, a fully automatic system needing no operator action.
    spec = BL.BLOCKING_DEFAULTS[blocking]
    if isolation_s is not None:
        spec = BL.BlockingSpec(spec.kind, isolation_s,
                               spec.failure_on_demand, spec.description)
    scenarios = enumerate_scenarios(site)
    transient_cases = _validate_transient_cases(
        scenarios, transient_cases, transient_policy)
    bin_index = {b.label: i for i, b in enumerate(HYRAM_BINS)}
    n_computed = n_skipped = 0
    pop_in, pop_out = dmg.population_fractions()
    equipment_targets = site.all_components()
    equipment_exposures: dict[tuple[str, str], eqd.Exposure] = {}

    work_items: list[_WorkItem] = []
    for sc in scenarios:
        if not sc.computable or not math.isfinite(sc.frequency_per_year):
            n_skipped += 1
            if not math.isfinite(sc.frequency_per_year):
                coverage.record_unquantified(sc.scenario_id, sc.tag)
            else:
                coverage.record_no_data(sc.frequency_per_year)
            continue
        n_computed += 1
        if sc.scenario_id in transient_cases:
            # A supplied profile already contains isolation, inventory
            # depletion and any other time-dependent limit. Applying the
            # ordinary blocking tree as well would credit isolation twice.
            for case in transient_cases[sc.scenario_id]:
                work_items.append(_WorkItem(
                    scenario=sc.model_copy(update={
                        "frequency_per_year": (sc.frequency_per_year
                                               * case.probability)}),
                    transient_case=case))
            continue
        grades.append(BL.BLOCKING_PROV.grade)
        scenario_spec = spec
        if blocking is not BL.BlockingSystem.NONE and isolation_s is None:
            scenario_spec = BL.BlockingSpec(
                spec.kind, sc.isolation_time_s, spec.failure_on_demand,
                f"{spec.description}; section-specific isolation time")
        for branch in BL.branches(blocking, scenario_spec):
            if branch.probability <= 0.0:
                continue
            # Consequences are nonlinear in release duration and mass.
            # Preserve the event-tree branches through the consequence
            # calculation and apply their probabilities to frequency.
            work_items.append(_WorkItem(
                scenario=sc.model_copy(update={
                    "frequency_per_year": (sc.frequency_per_year
                                           * branch.probability)}),
                blocking_branch=branch))

    for item in work_items:
        sc = item.scenario
        grades.append(sc.grade)
        res = resolve_frequency(sc.primitive, sc.service)
        src_key = ((sc.primitive, res.fuel_used), bin_index[sc.bin_label]) \
            if res.fuel_used is not None else None
        if item.transient_case is None:
            if item.blocking_branch is None:
                raise RuntimeError("pipeline work item has no release branch")
            d, released = _source(
                sc, item.blocking_branch.isolation_time_s)
            d_dispersion = d_ignition = d_fire = d
            release_duration_s = released.duration_s
            released_mass_kg = released.released_kg
        else:
            case = item.transient_case
            profile = case.profile
            if transient_policy is None:
                raise RuntimeError("validated transient policy is missing")
            dispersion_rate = profile.representative_rate(
                transient_policy.dispersion)
            ignition_rate = profile.representative_rate(
                transient_policy.ignition)
            fire_rate = profile.representative_rate(transient_policy.fire)
            d_dispersion, dispersion_step = _profile_discharge(
                sc, profile, dispersion_rate)
            d_ignition, ignition_step = _profile_discharge(
                sc, profile, ignition_rate)
            d_fire, fire_step = _profile_discharge(sc, profile, fire_rate)
            d = d_dispersion
            release_duration_s = profile.duration_s
            released_mass_kg = profile.released_kg
            grades.append(profile.provenance.grade)
            route_grades.setdefault(sc.physics_route.value, []).append(
                profile.provenance.grade)
            transient_audit.append(TransientAudit(
                scenario_id=sc.scenario_id,
                case_label=case.label,
                probability=case.probability,
                policy_label=transient_policy.label,
                duration_s=profile.duration_s,
                initial_mass_kg=profile.initial_mass_kg,
                released_mass_kg=profile.released_kg,
                peak_rate_kg_s=profile.peak_rate_kg_s,
                mass_equivalent_mean_rate_kg_s=profile.mean_rate_kg_s(),
                dispersion_basis=transient_policy.dispersion.value,
                dispersion_rate_kg_s=dispersion_rate,
                dispersion_state_time_s=dispersion_step.t_s,
                ignition_basis=transient_policy.ignition.value,
                ignition_rate_kg_s=ignition_rate,
                ignition_state_time_s=ignition_step.t_s,
                fire_basis=transient_policy.fire.value,
                fire_rate_kg_s=fire_rate,
                fire_state_time_s=fire_step.t_s,
                limited_by=profile.limited_by,
                provenance_source=profile.provenance.source,
                provenance_grade=profile.provenance.grade.value))
            notes.append(
                f"{sc.scenario_id}/{case.label}: supplied transient profile "
                f"replaced ordinary blocking branches; policy "
                f"{transient_policy.label}, released "
                f"{profile.released_kg:.6g} kg over "
                f"{profile.duration_s:.6g} s")

        if d.flow_model != "sharp-hole":
            notes.append(
                f"{sc.scenario_id}: {d.flow_model}; line outlet "
                f"{d.line_outlet_pressure_pa:.6g} Pa, pressure loss "
                f"{d.line_pressure_drop_pa:.6g} Pa, Darcy f="
                f"{d.line_friction_factor:.5g}, Re="
                f"{d.line_reynolds:.5g}, Mach="
                f"{d.line_outlet_mach:.4f}")
        if (sc.discharge_coefficient_basis
                is not DischargeCoefficientBasis.CONSERVATIVE_DEFAULT):
            notes.append(
                f"{sc.scenario_id}: Cd={sc.discharge_coefficient:g}; basis="
                f"{sc.discharge_coefficient_basis.value}; source/test="
                f"{sc.discharge_coefficient_note}")

        for wx in weather:
            # Dispersion duration is the release duration, which is the
            # isolation time OR the time to empty the section, whichever
            # comes first. Passing the isolation time alone sent infinity
            # for the no-blocking case, and slabx averages concentration
            # over that window: the LFL distance collapsed from 62 m to
            # 7 m, so removing the blocking system made the site SAFER.
            # Physically an infinite averaging window does dilute to
            # nothing; the error was treating an unbounded isolation time
            # as an unbounded release.
            _dur = min(release_duration_s, DISPERSION_MAX_S)
            disp = _dispersion(sc, d_dispersion.rate_kg_s, wx, _dur,
                               d_dispersion, available_mass_kg=released_mass_kg)
            if disp.status == "STEADY_REFERENCE_ONLY":
                notes.append(f"{sc.scenario_id}: steady GH2 geometry is a reference "
                             "envelope only; cloud build-up is unresolved and "
                             "flammable mass requires the declared refusal policy")
            grades.append(disp.provenance.grade)
            route_grades.setdefault(sc.physics_route.value, []).append(
                disp.provenance.grade)
            route_grades[sc.physics_route.value].append(sc.grade)
            w = sector_weight(wx)

            # The gate. A refused quantity has no value; resolve() forces a
            # policy decision rather than letting None flow downstream.
            # Bounds do not compose. A ground-level distance can be
            # bounded at the premise edge; the flammable mass cannot,
            # because the quantity that is unresolved in the buoyant
            # regime is the rise itself. BOUND therefore rescues the
            # flash fire branch and not the explosion branch, and the
            # shortfall is recorded rather than papered over.
            def _take(g):
                try:
                    return g.resolve(refuse_policy), None
                except RefusedError as exc:
                    return None, str(exc).split(".")[0]

            lfl, why_l = _take(disp.lfl_distance_m)
            mass, why_m = _take(disp.flammable_mass_kg)
            mass_refused = mass is None
            if why_m and lfl is not None:
                notes.append(f"{sc.scenario_id} @ u={wx.wind_m_s:.1f}: "
                             f"distance bounded but mass has no bound; "
                             f"explosion branch dropped")
            if lfl is None:
                coverage.record_refused(sc.frequency_per_year * w,
                                        disp.lfl_distance_m.quantity,
                                        sc.scenario_id)
                uc = ("n/a (outside fit range)" if disp.u_crit_m_s is None
                      else f"{disp.u_crit_m_s:.2f}")
                notes.append(
                    f"{sc.scenario_id} @ u={wx.wind_m_s:.1f}: REFUSE "
                    f"(u_crit={uc}) -> {refuse_policy.value}")
                continue
            if mass_refused:
                # The ground-level LFL bound is still a usable conservative
                # flash-fire footprint.  Only the explosion branch needs
                # flammable mass, so retain the former and zero the latter.
                mass = 0.0
            elif disp.flammable_mass_kg.refused:
                notes.append(f"{sc.scenario_id}: flammable mass is an inventory "
                             f"bound, not a prediction: {disp.flammable_mass_kg.bound_basis}")
                grades.append(Grade.ENGINEERING_JUDGEMENT)
            if disp.lfl_distance_m.refused:
                notes.append(
                    f"{sc.scenario_id} @ u={wx.wind_m_s:.1f}: bounded, "
                    f"not predicted ({disp.lfl_distance_m.bound_basis[:40]}...)")
                grades.append(Grade.ENGINEERING_JUDGEMENT)
            # Each blocking or transient branch is evaluated at its own
            # released mass; its probability is already carried in
            # sc.frequency_per_year. Averaging mass before fireball,
            # ignition and damage models would not preserve their
            # nonlinear response.
            _mass = released_mass_kg
            instantaneous = sc.release_kind is ReleaseKind.INSTANTANEOUS
            delayed_conditional = None
            if ignition_scheme is IgnitionScheme.PURPLE_SOURCES:
                if ignition_environment is None:
                    raise ValueError(
                        "PURPLE_SOURCES is Purple Book 4.7.2 method A and "
                        "needs the site's ignition sources. Supply an "
                        "IgnitionEnvironment, or choose PURPLE for the "
                        "free field bound.")
                g = ignition_environment.delayed(lfl, sc.position.x,
                                                 sc.position.y)
                if g.refused:
                    coverage.record_refused(
                        sc.frequency_per_year * w,
                        "delayed_ignition_probability", sc.scenario_id)
                    notes.append(f"{sc.scenario_id}: {g.reason[:80]}")
                    continue
                delayed_conditional = g.value
                grades.append(IS.IGNITION_PROV.grade)
            if mass_refused:
                coverage.record_refused(
                    sc.frequency_per_year * w,
                    disp.flammable_mass_kg.quantity, sc.scenario_id)
            else:
                coverage.record_evaluated(sc.frequency_per_year * w)
            tree = build_ignition_tree(
                ReleaseType.INSTANTANEOUS if instantaneous
                else ReleaseType.CONTINUOUS,
                _mass if instantaneous else d_ignition.rate_kg_s,
                ignition_scheme,
                # A cryogenic liquid release forms a pool; a gas release
                # does not. Without this the pool fire branch of the tree
                # is never reached and the spill fire model is unreachable
                # for exactly the service it was written for.
                forms_pool=(sc.service is Service.LH2
                            and sc.release_path is not
                            ReleasePath.VIA_RELIEF),
                delayed_conditional=delayed_conditional)
            # fire duration is the release duration; exposure is capped
            # separately at 20 s by Purple Book 5.2.3 note 3
            # Record what the scheme gave, once per medium and band, so
            # the comparison against recorded incidents travels with the
            # result rather than being looked up separately.
            _key = (sc.service.value, sc.release_kind.value,
                    tree.probabilities.band)
            if _key not in ignition_seen:
                ignition_seen[_key] = HIAD.check_scheme(
                    ignition_scheme.value, tree.p_ignited,
                    "LH2" if sc.service is Service.LH2 else "GH2")

            t_fire = min(release_duration_s, dmg.MAX_EXPOSURE_S)
            r03, r01 = multi_energy_radii(
                mass * fire.H2_HEAT_OF_COMBUSTION)
            flame = _flame_for(sc, d_fire, flame_model)
            if flame is not None:
                grades.append(fire.FIRE_PROV.grade)

            # Effect fields are computed once for the whole grid, not per
            # cell: the physics does not depend on which receptor is being
            # asked about, only on the offset, so the cell loop was pure
            # overhead. Profiling had 83% of run time in the radiation
            # stack at 1.8 million scalar calls for a 13x13 grid.
            GX, GY = np.meshgrid(grid.x, grid.y)
            DX, DY = GX - sc.position.x, GY - sc.position.y
            RR = np.hypot(DX, DY)

            fields: dict = {}
            elevated_upward_vent = (
                sc.release_path is ReleasePath.VIA_VENT
                and sc.orientation is Orientation.UP
                and sc.position.z > 0.0)
            flammable_profile = _gh2_flammable_profile(sc, d_dispersion)
            if elevated_upward_vent:
                fields[Outcome.FLASH_FIRE] = fieldmod.coverage_field(
                    DX, DY, grid.cell_size_m, 0.0)
            elif flammable_profile is not None:
                fields[Outcome.FLASH_FIRE] = (
                    fieldmod.directional_footprint_field(
                        DX, DY, grid.cell_size_m, *flammable_profile,
                        azimuth_deg=sc.release_azimuth_deg))
                if (sc.release_azimuth_deg is None
                        and sc.scenario_id not in footprint_note_seen):
                    footprint_note_seen.add(sc.scenario_id)
                    grades.append(Grade.ENGINEERING_JUDGEMENT)
                    route_grades[sc.physics_route.value].append(
                        Grade.ENGINEERING_JUDGEMENT)
                    notes.append(
                        f"{sc.scenario_id}: horizontal release azimuth was "
                        "not supplied; the Schefer eq.11 footprint was "
                        "averaged uniformly over 12 bearings for individual "
                        "risk, while equipment escalation retains the "
                        "conservative all-bearing envelope")
            else:
                fields[Outcome.FLASH_FIRE] = fieldmod.coverage_field(
                    DX, DY, grid.cell_size_m, lfl)
            if flame is not None:
                fields[Outcome.JET_FIRE] = fieldmod.directional_flux_field(
                    flame, DX, DY,
                    relative_humidity=wx.relative_humidity / 100.0,
                    orientation=sc.orientation.value,
                    source_height_m=sc.position.z,
                    azimuth_deg=sc.release_azimuth_deg)
            expl = (np.zeros_like(RR) if elevated_upward_vent else
                    np.where(RR <= r03, 0.35,
                             np.where(RR <= r01, 0.15, 0.0)))
            fields[Outcome.EXPLOSION] = expl

            # Fireball. Makarov et al. find the hazard distance set by the
            # fireball SIZE rather than by thermal dose: outside it the
            # second-degree burn dose was never reached, and inside it the
            # outcome is not a flux. So the field is coverage of the cell
            # by the fireball footprint, graded as 6.2.6 note 1 asks.
            # Ignited spill, for liquid releases that form a pool.
            _sf = None
            if (sc.service is Service.LH2 and mass > 0.0
                    and not instantaneous
                    and sc.release_path is not ReleasePath.VIA_RELIEF):
                _sf = SF.spill_fire(d_fire.rate_kg_s, mass)
                _dur = max(min(t_fire, dmg.MAX_EXPOSURE_S), 1.0)
                fields[Outcome.POOL_FIRE] = np.vectorize(
                    lambda rr: SF.burn_back_heat_flux(
                        _sf, float(rr), _dur,
                        wx.relative_humidity / 100.0, True))(RR)
                grades.append(SF.SPILL_FIRE_PROV.grade)

            # Vessel rupture throws pieces of the vessel. Enumerated as
            # a range, not as a lethality: nothing here predicts how a
            # vessel comes apart, and the Purple Book gives no fragment
            # lethality relation.
            if (instantaneous and sc.primitive is Primitive.VESSEL
                    and sc.scenario_id not in frag_seen):
                # No bare except here. A swallowed exception hid that
                # Scenario carries no pressure attribute at all, and the
                # branch silently produced nothing.
                _V = sc.available_mass_kg / 70.8
                _P = d.throat_pressure_pa if d.throat_pressure_pa > P_ATM \
                    else P_ATM * 2.0
                _Em = BLAST.mechanical_energy(_V, _P)
                _shell = 7850.0 * 0.010 * (6.0 * _V ** (2.0 / 3.0))
                frag_seen[sc.scenario_id] = FRAG.fragment_throw(
                    _Em, _shell, 4)
                grades.append(FRAG.FRAGMENT_PROV.grade)

            fb = _fireball_for(sc, _mass)
            if fb is not None:
                fields[Outcome.BLEVE] = fieldmod.coverage_field(
                    DX, DY, grid.cell_size_m, fb.radius_m)
                grades.append(fb.provenance.grade)

            _record_equipment_exposures(
                equipment_exposures, sc, equipment_targets, wx, lfl,
                r03, r01, flame, _sf, fb, frag_seen.get(sc.scenario_id),
                t_fire, elevated_upward_vent, flammable_profile)

            for sector in wx.sectors:
                for ev in tree.events:
                    if ev.outcome is Outcome.NO_IGNITION:
                        continue
                    pe, fin, fout = _damage_field(ev.outcome, fields, t_fire)
                    if pe is None:
                        continue
                    nz = np.nonzero((pe > 0.0) | (fin > 0.0) | (fout > 0.0))
                    n_cell_deaths = 0.0
                    for iy, ix in zip(*nz):
                        c = RiskContribution(
                            loc_id=sc.scenario_id, weather_class=wx.label,
                            sector_deg=sector.sector_deg,
                            ignition_event=ev.outcome.value,
                            pm_pphi=sector.pm_pphi, p_ignition=ev.probability,
                            p_death=float(pe[iy, ix]),
                            frequency_per_year=sc.frequency_per_year,
                            route=PdRoute.FLAMMABLE, source_key=src_key,
                            receptor_id=(int(ix), int(iy)))
                        grid.add(int(ix), int(iy), c.delta_ir)
                        contributions.append(c)
                        if population_per_cell > 0.0:
                            n_cell_deaths += (
                                float(fin[iy, ix]) * pop_in
                                + float(fout[iy, ix]) * pop_out
                            ) * population_per_cell
                    if n_cell_deaths > 0.0:
                        societal.append(SocietalOutcome(
                            frequency_per_year=(sc.frequency_per_year
                                                * sector.pm_pphi
                                                * ev.probability),
                            n_deaths=n_cell_deaths))

    def _equipment_exposure(source, target):
        distance = math.hypot(target.position.x - source.position.x,
                              target.position.y - source.position.y)
        return equipment_exposures.get(
            (source.tag, target.tag), eqd.Exposure(distance_m=distance))

    escalation = eqd.build_graph(
        equipment_targets, equipment_targets, _equipment_exposure)

    return PipelineResult(
        grid=grid, contributions=contributions, societal=societal,
        grade=weakest(grades) if grades else Grade.PLACEHOLDER,
        grade_by_route={k: weakest(v).value for k, v in route_grades.items()},
        n_scenarios=len(scenarios), n_computed=n_computed,
        n_skipped=n_skipped, coverage=coverage,
        refuse_policy=refuse_policy,
        flame_model=flame_model,
        escalation=escalation,
        ignition_checks=list(ignition_seen.values()),
        fragment_throws=list(frag_seen.values()),
        transient_audit=transient_audit,
        notes=sorted(set(notes)))


def _damage_field(outcome, fields, t_fire):
    """Vectorised counterpart of the damage models. Returns (PE, FE_in,
    FE_out) arrays, or None when this outcome has no field."""
    if outcome is Outcome.FLASH_FIRE:
        f = np.clip(fields[Outcome.FLASH_FIRE], 0.0, 1.0)
        return f, f, f
    if outcome is Outcome.BLEVE:
        if Outcome.BLEVE not in fields:
            return None, None, None
        inside = fields[Outcome.BLEVE]
        return inside, inside, inside
    if outcome is Outcome.POOL_FIRE:
        # An ignited LH2 spill is not a hydrocarbon pool fire: HSL
        # observed a jet at the source, a burn-back of the dispersed
        # cloud and, once, a secondary explosion. There is no steady
        # pool to build a solid flame around, so the burn-back is
        # modelled as a point source with the MEASURED radiative
        # fraction, and the geometry is not modelled at all.
        if Outcome.POOL_FIRE not in fields:
            return None, None, None
        return dmg.heat_radiation_arrays(fields[Outcome.POOL_FIRE], t_fire)
    if outcome is Outcome.JET_FIRE:
        if Outcome.JET_FIRE not in fields:
            return None, None, None
        flux = fields[Outcome.JET_FIRE]
        if not isinstance(flux, fieldmod.DirectionalFlux):
            raise TypeError("jet damage requires per-bearing DirectionalFlux, not mean flux")
        return tuple(v.mean(axis=-1) for v in
                     dmg.heat_radiation_arrays(flux.by_bearing, t_fire))
    if outcome is Outcome.EXPLOSION:
        p = fields[Outcome.EXPLOSION]
        pe = np.where(p >= dmg.P_HIGH_BARG, 1.0, 0.0)
        fin = np.where(p >= dmg.P_HIGH_BARG, 1.0,
                       np.where(p >= dmg.P_LOW_BARG, dmg.FE_IN_MID, 0.0))
        return pe, fin, pe
    return None, None, None


def erf_vec(x):
    return np.vectorize(math.erf)(x)


# _damage_at was removed here. It was the pre-vectorisation scalar
# damage mapping, superseded by _damage_field, and it had been left
# behind with no caller. It also carried a defect: it sent BLEVE to the
# jet flame radiation branch, whereas the fireball hazard is set by
# whether the receptor is inside the fireball, not by a flux. Dead code
# that is also wrong is worse than dead code, because the next person to
# call it gets a plausible number.
