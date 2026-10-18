"""
Equipment-level damage.

The rest of this system computes risk to a person at a point on the
ground. That is the wrong question for equipment management, where what
is asked is: if TK-1101 releases, does VP-1101 survive.

Same physics, different query. The flux, overpressure and fragment reach
are already computed; what was missing is a threshold at which a piece of
equipment is taken to be damaged, and a loop over pairs.

Where the thresholds come from
------------------------------
API RP 581, Risk-Based Inspection Technology, second edition 2008,
section 5.8.2.3, read from the document:

    component damage      explosion overpressure    34.5 kPa
                          thermal radiation         37.8 kW/m2
                          flash fire                25% of the LFL area
    personnel injury      explosion overpressure    20.7 kPa
                          thermal radiation         12.6 kW/m2
                          flash fire                the LFL area

API states in the same paragraph that these criteria "are subject to
intensive scientific debate, and values other than those used in this
methodology could be suggested", and that the results were "intended to
produce a relative risk ranking". That is exactly the standing this
module has, and the caveat travels with every result.

A second source, Assael & Kakosimos, *Fires, Explosions and Toxic Gas
Dispersions*, Table C3.6, gives structural damage as a band rather than a
point, which is more honest about what a single number hides:

    glass, 5% fracture              0.7 to 1 kPa
    glass, 50% fracture             1.4 to 3
    doors and window frames         6 to 9
    wall construction, 50-70%       35 to 80
    near total demolition           80 to 260
    railway car derailment          80 to 190

API's 34.5 kPa sits at the bottom of the wall-destruction band, so the
two are consistent: API takes the point at which damage becomes likely
rather than certain.

What is deliberately NOT done
-----------------------------
**Fragility curves.** A curve needs a distribution of failure pressure
for each equipment type, and the published material gives thresholds and
bands, not distributions. Fitting a curve to a band would invent the
shape.

**Cryogenic equipment.** The relevant failure mode for a vacuum-jacketed
vessel is loss of vacuum from thermal shock, not rupture from
overpressure, and no threshold for that is published anywhere. Cryogenic
targets return NOT_EVALUATED rather than a verdict.

**Escalation.** Whether a damaged target then releases is a separate
question and needs a conditional release probability that does not exist
for hydrogen equipment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from taxonomy import Grade, Primitive, Provenance, Service, TranscriptionSource

# API RP 581 5.8.2.3, component damage criteria.
DAMAGE_OVERPRESSURE_PA = 34.5e3
DAMAGE_HEAT_FLUX_W_M2 = 37.8e3
DAMAGE_FLASH_FIRE_AREA_FRACTION = 0.25

# Same paragraph, personnel injury criteria. Carried for comparison; the
# grid risk elsewhere in this system uses probit relations rather than
# thresholds, and these are not a substitute for those.
INJURY_OVERPRESSURE_PA = 20.7e3
INJURY_HEAT_FLUX_W_M2 = 12.6e3

# Assael & Kakosimos Table C3.6, structural damage bands, Pa.
STRUCTURAL_BANDS = {
    "glass 5% fracture": (0.7e3, 1.0e3),
    "glass 50% fracture": (1.4e3, 3.0e3),
    "glass 90% fracture": (3.0e3, 6.0e3),
    "roof tiles displaced": (3.0e3, 5.0e3),
    "doors and window frames destroyed": (6.0e3, 9.0e3),
    "wall construction 50-70% destroyed": (35.0e3, 80.0e3),
    "near total demolition": (80.0e3, 260.0e3),
    "pillars destroyed": (80.0e3, 260.0e3),
    "railway car derailment": (80.0e3, 190.0e3),
}

# Equipment whose governing failure mode is not covered by these
# criteria. A vacuum-jacketed vessel fails by losing its vacuum to
# thermal shock long before it fails by overpressure, and no published
# threshold exists for that.
CRYOGENIC_PRIMITIVES = {Primitive.VESSEL, Primitive.PIPE, Primitive.HOSE,
                        Primitive.JOINT, Primitive.FLANGE, Primitive.VALVE,
                        Primitive.PUMP_SEAL, Primitive.VAPORIZER}

DAMAGE_PROV = Provenance(
    source="API RP 581 second edition (2008) section 5.8.2.3; "
           "Assael & Kakosimos Table C3.6 for the structural bands",
    grade=Grade.PUBLISHED_UNVALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="API states these criteria are subject to intensive scientific "
         "debate and that the results were intended to produce a relative "
         "risk ranking. They are thresholds, not fragility curves, and "
         "there is no cryogenic equivalent.",
    not_claimable_as=["a failure probability",
                      "a fragility curve",
                      "applicable to cryogenic equipment"],
)


class DamageVerdict(str, Enum):
    AFFECTED = "AFFECTED"
    POTENTIALLY_AFFECTED = "POTENTIALLY_AFFECTED"
    NOT_AFFECTED = "NOT_AFFECTED"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class Exposure:
    """What one target sees from one source."""
    heat_flux_w_m2: float = 0.0
    overpressure_pa: float = 0.0
    inside_fireball: bool = False
    inside_flammable_cloud: bool = False
    within_fragment_range: bool = False
    distance_m: float = 0.0
    possible_flame_contact: bool = False
    overpressure_is_lower_bound: bool = False


@dataclass(frozen=True)
class DamageAssessment:
    source_tag: str
    target_tag: str
    verdict: DamageVerdict
    reasons: tuple
    exposure: Exposure
    provenance: Provenance = None

    def statement(self) -> str:
        if self.verdict is DamageVerdict.NOT_EVALUATED:
            return (f"{self.source_tag} -> {self.target_tag}: not "
                    f"evaluated. {'; '.join(self.reasons)}")
        return (f"{self.source_tag} -> {self.target_tag} at "
                f"{self.exposure.distance_m:.0f} m: {self.verdict.value}"
                + (f" ({'; '.join(self.reasons)})" if self.reasons else ""))


def structural_band(overpressure_pa: float) -> Optional[str]:
    """The most severe band whose lower bound is exceeded.

    A band rather than a point, because Table C3.6 gives ranges and
    collapsing them to a midpoint would hide how wide they are."""
    eligible = (
        (lower_bound, name)
        for name, (lower_bound, _upper_bound) in STRUCTURAL_BANDS.items()
        if overpressure_pa >= lower_bound
    )
    return max(eligible, default=(0.0, None))[1]


def assess(source_tag: str, target_tag: str, exposure: Exposure,
           target_primitive: Optional[Primitive] = None,
           target_service: Optional[Service] = None) -> DamageAssessment:
    """Three-state verdict, per API's thresholds.

    Three states rather than a probability, because thresholds do not
    give one. AFFECTED means a damage criterion is exceeded;
    POTENTIALLY_AFFECTED means an injury criterion is but not a damage
    one, which is the band where equipment survives and people do not;
    NOT_EVALUATED means the governing failure mode is not covered."""
    reasons: list[str] = []

    cryogenic = (target_service is Service.LH2
                 or (target_service is Service.COLD_GH2))
    if cryogenic and target_primitive in CRYOGENIC_PRIMITIVES:
        return DamageAssessment(
            source_tag, target_tag, DamageVerdict.NOT_EVALUATED,
            ("the governing failure mode for vacuum-jacketed cryogenic "
             "equipment is loss of vacuum from thermal shock, not rupture "
             "from overpressure or radiation, and no published threshold "
             "exists for it",),
            exposure, DAMAGE_PROV)

    if exposure.inside_fireball:
        reasons.append("inside the fireball")
    if exposure.heat_flux_w_m2 >= DAMAGE_HEAT_FLUX_W_M2:
        reasons.append(f"{exposure.heat_flux_w_m2 / 1e3:.1f} kW/m2 exceeds "
                       f"{DAMAGE_HEAT_FLUX_W_M2 / 1e3:.1f}")
    if exposure.overpressure_pa >= DAMAGE_OVERPRESSURE_PA:
        band = structural_band(exposure.overpressure_pa)
        reasons.append(f"{exposure.overpressure_pa / 1e3:.1f} kPa exceeds "
                       f"{DAMAGE_OVERPRESSURE_PA / 1e3:.1f}"
                       + (f"; {band}" if band else ""))
    if reasons:
        return DamageAssessment(source_tag, target_tag,
                                DamageVerdict.AFFECTED, tuple(reasons),
                                exposure, DAMAGE_PROV)

    if exposure.possible_flame_contact:
        reasons.append("direct flame contact is possible for an unresolved release bearing")
    if exposure.overpressure_is_lower_bound:
        reasons.append("pressure is a lower bound with no resolved upper bound; "
                       "component damage cannot be ruled out")
    if exposure.within_fragment_range:
        reasons.append("within the fragment range band, though whether a "
                       "fragment arrives is not modelled")
    if exposure.inside_flammable_cloud:
        reasons.append("inside the flammable cloud; API takes 25% of the "
                       "LFL area as damaged and does not say which 25%")
    if exposure.heat_flux_w_m2 >= INJURY_HEAT_FLUX_W_M2:
        reasons.append(f"{exposure.heat_flux_w_m2 / 1e3:.1f} kW/m2 exceeds "
                       f"the personnel injury criterion")
    if exposure.overpressure_pa >= INJURY_OVERPRESSURE_PA:
        reasons.append(f"{exposure.overpressure_pa / 1e3:.1f} kPa exceeds "
                       f"the personnel injury criterion")
    if reasons:
        return DamageAssessment(source_tag, target_tag,
                                DamageVerdict.POTENTIALLY_AFFECTED,
                                tuple(reasons), exposure, DAMAGE_PROV)

    return DamageAssessment(source_tag, target_tag,
                            DamageVerdict.NOT_AFFECTED, (), exposure,
                            DAMAGE_PROV)


# --------------------------------------------------------------------------
# first-order escalation graph
# --------------------------------------------------------------------------

@dataclass
class EscalationGraph:
    """Which equipment each source can damage.

    ONE STEP ONLY, and no probabilities on the edges.

    A second step needs P(target releases | target damaged), and that
    number does not exist for hydrogen equipment. It is the same kind of
    gap as the pump seal frequency, and inventing it would undo the
    discipline the rest of this system rests on. What the paths alone
    give is still the thing equipment management asks for: what to
    protect, and from what.

    The recorded incidents show the sequence is real. HIAD 1076: vent
    stack under repair, vacuum valve opened, jacket pressurised,
    catastrophic tank rupture. HIAD 609: rupture disc opened, fire at the
    vent outlet, vacuum lost, rapid evaporation. Both are one piece of
    equipment taking another with it."""
    edges: list = field(default_factory=list)     # DamageAssessment
    not_evaluated: list = field(default_factory=list)

    def targets_of(self, source_tag: str) -> list:
        return [e for e in self.edges if e.source_tag == source_tag
                and e.verdict in (DamageVerdict.AFFECTED,
                                  DamageVerdict.POTENTIALLY_AFFECTED)]

    def sources_hitting(self, target_tag: str) -> list:
        return [e for e in self.edges if e.target_tag == target_tag
                and e.verdict in (DamageVerdict.AFFECTED,
                                  DamageVerdict.POTENTIALLY_AFFECTED)]

    def most_exposed(self) -> list:
        """Targets ranked by how many sources can reach them.

        A count, not a risk: each source has its own frequency and those
        are not combined here, because combining them would imply the
        edges carry probabilities and they do not."""
        counts: dict = {}
        for e in self.edges:
            if e.verdict in (DamageVerdict.AFFECTED,
                             DamageVerdict.POTENTIALLY_AFFECTED):
                counts[e.target_tag] = counts.get(e.target_tag, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])

    def lines(self) -> list[str]:
        out = [f"{len(self.edges)} source-target pairs evaluated, "
               f"{len(self.not_evaluated)} not evaluated"]
        affected = [e for e in self.edges
                    if e.verdict is DamageVerdict.AFFECTED]
        maybe = [e for e in self.edges
                 if e.verdict is DamageVerdict.POTENTIALLY_AFFECTED]
        out.append(f"  AFFECTED {len(affected)}, "
                   f"POTENTIALLY_AFFECTED {len(maybe)}")
        for tag, n in self.most_exposed()[:8]:
            out.append(f"    {tag:24s} reachable from {n} source(s)")
        if self.not_evaluated:
            tags = sorted({e.target_tag for e in self.not_evaluated})
            out.append(f"  not evaluated: {', '.join(tags[:6])}"
                       + (" and others" if len(tags) > 6 else ""))
        out.append("  edges carry NO probability: P(target releases | "
                   "damaged) does not exist for hydrogen equipment, so "
                   "this is one step and it stops here")
        return out


def build_graph(sources, targets, exposure_of) -> EscalationGraph:
    """sources and targets are anything with tag, primitive, service and
    position; exposure_of(source, target) returns an Exposure."""
    g = EscalationGraph()
    for s in sources:
        for t in targets:
            if s.tag == t.tag:
                continue
            a = assess(s.tag, t.tag, exposure_of(s, t),
                       getattr(t, "primitive", None),
                       getattr(t, "service", None))
            if a.verdict is DamageVerdict.NOT_EVALUATED:
                g.not_evaluated.append(a)
            else:
                g.edges.append(a)
    return g


WHY_ONE_STEP = (
    "A second step needs the probability that a damaged target then "
    "releases. That number does not exist for hydrogen equipment, and a "
    "multi-step graph built on an invented one would compound the "
    "invention at every hop. One step, no edge probabilities, and the "
    "paths reported as paths."
)

WHY_NOT_A_FRAGILITY_CURVE = (
    "A fragility curve needs a distribution of failure pressure for each "
    "equipment type. API gives a threshold and Assael & Kakosimos give a "
    "band; neither gives a distribution, and fitting a curve to a band "
    "would invent its shape. Three states is what the data supports."
)

WHY_CRYOGENIC_IS_REFUSED = (
    "A vacuum-jacketed vessel loses its vacuum to thermal shock long "
    "before it ruptures from overpressure. HIAD event 1224 records "
    "exactly that: a vacuum leak in the insulation annulus led to major "
    "cracks in the bottom of the outer shell. No published threshold "
    "gives the flux or duration at which that happens, so a cryogenic "
    "target returns NOT_EVALUATED rather than a verdict computed from "
    "criteria written for hydrocarbon pressure equipment."
)
