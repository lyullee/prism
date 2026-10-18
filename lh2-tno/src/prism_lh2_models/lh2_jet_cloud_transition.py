"""Coupled LH2 two-phase horizontal-jet to cloud transition model.

This module supplies a *physical* source-to-cloud bridge.  It is deliberately
separate from SLABx: the transition is integrated from the flash plane until
both the suspended liquid inventory and the jet excess momentum are small.

The closure combines: (i) a flash/droplet state supplied by an independently
selected source-term model, (ii) d-squared droplet evaporation, (iii) classic
axisymmetric turbulent-jet entrainment, (iv) momentum uptake by entrained
co-flowing ambient air, and (v) an enthalpy balance for H2 liquid, H2 vapour,
and ambient air.  No receptor concentration is an input.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


R_UNIVERSAL = 8.314462618
MW_H2 = .002016
MW_AIR = .028965
H2_NORMAL_BOILING_TEMPERATURE_K = 20.36890353912107


@dataclass(frozen=True)
class WindForcing:
    """One measured, piecewise-constant meteorological wind interval.

    Bearings are meteorological *from* bearings.  A sequence is intended for
    packet-following near-field calculations; a single entry is exactly the
    conventional steady-wind case.
    """

    start_s: float
    end_s: float
    speed_m_s: float
    from_bearing_deg: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.start_s) and math.isfinite(self.end_s)
                and self.end_s > self.start_s):
            raise ValueError("wind interval must have finite end_s > start_s")
        if not math.isfinite(self.speed_m_s) or self.speed_m_s < 0:
            raise ValueError("wind speed must be finite and non-negative")
        if not math.isfinite(self.from_bearing_deg):
            raise ValueError("wind bearing must be finite")


@dataclass(frozen=True)
class AdvancedJetPhysics:
    """Opt-in conservative free-jet extensions used before wall contact.

    The default transition remains the archived bulk round-jet calculation.
    Enabling this object adds, without receptor fitting, the pieces that are
    explicit in the HyRAM/JETPLU family but absent from that legacy route:
    source-momentum and buoyancy entrainment, cross-flow entrainment and form
    drag, vertical momentum, a logarithmic wind profile, and distinct
    velocity/scalar Gaussian widths.  The source-momentum and local shear
    entrainment terms are combined by ``max`` rather than summed so the same
    turbulent interface is not counted twice.
    """

    momentum_entrainment_beta: float = .28
    jet_entrainment_alpha: float = .057
    plume_entrainment_alpha: float = .082
    plume_richardson_scale: float = .716
    crossflow_entrainment_alpha: float = .5
    form_drag_coefficient: float = .2
    scalar_to_velocity_width_ratio: float = 1.16
    # Three-dimensional wall jets spread much faster laterally than normal
    # to the wall.  These are self-similar half-width slopes, not ambient-air
    # entrainment velocities.  Keeping the two concepts separate avoids the
    # top-hat error in which every newly swept geometric strip is counted as
    # newly entrained air.
    wall_lateral_half_width_growth_rate: float = .26
    wall_normal_half_width_growth_rate: float = .048
    wall_jet_entrainment_alpha: float = .035
    # A passive scalar in a developed wall jet has its maximum at the wall.
    # A nearly zero SLAB core width gives the Gaussian limit of EQ13 while
    # retaining exact compatibility with the downstream solver.
    wall_scalar_core_fraction: float = 1e-4
    conservative_wall_profile: bool = False
    # Couple the explicit ground-reaction/lift-off route to the wall-jet
    # geometry.  A density sign change removes the gravity-current *driving*
    # pressure, not the lateral momentum accumulated while the cloud was
    # dense.  Retain that speed and let the already-computed wall skin
    # friction dissipate it.  Off by default for archived reproducibility.
    ground_reaction_liftoff: bool = False
    # Cross-wind pressure drag on the exposed vertical face of an attached
    # wall cloud.  It is opt-in with the state-transition route because the
    # archived scalar wall-jet closure has no laboratory-frame lateral
    # momentum equation.
    wall_crosswind_drag_coefficient: float = 0.0
    vertical_momentum: bool = True
    logarithmic_wind_shear: bool = True

    def __post_init__(self) -> None:
        positives = (
            self.momentum_entrainment_beta, self.jet_entrainment_alpha,
            self.plume_entrainment_alpha, self.plume_richardson_scale,
            self.scalar_to_velocity_width_ratio,
            self.wall_lateral_half_width_growth_rate,
            self.wall_normal_half_width_growth_rate,
            self.wall_jet_entrainment_alpha,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positives):
            raise ValueError("advanced jet scale parameters must be finite and positive")
        if (not math.isfinite(self.crossflow_entrainment_alpha)
                or self.crossflow_entrainment_alpha < 0.0):
            raise ValueError("crossflow entrainment coefficient must be finite and non-negative")
        if not math.isfinite(self.form_drag_coefficient) or self.form_drag_coefficient < 0.0:
            raise ValueError("form drag coefficient must be finite and non-negative")
        if (not math.isfinite(self.wall_crosswind_drag_coefficient)
                or self.wall_crosswind_drag_coefficient < 0.0):
            raise ValueError("wall cross-wind drag coefficient must be finite and non-negative")
        if self.plume_entrainment_alpha < self.jet_entrainment_alpha:
            raise ValueError("plume entrainment limit must not be below the jet coefficient")
        if (not math.isfinite(self.wall_scalar_core_fraction)
                or not 0.0 < self.wall_scalar_core_fraction < 1.0):
            raise ValueError("wall scalar core fraction must lie in (0, 1)")


@dataclass(frozen=True)
class TransitionInput:
    """Flash-plane state with all values declared upstream of the transition."""

    h2_rate_kg_s: float
    flash_vapour_mass_fraction: float
    flash_velocity_m_s: float
    flash_area_m2: float
    droplet_diameter_m: float
    evaporation_kb_m2_s: float
    liquid_density_kg_m3: float
    h2_temperature_K: float
    ambient_temperature_K: float
    ambient_density_kg_m3: float
    ambient_wind_m_s: float
    release_height_m: float
    friction_velocity_m_s: float = 0.0
    # Optional neutral logarithmic-law conversion of the measured wind record
    # into a local friction velocity.  Supplying neither retains the declared
    # constant ``friction_velocity_m_s`` used by historical calculations.
    wind_measurement_height_m: float | None = None
    surface_roughness_length_m: float | None = None
    # Classical round-jet entrainment coefficient.  This is a declared
    # literature closure, not an FFI-derived correction.
    entrainment_alpha: float = .10
    ground_shear_entrainment_coefficient: float = 1.5
    von_karman_constant: float = .4
    gravity_spreading_beta: float = 1.15
    wall_dynamic_viscosity_Pa_s: float = 1.7e-5
    wall_skin_friction_prefactor: float = .027
    # Once the free jet has contacted the ground, the outer wall-jet layer
    # grows approximately linearly with streamwise distance.  This is a
    # similarity closure for the wall-normal half-width, not a receptor
    # correction.  ``0`` retains the historical depth-averaged closure.
    wall_jet_vertical_growth_rate: float = 0.0
    # When turbulent lateral diffusivity expands the wall-cloud footprint, the
    # newly swept side faces entrain ambient air.  Historical runs widened the
    # geometric section through K_y/B but omitted this companion mass flux.
    # It is opt-in while existing archived routes remain reproducible.
    lateral_turbulent_exchange: bool = False
    # Optional, declared cryogenic-exchange inputs.  ``None`` means the
    # physics is unavailable, not zero humidity or zero wetting.
    ambient_relative_humidity_percent: float | None = None
    ground_wetted_area_m2: float | None = None
    ground_thermal_conductivity_W_mK: float = 1.7
    ground_thermal_diffusivity_m2_s: float = .7e-6
    # Optional moving-footprint conduction closure.  The contact width is the
    # computed wall-cloud width and the contact age is bounded by the declared
    # release duration; no receptor-derived wetted area is introduced.
    geometric_ground_contact: bool = False
    release_duration_s: float | None = None
    cp_h2_gas_J_kgK: float = 14300.0
    cp_h2_liquid_J_kgK: float = 9800.0
    cp_air_J_kgK: float = 1006.0
    latent_heat_J_kg: float = 445000.0
    # Optional horizontal-vector closure. Bearings are clockwise from north
    # and describe directions *toward* which the jet and wind travel.  Both
    # must be supplied together.  Leaving both absent retains the historical
    # one-dimensional, co-flowing calculation exactly.
    release_bearing_deg: float | None = None
    wind_from_bearing_deg: float | None = None
    # Optional measured wind history.  It is accepted only for the vector
    # route, where the actual parcel trajectory can respond to a changing
    # ambient velocity.  Omitting it retains the legacy steady wind exactly.
    wind_history: tuple[WindForcing, ...] | None = None
    # Absolute release time on the meteorological history clock.  It lets an
    # unsteady packet ensemble reuse one measured wind record: a packet
    # emitted at t0 samples U(t0 + parcel_age), rather than restarting the
    # weather record at every packet.  The default retains prior behaviour.
    wind_time_offset_s: float = 0.0
    # Resolve N2/O2/H2O phase separation in the LH2 entrainment zone.  It is
    # opt-in so existing generic gas/jet cases retain their declared legacy
    # closure; LH2 source-to-cloud calculations should enable it explicitly.
    resolve_cryogenic_air_phase: bool = False
    advanced_jet_physics: AdvancedJetPhysics | None = None

    def __post_init__(self) -> None:
        positives = ("h2_rate_kg_s", "flash_velocity_m_s", "flash_area_m2", "droplet_diameter_m",
                     "evaporation_kb_m2_s", "liquid_density_kg_m3", "h2_temperature_K",
                     "ambient_temperature_K", "ambient_density_kg_m3", "release_height_m",
                     "entrainment_alpha", "ground_shear_entrainment_coefficient", "gravity_spreading_beta", "wall_dynamic_viscosity_Pa_s", "wall_skin_friction_prefactor", "cp_h2_gas_J_kgK", "cp_h2_liquid_J_kgK", "cp_air_J_kgK",
                     "latent_heat_J_kg")
        if any(getattr(self, name) <= 0 for name in positives):
            raise ValueError("all physical scale inputs must be positive")
        if not 0 <= self.flash_vapour_mass_fraction <= 1:
            raise ValueError("flash_vapour_mass_fraction must lie in [0, 1]")
        if self.ambient_wind_m_s < 0:
            raise ValueError("ambient_wind_m_s must be non-negative")
        if self.friction_velocity_m_s < 0:
            raise ValueError("friction_velocity_m_s must be non-negative")
        if (self.wind_measurement_height_m is None) != (self.surface_roughness_length_m is None):
            raise ValueError("wind_measurement_height_m and surface_roughness_length_m must be supplied together")
        if self.wind_measurement_height_m is not None:
            assert self.surface_roughness_length_m is not None
            if self.wind_measurement_height_m <= self.surface_roughness_length_m or self.surface_roughness_length_m <= 0:
                raise ValueError("wind measurement height must exceed positive surface roughness length")
        if self.wall_jet_vertical_growth_rate < 0:
            raise ValueError("wall_jet_vertical_growth_rate must be non-negative")
        if self.ambient_relative_humidity_percent is not None and not 0 <= self.ambient_relative_humidity_percent <= 100:
            raise ValueError("ambient_relative_humidity_percent must lie in [0, 100]")
        if self.ground_wetted_area_m2 is not None and self.ground_wetted_area_m2 < 0:
            raise ValueError("ground_wetted_area_m2 must be non-negative")
        if self.release_duration_s is not None and self.release_duration_s <= 0:
            raise ValueError("release_duration_s must be positive when supplied")
        if self.geometric_ground_contact and self.release_duration_s is None:
            raise ValueError("geometric_ground_contact requires a declared release_duration_s")
        if (self.release_bearing_deg is None) != (self.wind_from_bearing_deg is None):
            raise ValueError("release_bearing_deg and wind_from_bearing_deg must be supplied together")
        if self.wind_history is not None:
            if self.release_bearing_deg is None:
                raise ValueError("wind_history requires vector release and wind bearings")
            if not self.wind_history:
                raise ValueError("wind_history may not be empty")
            previous_end = None
            for interval in self.wind_history:
                if previous_end is not None and interval.start_s < previous_end - 1e-12:
                    raise ValueError("wind_history intervals must not overlap")
                previous_end = interval.end_s
        if not math.isfinite(self.wind_time_offset_s):
            raise ValueError("wind_time_offset_s must be finite")
        for name in ("release_bearing_deg", "wind_from_bearing_deg"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite when supplied")


@dataclass(frozen=True)
class TransitionState:
    x_m: float
    time_s: float
    h2_gas_rate_kg_s: float
    h2_liquid_rate_kg_s: float
    entrained_air_rate_kg_s: float
    condensed_water_rate_kg_s: float
    ground_shear_air_rate_kg_s: float
    total_rate_kg_s: float
    h2_mass_fraction: float
    h2_mole_fraction: float
    temperature_K: float
    density_kg_m3: float
    velocity_m_s: float
    excess_velocity_m_s: float
    radius_m: float
    effective_half_width_m: float
    layer_depth_m: float
    height_m: float
    buoyancy_acceleration_m_s2: float
    lateral_eddy_diffusivity_m2_s: float
    local_richardson_number: float
    wall_skin_friction_coefficient: float
    wall_momentum_sink_N_m: float
    humid_condensation_heat_W: float
    ground_heat_W: float
    droplet_diameter_m: float
    mass_residual_kg_s: float
    energy_residual_W: float
    # Vector fields are zero/None for legacy one-dimensional calculations.
    east_m: float = 0.0
    north_m: float = 0.0
    velocity_east_m_s: float = 0.0
    velocity_north_m_s: float = 0.0
    velocity_bearing_deg: float | None = None
    wind_alignment_deg: float | None = None
    nitrogen_gas_rate_kg_s: float = 0.0
    oxygen_gas_rate_kg_s: float = 0.0
    water_gas_rate_kg_s: float = 0.0
    condensed_nitrogen_rate_kg_s: float = 0.0
    condensed_oxygen_rate_kg_s: float = 0.0
    # Opt-in profile/three-dimensional diagnostics.  Defaults keep archived
    # CSV consumers and positional construction backward compatible.
    vertical_velocity_m_s: float = 0.0
    vertical_momentum_flux_N: float = 0.0
    velocity_half_width_m: float = 0.0
    scalar_half_width_m: float = 0.0
    effective_flow_area_m2: float = 0.0
    crossflow_speed_m_s: float = 0.0
    crossflow_drag_N_m: float = 0.0
    entrainment_rate_kg_s_m: float = 0.0
    entrainment_model: str = "legacy_round_jet"
    geometric_flow_area_m2: float = 0.0
    # Wall-jet profile coordinates.  The geometric widths above describe the
    # hydrodynamic envelope; these fields describe the conservative scalar
    # section passed to the receptor field and SLAB.
    scalar_profile_depth_m: float = 0.0
    scalar_centre_height_m: float = 0.0
    scalar_core_fraction: float = .9
    target_scalar_lateral_half_width_m: float = 0.0
    target_scalar_vertical_half_width_m: float = 0.0


def _bearing_vector(bearing_deg: float) -> tuple[float, float]:
    """Return EN components for a clockwise-from-north travel bearing."""
    angle = math.radians(bearing_deg % 360.0)
    return math.sin(angle), math.cos(angle)


def _bearing_difference_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _wind_vector_at(inp: TransitionInput, time_s: float, *, height_m: float | None = None) -> tuple[float, float, float]:
    """Return EN wind and travel bearing at a parcel time.

    Before/after a measured history the nearest endpoint value is retained.
    This makes the boundary treatment explicit and avoids inventing an
    unreported extrapolation trend.
    """
    if inp.wind_history is None:
        assert inp.wind_from_bearing_deg is not None
        travel = (inp.wind_from_bearing_deg + 180.0) % 360.0
        east, north = _bearing_vector(travel)
        speed = inp.ambient_wind_m_s
    else:
        history_time_s = time_s + inp.wind_time_offset_s
        selected = inp.wind_history[0]
        for interval in inp.wind_history:
            if interval.start_s <= history_time_s < interval.end_s:
                selected = interval
                break
            if interval.start_s <= history_time_s:
                selected = interval
        travel = (selected.from_bearing_deg + 180.0) % 360.0
        east, north = _bearing_vector(travel)
        speed = selected.speed_m_s
    advanced = inp.advanced_jet_physics
    if (height_m is not None and advanced is not None and advanced.logarithmic_wind_shear
            and inp.wind_measurement_height_m is not None):
        assert inp.surface_roughness_length_m is not None
        z0 = inp.surface_roughness_length_m
        reference = math.log((inp.wind_measurement_height_m + z0) / z0)
        local = math.log((max(height_m, 0.0) + z0) / z0)
        speed *= max(0.0, local / reference)
    return east * speed, north * speed, travel


def _friction_velocity_at(inp: TransitionInput, time_s: float) -> float:
    """Return the local neutral-law friction velocity when geometry is known."""
    if inp.wind_measurement_height_m is None:
        return inp.friction_velocity_m_s
    assert inp.surface_roughness_length_m is not None
    east, north, _ = _wind_vector_at(inp, time_s)
    speed = math.hypot(east, north)
    return inp.von_karman_constant * speed / math.log(inp.wind_measurement_height_m / inp.surface_roughness_length_m)


def _hybrid_jet_entrainment(
    physics: AdvancedJetPhysics, *, radius_m: float, speed_m_s: float,
    excess_speed_m_s: float, vertical_speed_m_s: float, density_kg_m3: float,
    ambient_density_kg_m3: float, source_momentum_entrainment_m2_s: float,
    source_buoyancy_coefficient: float, crossflow_speed_m_s: float,
) -> tuple[float, str]:
    """Return advanced volumetric entrainment per streamline length [m2/s]."""
    diameter = 2.0 * max(radius_m, 1e-12)
    density_contrast = abs(ambient_density_kg_m3 - density_kg_m3)
    reduced_gravity = 9.80665 * density_contrast / max(density_kg_m3, 1e-30)
    local_ri = reduced_gravity * diameter / max(excess_speed_m_s ** 2, 1e-30)
    blend = local_ri / (local_ri + physics.plume_richardson_scale)
    alpha_local = (physics.jet_entrainment_alpha
                   + (physics.plume_entrainment_alpha - physics.jet_entrainment_alpha) * blend)
    local_shear = 2.0 * math.pi * radius_m * alpha_local * excess_speed_m_s
    # HyRAM source-momentum entrainment and local shear describe the same
    # turbulent interface.  Retain the controlling estimate rather than
    # summing them and double-counting that surface.
    base = max(source_momentum_entrainment_m2_s, local_shear)
    froude_l = (speed_m_s ** 2 * density_kg_m3
                / max(9.80665 * radius_m * density_contrast, 1e-30))
    buoyant = (source_buoyancy_coefficient / max(froude_l, 1e-30)
               * 2.0 * math.pi * speed_m_s * radius_m
               * abs(vertical_speed_m_s) / max(speed_m_s, 1e-30))
    capped = min(base + buoyant,
                 physics.plume_entrainment_alpha * 2.0 * math.pi * radius_m * speed_m_s)
    crossflow = (physics.crossflow_entrainment_alpha * 2.0 * radius_m
                 * max(crossflow_speed_m_s, 0.0))
    return capped + crossflow, "hybrid_hyram_jetplu"


def _source_buoyancy_coefficient(inp: TransitionInput, source_density_kg_m3: float) -> float:
    """HyRAM/Houf source-Froude buoyancy coefficient."""
    diameter = 2.0 * math.sqrt(inp.flash_area_m2 / math.pi)
    contrast = abs(inp.ambient_density_kg_m3 - source_density_kg_m3)
    if contrast <= 1e-15:
        froude = math.inf
    else:
        froude = inp.flash_velocity_m_s / math.sqrt(
            9.80665 * diameter * contrast / max(source_density_kg_m3, 1e-30)
        )
    return (17.313 - .11665 * froude + 2.0771e-4 * froude ** 2
            if froude < 268.0 else .97)


def _mole_fraction(h2_mass: float, dry_air_mass: float, condensed_water_mass: float = 0.0) -> float:
    total_moles = h2_mass / MW_H2 + dry_air_mass / MW_AIR + condensed_water_mass / .01801528
    return (h2_mass / MW_H2) / max(total_moles, 1e-30)


def _mixture_density(temperature_K: float, x_h2: float) -> float:
    mw = x_h2 * MW_H2 + (1.0 - x_h2) * MW_AIR
    return 101325.0 * mw / (R_UNIVERSAL * temperature_K)


def _energy_temperature(inp: TransitionInput, gas_h2: float, liquid_h2: float,
                        air: float, condensed_water: float, initial_energy_W: float,
                        exchange_heat_W: float = 0.0) -> tuple[float, float]:
    """Solve the explicit three-stream enthalpy balance at the current state.

    Gas enthalpy is referenced to zero at 0 K.  Liquid H2 carries the same
    sensible reference minus the declared latent heat, so evaporation consumes
    energy without an empirical cooling factor.
    """
    # Every increment of entrained ambient air carries its own sensible
    # enthalpy into the control volume.  Leaving this term out would force the
    # cold initial LH2 enthalpy to cool an arbitrarily large air mass below
    # absolute zero, which is a bookkeeping error rather than an LH2 effect.
    target_energy = initial_energy_W + air * inp.cp_air_J_kgK * inp.ambient_temperature_K + exchange_heat_W
    heat_capacity = (gas_h2 * inp.cp_h2_gas_J_kgK + liquid_h2 * inp.cp_h2_liquid_J_kgK
                     + air * inp.cp_air_J_kgK + condensed_water * 2100.0)
    phase_offset = liquid_h2 * inp.latent_heat_J_kg
    # A partially evaporated parcel can otherwise produce a negative
    # reconstructed temperature when the latent reference is larger than the
    # retained sensible energy.  That is an energy-bookkeeping failure, not a
    # physical LH2 state.  Keep the calculation finite and expose the residual
    # below; callers may reject the state if the residual is material.
    temperature = max(1.0, (target_energy + phase_offset) / max(heat_capacity, 1e-30))
    reconstructed = (gas_h2 * inp.cp_h2_gas_J_kgK * temperature
                     + liquid_h2 * (inp.cp_h2_liquid_J_kgK * temperature - inp.latent_heat_J_kg)
                     + air * inp.cp_air_J_kgK * temperature + condensed_water * 2100.0 * temperature)
    return temperature, reconstructed - target_energy


def _minimum_liquid_for_energy(inp: TransitionInput, *, liquid0: float,
                               air: float, condensed_water: float,
                               initial_energy_W: float,
                               exchange_heat_W: float = 0.0) -> float:
    """Liquid H2 that must remain to avoid unpowered sub-boiling evaporation.

    The d-squared relation is a mass-transfer upper bound, not an energy
    source.  While LH2 liquid remains, the plug may not cool below its
    one-atmosphere saturation temperature merely to satisfy that upper bound.
    This analytic enthalpy limit retains enough liquid to close the energy
    balance at saturation; when the returned value reaches zero, all liquid
    may physically vaporise and the gas-only energy equation takes over.
    """
    temperature = H2_NORMAL_BOILING_TEMPERATURE_K
    h2_total = inp.h2_rate_kg_s
    target_energy = initial_energy_W + air * inp.cp_air_J_kgK * inp.ambient_temperature_K + exchange_heat_W
    gas_only_at_saturation = (h2_total * inp.cp_h2_gas_J_kgK * temperature
                               + air * inp.cp_air_J_kgK * temperature
                               + condensed_water * 2100.0 * temperature)
    liquid_increment = ((inp.cp_h2_liquid_J_kgK - inp.cp_h2_gas_J_kgK) * temperature
                        - inp.latent_heat_J_kg)
    required = (target_energy - gas_only_at_saturation) / min(liquid_increment, -1e-30)
    return min(liquid0, max(0.0, required))


def transition_input_from_rescigno(exit_state, baseline, *, ambient_temperature_K: float,
                                   ambient_density_kg_m3: float, ambient_wind_m_s: float,
                                   friction_velocity_m_s: float = 0.0,
                                   release_bearing_deg: float | None = None,
                                   wind_from_bearing_deg: float | None = None,
                                   ambient_relative_humidity_percent: float | None = None,
                                   ground_wetted_area_m2: float | None = None,
                                   geometric_ground_contact: bool = False,
                                   release_duration_s: float | None = None) -> TransitionInput:
    """Build an auditable transition input from a declared Rescigno result.

    The caller owns the upstream nozzle state and must not infer it from a
    receptor.  This helper merely preserves the resulting flash area,
    velocity, quality, droplet diameter and d-squared evaporation coefficient.
    """
    return TransitionInput(
        h2_rate_kg_s=exit_state.mass_flow_kg_s,
        flash_vapour_mass_fraction=baseline.flashed_quality,
        flash_velocity_m_s=baseline.flashed_velocity_m_s,
        flash_area_m2=baseline.flashed_area_m2,
        droplet_diameter_m=baseline.droplet_diameter_m,
        evaporation_kb_m2_s=baseline.evaporation_kb_m2_s,
        liquid_density_kg_m3=baseline.liquid_density_kg_m3,
        h2_temperature_K=exit_state.temperature_k,
        ambient_temperature_K=ambient_temperature_K,
        ambient_density_kg_m3=ambient_density_kg_m3,
        ambient_wind_m_s=ambient_wind_m_s,
        release_height_m=exit_state.release_height_m,
        friction_velocity_m_s=friction_velocity_m_s,
        release_bearing_deg=release_bearing_deg,
        wind_from_bearing_deg=wind_from_bearing_deg,
        ambient_relative_humidity_percent=ambient_relative_humidity_percent,
        ground_wetted_area_m2=ground_wetted_area_m2,
        geometric_ground_contact=geometric_ground_contact,
        release_duration_s=release_duration_s,
    )


def integrate_transition(inp: TransitionInput, *, x_max_m: float = 100.0,
                         dx_m: float = .01,
                         liquid_tolerance: float = 1e-5,
                         excess_velocity_ratio: float = .10,
                         stop_on_passive: bool = True) -> tuple[TransitionState, ...]:
    """Integrate the physical transition; does not fit or inspect receptors.

    The returned series includes the first state meeting both handoff tests:
    remaining liquid H2 below ``liquid_tolerance`` of release and jet excess
    velocity below ``excess_velocity_ratio`` of ambient wind (or 0.1 m/s in
    calm air).  Callers may use that state as a gas-cloud handoff plane.
    """
    if x_max_m <= 0 or dx_m <= 0:
        raise ValueError("x_max_m and dx_m must be positive")
    if not 0 < liquid_tolerance < 1 or excess_velocity_ratio <= 0:
        raise ValueError("invalid handoff tolerances")
    if not isinstance(stop_on_passive, bool):
        raise ValueError("stop_on_passive must be boolean")
    advanced = inp.advanced_jet_physics
    centre_height = inp.release_height_m
    momentum_up = 0.0
    vector_mode = inp.release_bearing_deg is not None
    if vector_mode:
        assert inp.release_bearing_deg is not None and inp.wind_from_bearing_deg is not None
        wind_east, wind_north, wind_bearing = _wind_vector_at(
            inp, 0.0, height_m=centre_height,
        )
        jet_east, jet_north = _bearing_vector(inp.release_bearing_deg)
        # Carry laboratory-frame momentum.  Entrained air subsequently adds
        # the wind velocity at the parcel's actual time.  With constant wind,
        # this reduces exactly to the historical conserved excess-momentum
        # formulation; with a measured wind history it bends continuously.
        momentum_east = inp.h2_rate_kg_s * inp.flash_velocity_m_s * jet_east
        momentum_north = inp.h2_rate_kg_s * inp.flash_velocity_m_s * jet_north
        east_m = north_m = 0.0
        elapsed_s = 0.0
    else:
        wind_bearing = None
        wind_east, wind_north = inp.ambient_wind_m_s, 0.0
        momentum_east = inp.h2_rate_kg_s * max(0.0, inp.flash_velocity_m_s - inp.ambient_wind_m_s)
        momentum_north = 0.0
        east_m = north_m = 0.0
        elapsed_s = 0.0
    liquid0 = inp.h2_rate_kg_s * (1.0 - inp.flash_vapour_mass_fraction)
    gas0 = inp.h2_rate_kg_s - liquid0
    radius = math.sqrt(inp.flash_area_m2 / math.pi)
    source_density = inp.h2_rate_kg_s / max(
        inp.flash_area_m2 * inp.flash_velocity_m_s, 1e-30,
    )
    source_momentum_entrainment = (0.0 if advanced is None else
        advanced.momentum_entrainment_beta * math.sqrt(
            inp.h2_rate_kg_s * inp.flash_velocity_m_s
            / max(inp.ambient_density_kg_m3, 1e-30)
        ))
    source_buoyancy_coefficient = (0.0 if advanced is None else
                                   _source_buoyancy_coefficient(inp, source_density))
    # ``half_width`` is the horizontal half-width of the cloud footprint.  It
    # separates from the round-jet radius only after the growing jet meets the
    # ground.  The transition preserves cross-sectional area in that change;
    # it is not a receptor-derived widening.
    half_width = radius
    layer_depth = 2.0 * radius
    velocity_half_depth = radius
    scalar_lateral_spread = (radius if advanced is None else
                             advanced.scalar_to_velocity_width_ratio * radius)
    scalar_vertical_spread = scalar_lateral_spread
    ground_layer = False
    # In the scalar legacy route this is the original co-flowing momentum;
    # in vector mode it carries the two EN components defined above.
    excess_momentum = momentum_east
    air = 0.0
    air_from_ground_shear = 0.0
    condensed_water = 0.0
    if inp.ambient_relative_humidity_percent is not None and not inp.resolve_cryogenic_air_phase:
        from .cryogenic_exchange import HumidAirExchange
        humid_exchange = HumidAirExchange(inp.ambient_temperature_K, inp.ambient_relative_humidity_percent)
    else:
        humid_exchange = None
    ground_exchange = None
    droplet = inp.droplet_diameter_m if liquid0 > 0 else 0.0
    # Once the equilibrium calculation has demonstrated that all LH2 and
    # condensed-air inventories are gone, subsequent warm-air entrainment can
    # only increase the parcel enthalpy.  The standard gas/air balance is then
    # thermodynamically identical for this purpose, so stop repeating costly
    # multicomponent property calls without truncating an active phase change.
    cryogenic_phase_active = inp.resolve_cryogenic_air_phase
    initial_energy = (gas0 * inp.cp_h2_gas_J_kgK * inp.h2_temperature_K
                      + liquid0 * (inp.cp_h2_liquid_J_kgK * inp.h2_temperature_K - inp.latent_heat_J_kg))
    geometric_ground_heat_W = 0.0
    wall_gravity_speed_m_s = 0.0
    rows: list[TransitionState] = []
    x = 0.0
    while x <= x_max_m + 1e-12:
        liquid_ratio = 0.0 if liquid0 == 0 else max(0.0, droplet / inp.droplet_diameter_m) ** 3
        liquid = liquid0 * liquid_ratio
        gas = inp.h2_rate_kg_s - liquid
        # Start with the dry-air / H2 energy solution, then close the optional
        # humidity and ground-exchange terms by a short fixed-point iteration.
        total = gas + liquid + air + condensed_water
        if vector_mode:
            wind_east, wind_north, wind_bearing = _wind_vector_at(
                inp, elapsed_s, height_m=centre_height,
            )
            excess_east = momentum_east - total * wind_east
            excess_north = momentum_north - total * wind_north
            excess_up = momentum_up
            excess_u = math.sqrt(excess_east ** 2 + excess_north ** 2 + excess_up ** 2) / max(total, 1e-30)
            velocity_east = momentum_east / max(total, 1e-30)
            velocity_north = momentum_north / max(total, 1e-30)
            velocity_up = momentum_up / max(total, 1e-30)
            velocity_plan = math.hypot(velocity_east, velocity_north)
            velocity = math.hypot(velocity_plan, velocity_up)
            velocity_bearing = math.degrees(math.atan2(velocity_east, velocity_north)) % 360.0
            wind_alignment = _bearing_difference_deg(velocity_bearing, wind_bearing)
            local_time_s = elapsed_s
        else:
            excess_u = excess_momentum / max(total, 1e-30)
            velocity = inp.ambient_wind_m_s + excess_u
            velocity_plan = velocity
            velocity_east, velocity_north = velocity, 0.0
            velocity_up = 0.0
            velocity_bearing = wind_alignment = None
            local_time_s = x / max(velocity, .05)
        y_h2 = inp.h2_rate_kg_s / total
        x_h2 = _mole_fraction(inp.h2_rate_kg_s, air, condensed_water)
        temperature, energy_residual = _energy_temperature(inp, gas, liquid, air, condensed_water, initial_energy)
        density = _mixture_density(temperature, x_h2)
        nitrogen_gas = oxygen_gas = water_gas = 0.0
        condensed_nitrogen = condensed_oxygen = 0.0
        if cryogenic_phase_active and air > 0.0:
            # Phase equilibrium and enthalpy are solved before the
            # hydrodynamic update.  N2/O2/H2O are therefore not folded into a
            # fictitious homogeneous ``air`` density in the cold core.
            from .cryogenic_air_phase import CryogenicPlugFlowInput, solve_cryogenic_plug_flow
            phase = solve_cryogenic_plug_flow(CryogenicPlugFlowInput(
                h2_gas_rate_kg_s=gas, h2_liquid_rate_kg_s=liquid,
                reference_h2_gas_rate_kg_s=gas0, reference_h2_liquid_rate_kg_s=liquid0,
                entrained_dry_air_rate_kg_s=air,
                h2_source_temperature_K=inp.h2_temperature_K,
                ambient_temperature_K=inp.ambient_temperature_K,
                relative_humidity_percent=inp.ambient_relative_humidity_percent,
                external_heat_W=geometric_ground_heat_W,
            ))
            gas, liquid = phase.h2_gas_rate_kg_s, phase.h2_liquid_rate_kg_s
            nitrogen_gas, oxygen_gas, water_gas = (phase.nitrogen_gas_rate_kg_s,
                                                    phase.oxygen_gas_rate_kg_s,
                                                    phase.water_gas_rate_kg_s)
            condensed_nitrogen, condensed_oxygen, condensed_water = (
                phase.condensed_nitrogen_rate_kg_s, phase.condensed_oxygen_rate_kg_s,
                phase.condensed_water_rate_kg_s)
            total = gas + liquid + air + water_gas + condensed_water
            y_h2 = inp.h2_rate_kg_s / total
            x_h2 = phase.gas_h2_mole_fraction
            temperature, density, energy_residual = (phase.temperature_K, phase.gas_density_kg_m3,
                                                      phase.energy_residual_W)
            if (liquid <= 1e-12 and phase.condensed_air_rate_kg_s <= 1e-12
                    and phase.condensed_water_rate_kg_s <= 1e-12):
                cryogenic_phase_active = False
        # At first contact, map the circular free-jet control volume to a
        # shallow layer while preserving cross-sectional area.  The subsequent
        # wall-cloud evolution is governed by gravity spreading and vertical
        # entrainment below, not by a frozen circular jet radius.
        if not ground_layer and radius >= centre_height:
            ground_layer = True
            layer_depth = max(2.0 * centre_height, 2.0 * radius * 1e-6)
            half_width = max(half_width, math.pi * radius * radius / (2.0 * layer_depth))
            centre_height = .5 * layer_depth
            velocity_half_depth = .5 * layer_depth
            if advanced is not None:
                scalar_lateral_spread = max(
                    scalar_lateral_spread,
                    advanced.scalar_to_velocity_width_ratio * half_width,
                )
                scalar_vertical_spread = max(
                    scalar_vertical_spread,
                    advanced.scalar_to_velocity_width_ratio * velocity_half_depth,
                )
            momentum_up = 0.0
            if inp.ground_wetted_area_m2 is not None:
                from .cryogenic_exchange import WettedGroundExchange
                ground_exchange = WettedGroundExchange(inp.ground_thermal_conductivity_W_mK,
                                                       inp.ground_thermal_diffusivity_m2_s,
                                                       inp.ambient_temperature_K, inp.ground_wetted_area_m2)
        grounded = ground_layer
        if not grounded:
            layer_depth = 2.0 * radius
            half_width = radius
            velocity_half_depth = radius
            if advanced is not None:
                scalar_lateral_spread = advanced.scalar_to_velocity_width_ratio * radius
                scalar_vertical_spread = scalar_lateral_spread
        humidity_heat = 0.0
        ground_heat = geometric_ground_heat_W
        if humid_exchange is not None or (ground_exchange is not None and grounded):
            for _ in range(4):
                new_condensed = (humid_exchange.condensation_from_dry_air(air, temperature)
                                 if humid_exchange is not None else 0.0)
                humidity_heat = (humid_exchange.latent_heating_W(air, temperature)
                                 if humid_exchange is not None else 0.0)
                ground_heat = (geometric_ground_heat_W
                               + (ground_exchange.heat_rate_W(temperature, max(local_time_s, .01))
                                  if ground_exchange is not None and grounded else 0.0))
                temperature, energy_residual = _energy_temperature(inp, gas, liquid, air, new_condensed,
                                                                      initial_energy, humidity_heat + ground_heat)
            condensed_water = new_condensed
            total = gas + liquid + air + condensed_water
            y_h2 = inp.h2_rate_kg_s / total
            x_h2 = _mole_fraction(inp.h2_rate_kg_s, air, condensed_water)
            density = _mixture_density(temperature, x_h2)
        if vector_mode:
            # Phase changes alter total flux, so refresh the velocity before
            # evaluating aerodynamic forces and exporting the state.
            wind_east, wind_north, wind_bearing = _wind_vector_at(
                inp, elapsed_s, height_m=centre_height,
            )
            velocity_east = momentum_east / max(total, 1e-30)
            velocity_north = momentum_north / max(total, 1e-30)
            velocity_up = momentum_up / max(total, 1e-30)
            velocity_plan = math.hypot(velocity_east, velocity_north)
            velocity = math.hypot(velocity_plan, velocity_up)
            excess_east = momentum_east - total * wind_east
            excess_north = momentum_north - total * wind_north
            excess_u = math.sqrt(excess_east ** 2 + excess_north ** 2 + momentum_up ** 2) / max(total, 1e-30)
            velocity_bearing = math.degrees(math.atan2(velocity_east, velocity_north)) % 360.0
            wind_alignment = _bearing_difference_deg(velocity_bearing, wind_bearing)
        # Neutral-boundary-layer turbulent diffusion follows the mixing-length
        # scale K_y = kappa*u_*h.  It expands a top-hat half-width through
        # d(B^2)/dt = 2 K_y, with no wind-direction or sensor fit.
        friction_velocity = _friction_velocity_at(inp, local_time_s)
        lateral_K = inp.von_karman_constant * friction_velocity * layer_depth
        # A gas-only density is not a valid buoyancy density while a suspended
        # LH2 liquid inventory is still present.  The resulting reduced-gravity
        # value is handed to the downstream plume stage; it is not used to
        # invent a near-field lift-off trajectory without a two-phase vertical
        # momentum closure.
        buoyancy = (9.80665 * (inp.ambient_density_kg_m3 - density) / max(density, 1e-30)
                    if liquid <= liquid_tolerance * inp.h2_rate_kg_s else 0.0)
        crossflow_speed = crossflow_drag = 0.0
        drag_east = drag_north = drag_up = 0.0
        if advanced is not None and vector_mode and not grounded:
            speed_floor = max(velocity, 1e-30)
            axis_e = velocity_east / speed_floor
            axis_n = velocity_north / speed_floor
            axis_z = velocity_up / speed_floor
            relative_e = wind_east - velocity_east
            relative_n = wind_north - velocity_north
            relative_z = -velocity_up
            along = relative_e * axis_e + relative_n * axis_n + relative_z * axis_z
            perpendicular_e = relative_e - along * axis_e
            perpendicular_n = relative_n - along * axis_n
            perpendicular_z = relative_z - along * axis_z
            crossflow_speed = math.sqrt(
                perpendicular_e ** 2 + perpendicular_n ** 2 + perpendicular_z ** 2
            )
            projected_width = 2.0 * radius
            crossflow_drag = (.5 * advanced.form_drag_coefficient * inp.ambient_density_kg_m3
                              * crossflow_speed ** 2 * projected_width)
            if crossflow_speed > 0.0:
                drag_east = crossflow_drag * perpendicular_e / crossflow_speed
                drag_north = crossflow_drag * perpendicular_n / crossflow_speed
                drag_up = crossflow_drag * perpendicular_z / crossflow_speed
        area_now = (2.0 * half_width * layer_depth if grounded
                    else math.pi * radius * radius)
        # The wall-growth closure supplies a geometric envelope, while the
        # transported scalar requires the flux-equivalent section
        # M/(rho*U).  Export both: the latter is the only area that can be
        # handed to another integral model without changing mass flux.
        effective_transport_area = (area_now if advanced is None else
            total / max(density * velocity, 1e-30))
        if advanced is None:
            velocity_width = half_width if grounded else radius
            scalar_width = velocity_width
            scalar_profile_depth = layer_depth
            scalar_centre_height = .5 * layer_depth if grounded else centre_height
            scalar_core_fraction = .9
            entrainment_model = "legacy_round_jet" if not grounded else "legacy_wall_jet"
        else:
            velocity_width = half_width if grounded else radius
            if grounded and advanced.conservative_wall_profile:
                # The turbulent spreading laws determine the lateral/normal
                # aspect ratio.  The transported mass and momentum determine
                # the flux-equivalent area.  Scaling both profile axes by the
                # same factor satisfies both constraints without inventing or
                # deleting scalar inventory.
                aspect = scalar_lateral_spread / max(scalar_vertical_spread, 1e-30)
                scalar_width = math.sqrt(max(effective_transport_area * aspect / 2.0, 1e-30))
                scalar_profile_depth = effective_transport_area / max(2.0 * scalar_width, 1e-30)
                scalar_centre_height = 0.0
                scalar_core_fraction = advanced.wall_scalar_core_fraction
                entrainment_model = "advanced_3d_wall_jet"
            else:
                scalar_width = advanced.scalar_to_velocity_width_ratio * velocity_width
                scalar_profile_depth = (effective_transport_area
                                        / max(2.0 * scalar_width, 1e-30))
                scalar_centre_height = (.5 * scalar_profile_depth
                                        if grounded else centre_height)
                scalar_core_fraction = .9
                entrainment_model = "advanced_wall_jet" if grounded else "hybrid_hyram_jetplu"
        ri = (9.80665 * layer_depth * max(0.0, density - inp.ambient_density_kg_m3)
              / max(inp.ambient_density_kg_m3 * friction_velocity ** 2, 1e-30)) if grounded else 0.0
        if grounded:
            # Smooth-wall turbulent boundary-layer skin friction, evaluated
            # on the ground-relative excess velocity and layer depth.  The
            # force is applied to the exposed bottom width (2B), so it is an
            # axial momentum sink rather than an invented entrainment source.
            re_wall = density * max(excess_u, 1e-6) * layer_depth / inp.wall_dynamic_viscosity_Pa_s
            wall_cf = inp.wall_skin_friction_prefactor / max(re_wall, 1.0) ** (1.0 / 7.0)
            wall_sink = .5 * wall_cf * density * excess_u * excess_u * (2.0 * half_width)
        else:
            wall_cf = 0.0
            wall_sink = 0.0
        if not grounded:
            if advanced is None:
                current_dm_air_dx = (2.0 * math.pi * radius * inp.ambient_density_kg_m3
                                     * inp.entrainment_alpha * excess_u)
            else:
                volume_entrainment, _ = _hybrid_jet_entrainment(
                    advanced, radius_m=radius, speed_m_s=velocity,
                    excess_speed_m_s=excess_u, vertical_speed_m_s=velocity_up,
                    density_kg_m3=density, ambient_density_kg_m3=inp.ambient_density_kg_m3,
                    source_momentum_entrainment_m2_s=source_momentum_entrainment,
                    source_buoyancy_coefficient=source_buoyancy_coefficient,
                    crossflow_speed_m_s=crossflow_speed,
                )
                current_dm_air_dx = inp.ambient_density_kg_m3 * volume_entrainment
        else:
            instantaneous_w_gravity = (
                inp.gravity_spreading_beta * friction_velocity * math.sqrt(ri)
            )
            if advanced is not None and advanced.ground_reaction_liftoff:
                # Ground reaction removes normal momentum, while the lateral
                # gravity-current momentum already present in the wall layer
                # survives a density reversal and decays through wall drag.
                if wall_gravity_speed_m_s == 0.0 and ri > 0.0:
                    wall_gravity_speed_m_s = instantaneous_w_gravity
                w_gravity = wall_gravity_speed_m_s
            else:
                w_gravity = instantaneous_w_gravity
            w_vertical = (inp.von_karman_constant * friction_velocity
                          / (0.88 + 0.099 * ri ** 1.04))
            w_wall_jet = inp.wall_jet_vertical_growth_rate * velocity
            w_lateral_turbulent = lateral_K / max(half_width, 1e-30)
            side_exchange = (2.0 * layer_depth * w_lateral_turbulent
                             if inp.lateral_turbulent_exchange else 0.0)
            perimeter_volume_entrainment = (
                2.0 * half_width * (w_vertical + w_wall_jet)
                + 2.0 * layer_depth * w_gravity + side_exchange
            )
            if advanced is None:
                current_dm_air_dx = (perimeter_volume_entrainment
                                     * inp.ambient_density_kg_m3 / max(velocity, .05))
            elif advanced.conservative_wall_profile:
                # The 3-D wall-jet half-width slopes describe redistribution
                # and secondary motion; they are not face-normal entrainment
                # speeds.  Ambient uptake is closed independently by a wall-
                # jet shear velocity plus the dense-cloud upper-face term.
                # This removes the former double counting of both vertical
                # growth and gravity spreading as fresh ambient volume.
                shear_entrainment_speed = advanced.wall_jet_entrainment_alpha * excess_u
                top_entrainment_speed = max(w_vertical, shear_entrainment_speed)
                side_entrainment_speed = shear_entrainment_speed
                if inp.lateral_turbulent_exchange:
                    side_entrainment_speed = max(side_entrainment_speed, w_lateral_turbulent)
                independent_volume_entrainment = (
                    2.0 * half_width * top_entrainment_speed
                    + 2.0 * layer_depth * side_entrainment_speed
                )
                current_dm_air_dx = independent_volume_entrainment * inp.ambient_density_kg_m3
            else:
                current_dm_air_dx = perimeter_volume_entrainment * inp.ambient_density_kg_m3
        rows.append(TransitionState(
            x, local_time_s, gas, liquid, air, condensed_water, air_from_ground_shear, total, y_h2, x_h2,
            temperature, density, velocity, excess_u, radius, half_width, layer_depth,
            centre_height if advanced is not None else (.5 * layer_depth if grounded else inp.release_height_m),
            buoyancy, lateral_K, ri, wall_cf, wall_sink, humidity_heat, ground_heat,
            droplet, inp.h2_rate_kg_s - gas - liquid, energy_residual,
            east_m, north_m, velocity_east, velocity_north, velocity_bearing, wind_alignment,
            nitrogen_gas, oxygen_gas, water_gas, condensed_nitrogen, condensed_oxygen,
            velocity_up, momentum_up, velocity_width, scalar_width,
            effective_transport_area, crossflow_speed, crossflow_drag,
            current_dm_air_dx, entrainment_model, area_now,
            scalar_profile_depth, scalar_centre_height, scalar_core_fraction,
            scalar_lateral_spread, scalar_vertical_spread,
        ))
        threshold = max(.1, excess_velocity_ratio * max(inp.ambient_wind_m_s, .1))
        if (stop_on_passive and x > 0
                and liquid <= liquid_tolerance * inp.h2_rate_kg_s
                and excess_u <= threshold):
            break
        dt = dx_m / max(velocity, .05)
        if not grounded:
            # Classical round-jet entrainment is retained for archived runs;
            # the opt-in route uses the audited HyRAM/JETPLU hybrid above.
            dm_air_dx = current_dm_air_dx
            air += dm_air_dx * dx_m
            if advanced is None:
                radius += inp.entrainment_alpha * dx_m
            else:
                volume_entrainment = dm_air_dx / max(inp.ambient_density_kg_m3, 1e-30)
                radius += (volume_entrainment
                           / max(2.0 * math.pi * radius * velocity, 1e-30)) * dx_m
                # Pressure drag rotates the jet toward the cross-flow.  The
                # buoyancy force is integrated in the same laboratory frame.
                momentum_east += drag_east * dx_m
                momentum_north += drag_north * dx_m
                if advanced.vertical_momentum:
                    buoyancy_force_up = density * buoyancy * area_now
                    momentum_up += (buoyancy_force_up + drag_up) * dx_m
        else:
            # Published Raj-equivalent gravity-current closure used by the
            # PHMSA/DEGADIS family.  It supplies horizontal gravity spreading
            # and vertical entrainment, replacing the previous duplicate
            # ground-shear term.
            # A ground-contacting horizontal jet is a wall jet, not a layer
            # frozen at twice the release height.  Its outer wall-normal
            # scale grows linearly in the self-similar regime.  The associated
            # volume growth entrains air through the upper face; keeping that
            # term in the integral balance prevents an artificial widening
            # without dilution.
            # The side-face turbulent exchange is the mass counterpart of
            # dB/dt = K_y/B.  Without it a cloud can become wider while its
            # sectional air inventory stays unchanged: an unphysical source
            # of cross-section-mean H2 concentration.  The gravity term was
            # already present; add only the turbulent component when the new
            # closure is explicitly selected.
            # perimeter [m] * face-normal speed [m/s] * rho [kg/m3]
            # already has the required d(mass-flow)/dx units.  The advanced
            # value was computed before exporting the state so the handoff
            # ledger can audit it; the legacy branch retains its archived
            # interpretation above.
            dm_air_dx = current_dm_air_dx
            air += dm_air_dx * dx_m
            air_from_ground_shear += dm_air_dx * dx_m
            if advanced is None:
                half_width += (w_gravity / max(velocity, .05)
                               + lateral_K / max(half_width * velocity, 1e-30)) * dx_m
                layer_depth += (w_vertical + w_wall_jet) / max(velocity, .05) * dx_m
                velocity_half_depth = .5 * layer_depth
            elif advanced.conservative_wall_profile:
                lateral_slope = max(
                    advanced.wall_lateral_half_width_growth_rate,
                    w_gravity / max(velocity, .05)
                    + lateral_K / max(half_width * velocity, 1e-30),
                )
                normal_slope = max(
                    advanced.wall_normal_half_width_growth_rate,
                    w_vertical / max(velocity, .05),
                )
                half_width += lateral_slope * dx_m
                velocity_half_depth += normal_slope * dx_m
                layer_depth = 2.0 * velocity_half_depth
                # Scalar and velocity half-widths have approximately equal
                # downstream growth in developed wall jets.  Their different
                # source widths are retained, rather than forcing a fixed
                # ratio at every station.
                scalar_lateral_spread += lateral_slope * dx_m
                scalar_vertical_spread += normal_slope * dx_m
            else:
                half_width += (w_gravity / max(velocity, .05)
                               + lateral_K / max(half_width * velocity, 1e-30)) * dx_m
                layer_depth += (w_vertical + w_wall_jet) / max(velocity, .05) * dx_m
                velocity_half_depth = .5 * layer_depth
            if vector_mode:
                pnorm = math.hypot(excess_east, excess_north)
                retained = max(0.0, 1.0 - wall_sink * dx_m / max(pnorm, 1e-30))
                momentum_east = total * wind_east + excess_east * retained
                momentum_north = total * wind_north + excess_north * retained
                momentum_up = 0.0
                if (advanced is not None
                        and advanced.wall_crosswind_drag_coefficient > 0.0):
                    # Pressure drag acts on the exposed vertical section of
                    # the wall cloud and exchanges laboratory-frame momentum
                    # with the local wind.  This is active whenever the
                    # declared wall-cloud drag coefficient is non-zero,
                    # including the dense attached phase; restricting it to
                    # the later ground-reaction switch left the attached
                    # plume artificially locked to the nozzle bearing.  The
                    # force is per streamwise metre, so its projected
                    # dimension is the cloud depth [m].
                    relative_e = wind_east - velocity_east
                    relative_n = wind_north - velocity_north
                    relative_speed = math.hypot(relative_e, relative_n)
                    if relative_speed > 0.0:
                        wall_drag = (
                            .5 * advanced.wall_crosswind_drag_coefficient
                            * inp.ambient_density_kg_m3 * relative_speed
                            * layer_depth
                        )
                        momentum_east += wall_drag * relative_e * dx_m
                        momentum_north += wall_drag * relative_n * dx_m
            else:
                excess_momentum = max(0.0, excess_momentum - wall_sink * dx_m)
            if advanced is not None and advanced.ground_reaction_liftoff:
                # Shallow-layer lateral momentum: pressure driving tends
                # toward the Raj gravity-current speed on the footprint
                # crossing time; after density reversal the same equation
                # supplies inertial spreading rather than an instantaneous
                # collapse to zero.
                lateral_acceleration = (
                    instantaneous_w_gravity ** 2 - wall_gravity_speed_m_s ** 2
                ) / max(half_width, layer_depth, 1e-30)
                wall_gravity_speed_m_s = max(
                    0.0, wall_gravity_speed_m_s + lateral_acceleration * dt
                )
                # Quadratic wall stress, using the existing skin-friction
                # coefficient and layer depth: no new fitted decay constant.
                wall_gravity_speed_m_s /= (
                    1.0 + 0.5 * wall_cf * wall_gravity_speed_m_s * dt
                    / max(layer_depth, 1e-30)
                )
        if vector_mode:
            # New ambient mass arrives carrying the instantaneous measured
            # wind momentum.  Keeping this separate from wall friction makes
            # a changing wind history a physical forcing rather than a route
            # rotation in post-processing.
            momentum_east += dm_air_dx * dx_m * wind_east
            momentum_north += dm_air_dx * dx_m * wind_north
        # d^2-law converted from time to streamwise distance.  It applies only
        # while the liquid phase remains suspended in the integral core.
        if droplet > 0:
            candidate = math.sqrt(max(0.0, droplet * droplet - inp.evaporation_kb_m2_s * dt))
            candidate_liquid = liquid0 * (candidate / inp.droplet_diameter_m) ** 3
            if cryogenic_phase_active and air > 0.0:
                from .cryogenic_air_phase import CryogenicPlugFlowInput, solve_cryogenic_plug_flow
                phase_after_entrainment = solve_cryogenic_plug_flow(CryogenicPlugFlowInput(
                    h2_gas_rate_kg_s=inp.h2_rate_kg_s - candidate_liquid,
                    h2_liquid_rate_kg_s=candidate_liquid,
                    reference_h2_gas_rate_kg_s=gas0, reference_h2_liquid_rate_kg_s=liquid0,
                    entrained_dry_air_rate_kg_s=air,
                    h2_source_temperature_K=inp.h2_temperature_K,
                    ambient_temperature_K=inp.ambient_temperature_K,
                    relative_humidity_percent=inp.ambient_relative_humidity_percent,
                    external_heat_W=geometric_ground_heat_W,
                ))
                retained_liquid = phase_after_entrainment.h2_liquid_rate_kg_s
            else:
                retained_liquid = max(candidate_liquid, _minimum_liquid_for_energy(
                    inp, liquid0=liquid0, air=air, condensed_water=condensed_water,
                    initial_energy_W=initial_energy, exchange_heat_W=humidity_heat + ground_heat,
                ))
            droplet = inp.droplet_diameter_m * (retained_liquid / liquid0) ** (1.0 / 3.0)
        if vector_mode:
            east_m += velocity_east * dt
            north_m += velocity_north * dt
            if advanced is not None and not grounded:
                centre_height = max(0.0, centre_height + velocity_up * dt)
            elif grounded:
                centre_height = .5 * layer_depth
            elapsed_s += dt
        # A moving cryogenic ground cloud has a calculated contact footprint:
        # dA = 2B dx.  With a semi-infinite solid, each footprint element has
        # a finite age bounded by the declared release duration.  Apply this
        # only while an LH2 or condensed-air phase is actually present; a warm
        # gas cloud has no perfect cryogenic thermal-contact boundary.
        condensed_contact_rate = liquid + condensed_nitrogen + condensed_oxygen + condensed_water
        if inp.geometric_ground_contact and grounded and condensed_contact_rate > 1e-10:
            assert inp.release_duration_s is not None
            contact_age = max(.01, inp.release_duration_s - local_time_s)
            q_flux = (inp.ground_thermal_conductivity_W_mK
                      * max(0.0, inp.ambient_temperature_K - temperature)
                      / math.sqrt(math.pi * inp.ground_thermal_diffusivity_m2_s * contact_age))
            geometric_ground_heat_W += q_flux * (2.0 * half_width) * dx_m
        x += dx_m
    return tuple(rows)


def select_handoff(rows: tuple[TransitionState, ...], *, h2_rate_kg_s: float,
                   liquid_tolerance: float = 1e-5, ground_contact_required: bool = True,
                   excess_velocity_m_s: float | None = None,
                   wind_alignment_tolerance_deg: float | None = None) -> TransitionState:
    """Return the first gas, ground-attached state suitable for SLAB handoff.

    SLAB carries an initial depth-averaged velocity, so decay to the ambient
    wind is *not* intrinsically a handoff requirement.  A caller may request
    an additional velocity guard for a passive-plume-only downstream model.
    """
    for row in rows:
        grounded = row.height_m <= .5 * row.layer_depth_m + 1e-9
        velocity_ok = excess_velocity_m_s is None or row.excess_velocity_m_s <= excess_velocity_m_s
        alignment_ok = (wind_alignment_tolerance_deg is None
                        or (row.wind_alignment_deg is not None
                            and row.wind_alignment_deg <= wind_alignment_tolerance_deg))
        if (row.x_m > 0 and row.h2_liquid_rate_kg_s <= liquid_tolerance * h2_rate_kg_s
                and (not ground_contact_required or grounded) and velocity_ok and alignment_ok):
            return row
    raise RuntimeError("transition did not satisfy the declared handoff guards within x_max")
