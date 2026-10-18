"""
Fragment throw from a vessel rupture.

Yellow Book (CPR 14E) and the Purple Book's own account of what a
catastrophic rupture produces. Until now the pipeline enumerated the
rupture, the fireball and the blast, and silently dropped the pieces of
the vessel.

Why it matters here specifically
---------------------------------
Two of the three LH2 tank explosions in HIAD ended with the vessel coming
apart: event 1076 records that "one end of the tank blew off", and event
1224 that a vacuum leak in the insulation annulus "led to major cracks in
the bottom of the outer shell". A vacuum-jacketed vessel has a second
shell whose brittle failure at cryogenic temperature is a recognised
sequence, and the project has been carrying "jacket brittle fracture and
fragment throw is a separate sequence, not enumerated" as a declared gap
for some time.

What is modelled
----------------
Ballistic range from an initial velocity, with drag, which is the
standard treatment. The initial velocity comes from the fraction of the
stored expansion energy that goes into the fragments -- the same
mechanical energy the blast module already computes from the Abel-Noble
equation of state, so the two share a source term and cannot disagree
about how much energy there was.

What is NOT modelled
--------------------
The number of fragments, their mass distribution and their departure
angles. Those depend on how the vessel fails, which depends on where the
flaw was, and no model here predicts that. The Purple Book's own position
is that fragment effects are treated by rule of thumb rather than
calculated, and it does not give a lethality relation at all.

So this returns a RANGE, not a probability of death. A range is what can
be defended; converting it to a fatality probability would need a hit
probability per unit area and a lethality given a hit, and neither exists
for hydrogen vessels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from fire import Coefficient, Confidence
from gating import Gated
from taxonomy import Grade, Provenance, TranscriptionSource

G = 9.81
RHO_AIR = 1.225

# Fraction of the stored expansion energy that becomes fragment kinetic
# energy. Baker and the Yellow Book both put it in the region of a fifth
# for a brittle vessel, with the rest going to the blast wave and to
# deforming the vessel. It is a wide band and it is treated as one.
KE_FRACTION_LOW = Coefficient(
    0.05, "f_KE low", "Baker et al.; a ductile vessel absorbs most of the "
                      "energy in deformation", Confidence.NEEDS_SOURCE)
KE_FRACTION_HIGH = Coefficient(
    0.40, "f_KE high", "Baker et al.; a brittle vessel at cryogenic "
                       "temperature releases most of it",
    Confidence.NEEDS_SOURCE)

# Drag coefficient and the lift-to-drag ratio of a tumbling fragment.
DRAG_COEFFICIENT = Coefficient(
    1.5, "C_D", "tumbling irregular fragment; Baker et al. give 1.0 to 2.0",
    Confidence.STRUCTURE_SOUND)

FRAGMENT_PROV = Provenance(
    source="Yellow Book (CPR 14E) fragment treatment; Baker et al. energy "
           "partition; HIAD events 1076 and 1224 for the failure mode",
    grade=Grade.ENGINEERING_JUDGEMENT,
    transcription=TranscriptionSource.UNVERIFIED,
    note="Range only. The number of fragments, their masses and their "
         "departure angles are not modelled because nothing here predicts "
         "how a vessel comes apart. The Purple Book gives no fragment "
         "lethality relation.",
    not_claimable_as=["a fragment hit probability",
                      "a fatality probability from fragments"],
)


@dataclass(frozen=True)
class Fragment:
    mass_kg: float
    initial_velocity_m_s: float
    range_m: float
    launch_angle_deg: float


@dataclass(frozen=True)
class FragmentThrow:
    energy_available_j: float
    ke_fraction_low: float
    ke_fraction_high: float
    fragment_mass_kg: float
    velocity_low_m_s: float
    velocity_high_m_s: float
    range_low_m: float
    range_high_m: float
    provenance: Provenance = None

    def statement(self) -> str:
        return (f"fragments of about {self.fragment_mass_kg:.0f} kg leave "
                f"at {self.velocity_low_m_s:.0f} to "
                f"{self.velocity_high_m_s:.0f} m/s and travel "
                f"{self.range_low_m:.0f} to {self.range_high_m:.0f} m")


def initial_velocity(energy_j: float, ke_fraction: float,
                     total_fragment_mass_kg: float) -> float:
    """v = sqrt(2 f E / m). The energy is shared over the fragments, so
    this is the velocity of the whole fragment mass moving together and
    an individual piece can exceed it."""
    m = max(total_fragment_mass_kg, 1e-9)
    return math.sqrt(2.0 * max(ke_fraction, 0.0) * max(energy_j, 0.0) / m)


def ballistic_range(v0: float, mass_kg: float, area_m2: float,
                    angle_deg: float = 45.0,
                    drag: bool = True, steps: int = 4000) -> float:
    """Range with quadratic drag, integrated rather than solved.

    Without drag the answer is v^2 sin(2 theta)/g and is wrong by a large
    factor for a light fragment at high speed, which is exactly the case
    a thin cryogenic outer shell produces."""
    if v0 <= 0.0:
        return 0.0
    th = math.radians(angle_deg)
    vx, vy = v0 * math.cos(th), v0 * math.sin(th)
    x, y = 0.0, 0.0
    k = (0.5 * RHO_AIR * float(DRAG_COEFFICIENT) * area_m2
         / max(mass_kg, 1e-9)) if drag else 0.0
    dt = 2.0 * v0 * math.sin(th) / G / steps
    for _ in range(steps * 4):
        v = math.hypot(vx, vy)
        ax = -k * v * vx
        ay = -G - k * v * vy
        vx += ax * dt
        vy += ay * dt
        x += vx * dt
        y += vy * dt
        if y < 0.0:
            break
    return max(x, 0.0)


def optimum_range(v0: float, mass_kg: float, area_m2: float) -> tuple:
    """The angle that maximises range is 45 degrees without drag and less
    with it, so it is searched rather than assumed."""
    best = (0.0, 45.0)
    for a in range(10, 60, 2):
        r = ballistic_range(v0, mass_kg, area_m2, float(a))
        if r > best[0]:
            best = (r, float(a))
    return best


def fragment_throw(mechanical_energy_j: float,
                   vessel_mass_kg: float,
                   n_fragments: int = 4,
                   fragment_area_m2: Optional[float] = None
                   ) -> FragmentThrow:
    """Range band for a vessel that comes apart.

    n_fragments defaults to four, which is the rule of thumb for a
    cylindrical vessel failing at a weld: two ends and two shell pieces.
    HIAD 1076 records exactly that outcome, one end blown off."""
    m_frag = max(vessel_mass_kg / max(n_fragments, 1), 1e-6)
    if fragment_area_m2 is None:
        # a plate of the same mass, 8 mm steel, presented edge-on to
        # edge-on tumbling: area scales as mass / (density x thickness)
        fragment_area_m2 = m_frag / (7850.0 * 0.008)
    v_lo = initial_velocity(mechanical_energy_j, float(KE_FRACTION_LOW),
                            vessel_mass_kg)
    v_hi = initial_velocity(mechanical_energy_j, float(KE_FRACTION_HIGH),
                            vessel_mass_kg)
    r_lo, _ = optimum_range(v_lo, m_frag, fragment_area_m2)
    r_hi, _ = optimum_range(v_hi, m_frag, fragment_area_m2)
    return FragmentThrow(
        energy_available_j=mechanical_energy_j,
        ke_fraction_low=float(KE_FRACTION_LOW),
        ke_fraction_high=float(KE_FRACTION_HIGH),
        fragment_mass_kg=m_frag,
        velocity_low_m_s=v_lo, velocity_high_m_s=v_hi,
        range_low_m=r_lo, range_high_m=r_hi,
        provenance=FRAGMENT_PROV)


def lethality(distance_m: float, throw: FragmentThrow) -> Gated[float]:
    """Refused.

    Converting a range to a fatality probability needs a hit probability
    per unit area, which needs the number of fragments and their angular
    distribution, and a lethality given a hit. None of those exist for
    hydrogen vessels, and the Purple Book gives no fragment lethality
    relation either. Returning a number here would be inventing one."""
    return Gated.refuse(
        "fragment_lethality",
        "fragment range is modelled; lethality is not. That needs a hit "
        "probability per unit area, which needs a fragment count and an "
        "angular distribution, and a lethality given a hit. The Purple "
        "Book gives no fragment lethality relation and neither does any "
        "hydrogen source in this project",
        bound=1.0 if distance_m <= throw.range_high_m else 0.0,
        bound_basis="inside the maximum range something can land; outside "
                    "it nothing can. That is a bound on presence, not on "
                    "harm")


VACUUM_JACKET_NOTE = (
    "A vacuum-jacketed vessel has an outer shell that is not designed to "
    "hold pressure -- the drawings in this project give 0.98 MPag outer "
    "against 1.034 MPag inner -- and that sits at cryogenic temperature "
    "if the vacuum is lost. EIGA TB 11/20 records the mechanism on a "
    "60,000 litre nitrogen tank: an internal-pipe leak locally cooled the "
    "carbon-steel jacket before brittle fracture and fragment ejection. "
    "This is transferable cryogenic evidence, not LH2 validation. The "
    "jacket is therefore a credible fragment source, but its sequence "
    "frequency is not established here."
)

NEEDS_SOURCE_LIST = [KE_FRACTION_LOW, KE_FRACTION_HIGH]
