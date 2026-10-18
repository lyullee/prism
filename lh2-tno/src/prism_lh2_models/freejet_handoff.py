"""Conservative free-jet-to-SLABx handoff interface.

This module is deliberately model-neutral: HyRAM+ and JETPLU adapters must
resolve their own free-jet state and pass a :class:`FreeJetHandoffState`.
No upstream model is imported here.  This keeps the MIT handoff core separate
from optional upstream package licences and prevents a silent recreation of a
pure-nozzle ``HorizontalJet`` source after free-jet entrainment has occurred.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from slabx.core.source import SourceFlux, SourceModel, SourceState
from slabx.core.trajectory import Mode
from slabx.submodels.atmosphere import Atmosphere
from slabx.thermo.base import Substance


@dataclass(frozen=True)
class FreeJetHandoffState:
    """Resolved gas-mixture state on one declared downstream handoff plane.

    ``total_rate_kg_s`` is the total mixture rate across the equivalent
    rectangular section, while ``h2_mass_fraction`` identifies its hydrogen
    component.  The geometry is an *already declared* SLAB-equivalent
    rectangle; this class never derives it from a centreline value.
    """
    handoff_distance_m: float
    duration_s: float
    total_rate_kg_s: float
    h2_mass_fraction: float
    temperature_K: float
    density_kg_m3: float
    velocity_m_s: float
    centre_height_m: float
    half_width_m: float
    depth_m: float
    mixture_cp_J_kgK: float
    source_model: str
    geometry_closure: str

    def __post_init__(self) -> None:
        positive = (
            self.handoff_distance_m, self.duration_s, self.total_rate_kg_s,
            self.temperature_K, self.density_kg_m3, self.velocity_m_s,
            self.half_width_m, self.depth_m, self.mixture_cp_J_kgK,
        )
        if any(not math.isfinite(x) or x <= 0.0 for x in positive):
            raise ValueError("all dimensional handoff fields except centre height must be finite and positive")
        if not math.isfinite(self.centre_height_m) or self.centre_height_m < 0.0:
            raise ValueError("centre_height_m must be finite and non-negative")
        if not 0.0 < self.h2_mass_fraction <= 1.0:
            raise ValueError("h2_mass_fraction must be in (0, 1]")
        if not self.source_model.strip() or not self.geometry_closure.strip():
            raise ValueError("source_model and geometry_closure must be declared")

    @property
    def equivalent_area_m2(self) -> float:
        """Full rectangular area represented by SLAB half-width and depth."""
        return 2.0 * self.half_width_m * self.depth_m

    @property
    def h2_rate_kg_s(self) -> float:
        return self.total_rate_kg_s * self.h2_mass_fraction

    @property
    def geometry_rate_kg_s(self) -> float:
        return self.density_kg_m3 * self.velocity_m_s * self.equivalent_area_m2

    def mass_residual_relative(self) -> float:
        return abs(self.geometry_rate_kg_s - self.total_rate_kg_s) / self.total_rate_kg_s

    def validate(self, *, mass_tolerance: float = 0.02) -> None:
        if not 0.0 <= mass_tolerance < 1.0:
            raise ValueError("mass_tolerance must be in [0, 1)")
        residual = self.mass_residual_relative()
        if residual > mass_tolerance:
            raise ValueError(
                f"handoff geometry mass residual {residual:.3%} exceeds {mass_tolerance:.3%}; "
                "do not adjust the source to make SLABx fit downstream observations"
            )


@dataclass(frozen=True)
class NearFieldHandoff(SourceModel):
    """SLABx source whose initial mixture state is supplied by a free-jet model.

    This source begins downstream of the free-jet handoff plane and has no
    additional in-domain source flux.  It therefore preserves the supplied
    pre-diluted mixture rather than re-expanding an undiluted nozzle release.
    """
    substance: Substance
    state: FreeJetHandoffState
    mass_tolerance: float = 0.02
    name: str = "near_field_freejet_handoff"

    def __post_init__(self) -> None:
        self.state.validate(mass_tolerance=self.mass_tolerance)

    @property
    def duration(self) -> float:
        return self.state.duration_s

    @property
    def rate(self) -> float:
        """Hydrogen mass rate required by SLABx's common source interface."""
        return self.state.h2_rate_kg_s

    @property
    def T(self) -> float:
        """Declared mixed-plane temperature required by SLABx plume stages."""
        return self.state.temperature_K

    @property
    def half_width(self) -> float:
        return self.state.half_width_m

    @property
    def total_mass(self) -> float:
        return self.state.h2_rate_kg_s * self.duration

    def released_mass(self, t: float) -> float:
        return self.state.h2_rate_kg_s * min(max(t, 0.0), self.duration)

    def flux(self, x: float, t: float) -> SourceFlux:
        return SourceFlux()

    def initial_state(self, atm: Atmosphere, *, dx: float, **_: object) -> SourceState:
        """Return the declared mixture state without a source re-expansion."""
        s = self.state
        # SLAB's R uses its half-width convention.  The full-section mass rate
        # has already been checked as rho*u*(2*B*h), hence R = total_rate/2.
        return SourceState(
            x_start=s.handoff_distance_m,
            t_start=0.0,
            mode=Mode.PLUME,
            h=s.depth_m,
            z_c=s.centre_height_m,
            b_half=s.half_width_m,
            b_shape=0.9 * s.half_width_m,
            b_half_x=1.0,
            b_shape_x=1.0,
            u=s.velocity_m_s,
            T=s.temperature_K,
            rho=s.density_kg_m3,
            cp=s.mixture_cp_J_kgK,
            m_emission=s.h2_mass_fraction,
            m_ev=s.h2_mass_fraction,
            m_water=0.0,
            m_wv=0.0,
            u_ambient_mean=atm.wind_speed(max(s.centre_height_m + 0.5 * s.depth_m, 1e-6)),
            R_flux=0.5 * s.total_rate_kg_s,
        )


__all__ = ["FreeJetHandoffState", "NearFieldHandoff"]
