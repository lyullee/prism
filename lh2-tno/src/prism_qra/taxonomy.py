"""
Tier 0 taxonomy, frequency library and physics model registry.  Revision 3.

Licensing posture (decision: A + D)
-----------------------------------
A.  No GPL code is used or linked. HyRAM+ is GPL-3.0-only with no linking
    exception, so every physics model is implemented from its PRIMARY
    publication, and each carries that citation. HyRAM+ is an implementation
    of those papers, not their author.

D.  HyRAM+ is installed locally and used only to cross-check results. It is
    never distributed, so no GPL obligation attaches. Cross-checks are
    registered rather than assumed.

Frequency values are facts, not code, and are cited to the underlying SAND
reports. Every value carries a TranscriptionSource so that anything not yet
read out of the report itself is visibly unverified.

Changes from revision 2
-----------------------
* Component list aligned to the Sandia standard set (adds exchanger,
  vaporizer, arm). These are the industry-standard slots even where no
  data exists for them.
* Per-(component, fuel) provenance. In the LH2 dataset only the storage
  vessel is LH2-specific; flange/hose/joint/pipe/valve are the gaseous
  values copied across, and they are graded accordingly.
* LNG removed from the LH2 proxy chain: it fills nothing that GH2 does not
  already fill, and is INF for exactly the components that GH2 is.
* rev2's filter row was wrong (values recalled, not read). Corrected and
  flagged for report verification.

Units are SI throughout.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------

class Grade(str, Enum):
    MEASURED = "MEASURED"
    PUBLISHED_VALIDATED = "PUBLISHED_VALIDATED"
    PUBLISHED_UNVALIDATED = "PUBLISHED_UNVALIDATED"
    ENGINEERING_JUDGEMENT = "ENGINEERING_JUDGEMENT"
    PLACEHOLDER = "PLACEHOLDER"


_ORDER = [Grade.MEASURED, Grade.PUBLISHED_VALIDATED,
          Grade.PUBLISHED_UNVALIDATED, Grade.ENGINEERING_JUDGEMENT,
          Grade.PLACEHOLDER]


class TranscriptionSource(str, Enum):
    """Where the number in this file physically came from."""
    REPORT = "REPORT"                  # read from the cited publication
    CODE_INSPECTION = "CODE_INSPECTION"  # observed in GPL source; must be
                                         # re-read from the report before use
    UNVERIFIED = "UNVERIFIED"


class Provenance(BaseModel):
    source: str
    grade: Grade
    transcription: TranscriptionSource = TranscriptionSource.UNVERIFIED
    note: str = ""
    not_claimable_as: list[str] = Field(default_factory=list)

    @staticmethod
    def weakest(items: list["Provenance"]) -> Grade:
        return max((p.grade for p in items), key=_ORDER.index)


# --------------------------------------------------------------------------
# enumerations
# --------------------------------------------------------------------------

class Service(str, Enum):
    GH2 = "GH2"
    COLD_GH2 = "COLD_GH2"
    LH2 = "LH2"


class Fuel(str, Enum):
    LH2 = "LH2"
    GH2 = "GH2"
    OANDG = "OANDG"


class Primitive(str, Enum):
    # Sandia standard component set
    COMPRESSOR = "COMPRESSOR"
    VESSEL = "VESSEL"
    FILTER = "FILTER"
    FLANGE = "FLANGE"
    HOSE = "HOSE"
    JOINT = "JOINT"
    PIPE = "PIPE"
    VALVE = "VALVE"
    INSTRUMENT = "INSTRUMENT"
    EXCHANGER = "EXCHANGER"
    VAPORIZER = "VAPORIZER"
    ARM = "ARM"
    # our own additions; no standard Sandia slot exists
    PUMP_SEAL = "PUMP_SEAL"
    VENT_STACK = "VENT_STACK"


class Assembly(str, Enum):
    """Input conveniences that decompose into primitives with data.
    Preferred over the bare primitive wherever the primitive has no data."""
    VAPORIZER_UNIT = "VAPORIZER_UNIT"
    LH2_PUMP = "LH2_PUMP"
    LOADING_ARM_UNIT = "LOADING_ARM_UNIT"
    DISPENSER = "DISPENSER"
    VJ_LINE = "VJ_LINE"
    VENT_SYSTEM = "VENT_SYSTEM"


class Orientation(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    HORIZONTAL = "HORIZONTAL"


class ReleasePath(str, Enum):
    DIRECT = "DIRECT"
    VIA_RELIEF = "VIA_RELIEF"   # designed relief, high-vapour two-phase flow
    VIA_VENT = "VIA_VENT"       # through the vent stack, at its outlet height


class DischargeCoefficientBasis(str, Enum):
    """Evidence class for an equipment-specific discharge coefficient.

    Cd=1 remains the conservative source-term default.  Any lower value is
    accepted only with an explicit basis and a traceable note, so a fitted
    coefficient cannot silently become an independently validated property.
    """
    CONSERVATIVE_DEFAULT = "CONSERVATIVE_DEFAULT"
    ENGINEERING_ASSUMPTION = "ENGINEERING_ASSUMPTION"
    MANUFACTURER_CERTIFIED = "MANUFACTURER_CERTIFIED"
    MEASURED = "MEASURED"
    CALIBRATED = "CALIBRATED"


class PhysicsRoute(str, Enum):
    GH2_JET = "GH2_JET"          # own implementation, primary-source models
    SLABX_LH2 = "SLABX_LH2"
    UNCOVERED = "UNCOVERED"


# --------------------------------------------------------------------------
# physics model registry  (the "A" half of A+D)
# --------------------------------------------------------------------------

class ImplStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    PLANNED = "PLANNED"
    NOT_STARTED = "NOT_STARTED"


class PhysicsModel(BaseModel):
    """A model we implement ourselves, cited to its primary publication.
    cross_check records whether an independent tool has been compared."""
    key: str
    purpose: str
    primary_source: str
    status: ImplStatus = ImplStatus.NOT_STARTED
    cross_check_tool: Optional[str] = None
    cross_check_result: Optional[str] = None


MODEL_REGISTRY: dict[str, PhysicsModel] = {m.key: m for m in [
    PhysicsModel(key="notional_nozzle_birch",
                 purpose="underexpanded jet effective source",
                 primary_source="Birch et al. (1984/1987)"),
    PhysicsModel(key="notional_nozzle_ewan_moodie",
                 purpose="underexpanded jet effective source",
                 primary_source="Ewan & Moodie (1986)"),
    PhysicsModel(key="notional_nozzle_yuceil_otugen",
                 purpose="underexpanded jet effective source",
                 primary_source="Yuceil & Otugen (2002)"),
    PhysicsModel(key="real_gas_eos",
                 purpose="H2 compressibility at 350-700 bar",
                 primary_source="CoolProp (MIT) / Abel-Noble",
                 status=ImplStatus.PLANNED),
    PhysicsModel(key="flame_length_molkov",
                 purpose="H2 jet flame length",
                 primary_source="Molkov & Saffers (2013)"),
    PhysicsModel(key="radiant_multisource",
                 purpose="jet flame radiant heat flux",
                 primary_source="Hankinson & Lowesmith (2012); Ekoto et al."),
    PhysicsModel(key="unconfined_overpressure_bst",
                 purpose="unconfined vapour cloud overpressure",
                 primary_source="Baker-Strehlow-Tang; Bauwens et al."),
    PhysicsModel(key="slabx_lh2",
                 purpose="LH2 dispersion, LFL distance",
                 primary_source="this project (SLAB extension, MIT)",
                 status=ImplStatus.IMPLEMENTED,
                 cross_check_tool="FFI / NASA / PRESLHY trials",
                 cross_check_result="5 of 6 FFI trials within band; x1.25 factor"),
    PhysicsModel(key="probit_thermal_green",
                 purpose="thermal dose to lethality",
                 primary_source="Green Book (CPR 16), Purple Book 5.2.3"),
    PhysicsModel(key="cold_gh2_dispersion",
                 purpose="30-250 K hydrogen release",
                 primary_source="NOT ESTABLISHED -- declared gap"),
]}


# --------------------------------------------------------------------------
# leak size binning
# --------------------------------------------------------------------------

class LeakBin(BaseModel):
    label: str
    area_fraction: Optional[float] = Field(default=None, gt=0, le=1.0)
    absolute_diameter_m: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one_of(self):
        if (self.area_fraction is None) == (self.absolute_diameter_m is None):
            raise ValueError(f"{self.label}: give exactly one sizing basis")
        return self

    def hole_diameter(self, nominal_d: float) -> float:
        if self.absolute_diameter_m is not None:
            return min(self.absolute_diameter_m, nominal_d)
        return nominal_d * math.sqrt(self.area_fraction)


HYRAM_BINS = [LeakBin(label=label, area_fraction=fraction)
              for label, fraction in
              [("0.01%", 1e-4), ("0.1%", 1e-3), ("1%", 1e-2),
               ("10%", 1e-1), ("100%", 1.0)]]
BIN_LABELS = [b.label for b in HYRAM_BINS]


# --------------------------------------------------------------------------
# frequency library, keyed per (component, fuel) with its own provenance
# --------------------------------------------------------------------------

_SAND_GH2 = "SAND2024-06491 Table 1-1 (HyRAM+ v5.1 defaults)"
_BROOKS = ("Brooks, Ehrhart & LaFleur (2021), 'Development of Liquid Hydrogen "
           "Leak Frequencies Using a Bayesian Update Process', ICHS 2021, Table 2")
_LH2_NOTE = ("Hierarchical Bayesian update combining gaseous hydrogen and "
             "liquefied natural gas data. No liquid hydrogen data exists to "
             "validate or calibrate against.")
_OANDG_SRC = "oil & gas reciprocating pump data, as used in published LH2 QRA"

_CODE = TranscriptionSource.CODE_INSPECTION


class FrequencyEntry(BaseModel):
    primitive: Primitive
    fuel: Fuel
    medians: list[float]                       # aligned to BIN_LABELS
    provenance: Provenance
    conservatism_factor: float = 1.0
    # lognormal parameters on ln(frequency), where the source gives them.
    # A median alone hides that these span roughly an order of magnitude
    # either side, which matters more than most of the physics.
    mu: Optional[list[float]] = None
    sigma: Optional[list[float]] = None

    def percentile(self, p: float) -> Optional[list[float]]:
        if self.mu is None or self.sigma is None:
            return None
        from statistics import NormalDist
        z = NormalDist().inv_cdf(p)
        return [math.exp(m + z * s) for m, s in zip(self.mu, self.sigma)]


def _entry(prim, fuel, meds, src, grade, note, trans=_CODE, cf=1.0, nca=None,
           mu=None, sigma=None):
    return FrequencyEntry(
        primitive=prim, fuel=fuel, medians=meds, conservatism_factor=cf,
        mu=mu, sigma=sigma,
        provenance=Provenance(source=src, grade=grade, transcription=trans,
                              note=note, not_claimable_as=nca or []))


_GH2_NOTE = ("Bayesian-updated from hydrocarbon and hydrogen service data. "
             "Read from SAND2024-06491 Table 1-1.")

_LIB: list[FrequencyEntry] = [
    # ---- gaseous hydrogen -------------------------------------------------
    _entry(Primitive.COMPRESSOR, Fuel.GH2,
           [9.97e-2, 1.70e-2, 4.57e-3, 1.52e-4, 1.46e-5],
           _SAND_GH2, Grade.PUBLISHED_VALIDATED, _GH2_NOTE,
           trans=TranscriptionSource.REPORT),
    _entry(Primitive.VESSEL, Fuel.GH2,
           [1.40e-6, 1.19e-6, 7.90e-7, 4.50e-7, 2.33e-7],
           _SAND_GH2, Grade.PUBLISHED_VALIDATED, _GH2_NOTE,
           trans=TranscriptionSource.REPORT),
    # SAND2024-06491 exists specifically to replace this row. Table 1-1
    # carries the v5.1 values, which made filters dominate every gaseous
    # hydrogen QRA; Table 4-1 is the recommendation that supersedes them
    # and drops the full-bore bin by a factor of ninety. Both were seen
    # during this work -- the older set from memory, the newer from the
    # software -- and neither was recognised as belonging to a different
    # revision until the report was opened.
    _entry(Primitive.FILTER, Fuel.GH2,
           [2.49e-3, 9.31e-4, 3.51e-4, 1.29e-4, 4.79e-5],
           "SAND2024-06491 Table 4-1 (supersedes Table 1-1 / HyRAM+ v5.1)",
           Grade.PUBLISHED_VALIDATED,
           "Updated filter leak frequencies. The report states the new "
           "values leave filters among the top contributors but no longer "
           "an order of magnitude above other components. Uncertainty is "
           "given as lognormal on ln(frequency) and is carried here.",
           trans=TranscriptionSource.REPORT,
           mu=[-5.99, -6.98, -7.96, -8.95, -9.94],
           sigma=[0.606, 0.585, 0.626, 0.718, 0.674]),
    _entry(Primitive.FLANGE, Fuel.GH2,
           [2.00e-2, 2.20e-3, 2.42e-4, 2.67e-5, 2.94e-6],
           _SAND_GH2, Grade.PUBLISHED_VALIDATED, _GH2_NOTE,
           trans=TranscriptionSource.REPORT),
    _entry(Primitive.HOSE, Fuel.GH2,
           [5.79e-4, 2.03e-4, 1.65e-4, 1.51e-4, 6.17e-5],
           _SAND_GH2, Grade.PUBLISHED_VALIDATED, _GH2_NOTE,
           trans=TranscriptionSource.REPORT),
    _entry(Primitive.JOINT, Fuel.GH2,
           [3.50e-5, 4.69e-6, 7.53e-6, 7.53e-6, 6.40e-6],
           _SAND_GH2, Grade.PUBLISHED_VALIDATED, _GH2_NOTE,
           trans=TranscriptionSource.REPORT),
    _entry(Primitive.PIPE, Fuel.GH2,
           [8.02e-6, 3.70e-6, 9.56e-7, 4.61e-7, 1.47e-7],
           _SAND_GH2, Grade.PUBLISHED_VALIDATED, _GH2_NOTE,
           trans=TranscriptionSource.REPORT),
    _entry(Primitive.VALVE, Fuel.GH2,
           [2.87e-3, 5.86e-4, 5.44e-5, 2.47e-5, 4.82e-6],
           _SAND_GH2, Grade.PUBLISHED_VALIDATED, _GH2_NOTE,
           trans=TranscriptionSource.REPORT),
    _entry(Primitive.INSTRUMENT, Fuel.GH2,
           [6.24e-4, 1.95e-4, 1.12e-4, 1.00e-4, 3.68e-5],
           _SAND_GH2, Grade.PUBLISHED_VALIDATED, _GH2_NOTE,
           trans=TranscriptionSource.REPORT),

    # ---- liquid hydrogen --------------------------------------------------
    # Brooks, Ehrhart & LaFleur (2021), Table 2. Estimated by hierarchical
    # Bayesian update of gaseous hydrogen with liquefied natural gas: proxy
    # data, but combined, not copied. An earlier reading of this project
    # had these as the gaseous values carried across unchanged, which they
    # are not -- the LH2 vessel median is 36x the gaseous one at the 1% bin
    # and 461x at 0.01%.
    #
    # The paper states plainly that the accuracy of these estimates is
    # difficult to judge without liquid hydrogen data for validation, so
    # they stay PUBLISHED_UNVALIDATED however precise the numbers look.
    #
    # Two of the six behave backwards: for hoses and joints the larger
    # leaks are slightly MORE frequent than the smaller ones, and the
    # authors say they cannot tell whether that is physical or an artefact.
    # It is transcribed as published rather than smoothed.
    _entry(Primitive.FLANGE, Fuel.LH2,
           [5.00e-05, 2.20e-05, 1.10e-05, 5.00e-06, 2.40e-06],
           _BROOKS, Grade.PUBLISHED_UNVALIDATED, _LH2_NOTE,
           trans=TranscriptionSource.REPORT,
           mu=[-9.9035, -10.7245, -11.4176, -12.2061, -12.9400],
           sigma=[0.6593, 1.2346, 2.5121, 3.0240, 2.9341],
           nca=["a measured LH2 leak frequency"]),
    _entry(Primitive.HOSE, Fuel.LH2,
           [1.10e-04, 9.00e-05, 1.20e-04, 1.20e-04, 1.30e-04],
           _BROOKS, Grade.PUBLISHED_UNVALIDATED, _LH2_NOTE,
           trans=TranscriptionSource.REPORT,
           mu=[-9.1150, -9.3157, -9.0280, -9.0280, -8.9480],
           sigma=[1.2245, 2.0141, 4.5895, 0.8391, 3.6997],
           nca=["a measured LH2 leak frequency"]),
    _entry(Primitive.JOINT, Fuel.LH2,
           [9.00e-05, 1.20e-04, 1.70e-04, 2.40e-04, 3.30e-04],
           _BROOKS, Grade.PUBLISHED_UNVALIDATED, _LH2_NOTE,
           trans=TranscriptionSource.REPORT,
           mu=[-9.3157, -9.0280, -8.6797, -8.3349, -8.0164],
           sigma=[0.9482, 1.3266, 1.2400, 2.8133, 1.4723],
           nca=["a measured LH2 leak frequency"]),
    _entry(Primitive.PIPE, Fuel.LH2,
           [3.40e-06, 1.60e-06, 8.00e-07, 3.90e-07, 1.90e-07],
           _BROOKS, Grade.PUBLISHED_UNVALIDATED, _LH2_NOTE,
           trans=TranscriptionSource.REPORT,
           mu=[-12.5917, -13.3455, -14.0387, -14.7571, -15.4762],
           sigma=[1.4263, 1.5083, 1.4420, 1.4553, 2.0530],
           nca=["a measured LH2 leak frequency"]),
    _entry(Primitive.VALVE, Fuel.LH2,
           [1.20e-04, 5.20e-05, 2.20e-05, 9.30e-06, 3.90e-06],
           _BROOKS, Grade.PUBLISHED_UNVALIDATED, _LH2_NOTE,
           trans=TranscriptionSource.REPORT,
           mu=[-9.0280, -9.8643, -10.7245, -11.5855, -12.4545],
           sigma=[0.6080, 1.0924, 1.4405, 2.0154, 1.9641],
           nca=["a measured LH2 leak frequency"]),
    _entry(Primitive.VESSEL, Fuel.LH2,
           [6.50e-04, 1.40e-04, 2.80e-05, 5.70e-06, 1.20e-06],
           _BROOKS, Grade.PUBLISHED_UNVALIDATED, _LH2_NOTE,
           trans=TranscriptionSource.REPORT,
           mu=[-7.3385, -8.8739, -10.4833, -12.0750, -13.6332],
           sigma=[1.7362, 2.5388, 2.0482, 2.7186, 3.1277],
           nca=["a measured LH2 leak frequency"]),

    # ---- rotating cryogenic equipment ------------------------------------
    # Cryogenic pump. Published LH2 QRA identifies the cryogenic pump as
    # the most probable source of a rupture and estimates it from
    # reciprocating pump data in the oil and gas field, noting that a
    # cryogenic hydrogen pump should be expected to leak more, from harsh
    # duty and from embrittlement. The named database is OREDA.
    #
    # The bin values here are still not read from OREDA -- that is a
    # subscription database and is not in the project -- so they remain
    # unsourced. What has changed is the factor of 10 that stood on top
    # of them: it was invented, and the literature says only "higher",
    # not "ten times higher". An unsourced number multiplied by an
    # invented factor is worse than an unsourced number, because the
    # product looks deliberate. The factor is removed and the direction
    # of the bias is recorded instead.
    _entry(Primitive.PUMP_SEAL, Fuel.OANDG,
           [1.0e-2, 3.0e-3, 5.0e-4, 1.0e-4, 1.0e-5],
           "reciprocating pump data, oil and gas; OREDA is the database "
           "named by published LH2 QRA. Values here are NOT read from it.",
           Grade.ENGINEERING_JUDGEMENT,
           "TWO independent published LH2 station QRAs name the cryogenic "
           "pump as the dominant risk unit: Jiepu et al. (2026) classify "
           "the booster-pump system D2 at a 5 mm leak with public "
           "individual risk outside the boundary exceeding the criterion, "
           "and Yoo et al. (2021) assign it 5.0e-5/yr for catastrophic "
           "rupture citing their ref [60]. Both expect a HIGHER rate than "
           "this proxy without quantifying how much. So the component most "
           "likely to dominate the answer carries the weakest evidence in "
           "the library. Tracing Yoo ref [60] is the highest-value "
           "outstanding data task.",
           trans=TranscriptionSource.UNVERIFIED, cf=1.0,
           nca=["a validated frequency", "a conservative estimate"]),
]

FREQUENCY_LIBRARY: dict[tuple[Primitive, Fuel], FrequencyEntry] = {
    (e.primitive, e.fuel): e for e in _LIB}

# Components with no published frequency for any fuel. Declared, not guessed.
NO_DATA = {Primitive.EXCHANGER, Primitive.VAPORIZER, Primitive.ARM,
           Primitive.VENT_STACK}

# LNG is deliberately absent: it is INF for exactly the components GH2 is
# INF for, so it fills nothing.
PROXY_CHAIN: dict[Service, list[Fuel]] = {
    Service.LH2:      [Fuel.LH2, Fuel.OANDG, Fuel.GH2],
    Service.COLD_GH2: [Fuel.GH2],
    Service.GH2:      [Fuel.GH2],
}

_PENALTY: dict[tuple[Service, Fuel], Grade] = {
    (Service.LH2, Fuel.GH2):      Grade.ENGINEERING_JUDGEMENT,
    (Service.LH2, Fuel.OANDG):    Grade.ENGINEERING_JUDGEMENT,
    (Service.COLD_GH2, Fuel.GH2): Grade.ENGINEERING_JUDGEMENT,
}

_NONE = Provenance(
    source="not established", grade=Grade.PLACEHOLDER,
    transcription=TranscriptionSource.REPORT,
    note="No published leak frequency exists for this component in any fuel. "
         "Sandia marks these as infinite rather than estimating them.",
    not_claimable_as=["a frequency", "a screening estimate"])


class Resolved(BaseModel):
    values: dict[str, float]
    provenance: Provenance
    fuel_used: Optional[Fuel] = None
    conservatism: float = 1.0


def resolve_frequency(primitive: Primitive, service: Service) -> Resolved:
    for fuel in PROXY_CHAIN.get(service, []):
        e = FREQUENCY_LIBRARY.get((primitive, fuel))
        if e is None:
            continue
        grade = e.provenance.grade
        floor = _PENALTY.get((service, fuel))
        if floor is not None and _ORDER.index(floor) > _ORDER.index(grade):
            grade = floor
        note = e.provenance.note
        if fuel.value != service.value:
            note = f"proxy: {fuel.value} data used for {service.value}. " + note
        cf = e.conservatism_factor
        if cf != 1.0:
            note += f" Conservatism factor {cf:g} applied."
        return Resolved(
            values={label: value * cf
                    for label, value in zip(BIN_LABELS, e.medians)},
            fuel_used=fuel, conservatism=cf,
            provenance=Provenance(source=e.provenance.source, grade=grade,
                                  transcription=e.provenance.transcription,
                                  note=note,
                                  not_claimable_as=e.provenance.not_claimable_as))
    return Resolved(values={label: float("nan") for label in BIN_LABELS},
                    provenance=_NONE)


# --------------------------------------------------------------------------
# facility description
# --------------------------------------------------------------------------

class Position(BaseModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    z: float = Field(default=0.0, allow_inf_nan=False)


class Section(BaseModel):
    id: str
    inventory_kg: float = Field(gt=0)
    isolation_time_s: float = Field(default=600.0, gt=0)
    service: Service


class UpstreamLine(BaseModel):
    """Finite supply/vent path between the inventory and terminal breach.

    A missing object means the established sharp-hole source remains in use.
    Roughness defaults to a hydraulically smooth upper-flow case; fittings
    can be aggregated in the dimensionless minor-loss coefficient.
    """
    length_m: float = Field(gt=0)
    diameter_m: float = Field(gt=0)
    roughness_m: float = Field(default=0.0, ge=0)
    minor_loss_k: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _roughness_range(self):
        if self.roughness_m / self.diameter_m >= 0.1:
            raise ValueError("upstream line relative roughness must be below 0.1")
        return self


class ComponentSpec(BaseModel):
    primitive: Primitive
    service: Service
    count: int = Field(default=1, ge=1)
    nominal_diameter_m: float = Field(gt=0)
    pressure_pa: float = Field(gt=0)
    temperature_k: float = Field(gt=0)
    orientation: Orientation = Orientation.HORIZONTAL
    # Plan-view direction measured counter-clockwise from the +x site axis.
    # None means the leak bearing is unknown and is averaged over bearings
    # in individual-risk calculations.
    release_azimuth_deg: Optional[float] = Field(default=None, ge=0, lt=360)
    position: Position
    section_id: str
    tag: str = ""
    release_path: ReleasePath = ReleasePath.DIRECT
    secondary_breach_probability: float = Field(default=1.0, gt=0, le=1.0)
    # Effective bore of the relief path, for releases that leave through a
    # designed device rather than through the failed component. A loss of
    # vacuum does not open a hole the size of the pipe; it raises the
    # pressure until the relief lifts, and the relief then sets the rate.
    relief_diameter_m: Optional[float] = Field(default=None, gt=0)
    upstream_line: Optional[UpstreamLine] = None
    discharge_coefficient: float = Field(default=1.0, gt=0, le=1.0)
    discharge_coefficient_basis: DischargeCoefficientBasis = (
        DischargeCoefficientBasis.CONSERVATIVE_DEFAULT
    )
    discharge_coefficient_note: str = ""

    @model_validator(mode="after")
    def _line_can_feed_terminal(self):
        terminal_diameter = self.relief_diameter_m or self.nominal_diameter_m
        if (self.upstream_line is not None
                and self.upstream_line.diameter_m < terminal_diameter):
            raise ValueError(
                "upstream line diameter cannot be smaller than the maximum "
                "terminal leak/relief diameter")
        return self

    @model_validator(mode="after")
    def _coefficient_is_traceable(self):
        if (not math.isclose(self.discharge_coefficient, 1.0)
                and self.discharge_coefficient_basis
                is DischargeCoefficientBasis.CONSERVATIVE_DEFAULT):
            raise ValueError(
                "a discharge coefficient below 1 requires an explicit basis")
        if (self.discharge_coefficient_basis
                is not DischargeCoefficientBasis.CONSERVATIVE_DEFAULT
                and not self.discharge_coefficient_note.strip()):
            raise ValueError(
                "a non-default discharge coefficient basis requires a "
                "source/test note")
        return self


class AssemblySpec(BaseModel):
    assembly: Assembly
    service: Service
    count: int = Field(default=1, ge=1)
    nominal_diameter_m: float = Field(gt=0)
    pressure_pa: float = Field(gt=0)
    temperature_k: float = Field(gt=0)
    release_azimuth_deg: Optional[float] = Field(default=None, ge=0, lt=360)
    position: Position
    section_id: str
    tag: str = ""

    # Effective relief bore for a vacuum-jacketed line. Back-solved at
    # 6 bar from the conservative Q=0.55 state to reproduce the one
    # recorded 0.10 kg/s scale. It is not a design value, and a site with
    # its own relief sizing or certified capacity should override it.
    relief_diameter_m: Optional[float] = Field(default=None, gt=0)
    upstream_line: Optional[UpstreamLine] = None
    discharge_coefficient: float = Field(default=1.0, gt=0, le=1.0)
    discharge_coefficient_basis: DischargeCoefficientBasis = (
        DischargeCoefficientBasis.CONSERVATIVE_DEFAULT
    )
    discharge_coefficient_note: str = ""

    @model_validator(mode="after")
    def _line_can_feed_assembly(self):
        if (self.upstream_line is not None
                and self.upstream_line.diameter_m
                < self.nominal_diameter_m):
            raise ValueError(
                "upstream line diameter cannot be smaller than the assembly "
                "nominal diameter")
        return self

    @model_validator(mode="after")
    def _coefficient_is_traceable(self):
        if (not math.isclose(self.discharge_coefficient, 1.0)
                and self.discharge_coefficient_basis
                is DischargeCoefficientBasis.CONSERVATIVE_DEFAULT):
            raise ValueError(
                "a discharge coefficient below 1 requires an explicit basis")
        if (self.discharge_coefficient_basis
                is not DischargeCoefficientBasis.CONSERVATIVE_DEFAULT
                and not self.discharge_coefficient_note.strip()):
            raise ValueError(
                "a non-default discharge coefficient basis requires a "
                "source/test note")
        return self

    def expand(self) -> list[ComponentSpec]:
        out = []
        rd = self.relief_diameter_m
        if rd is None and self.assembly is Assembly.VJ_LINE:
            rd = VJ_RELIEF_DIAMETER_M
        for prim, n, orient, path, pb in ASSEMBLY_COMPOSITION[self.assembly]:
            out.append(ComponentSpec(
                primitive=prim, service=self.service, count=n * self.count,
                nominal_diameter_m=self.nominal_diameter_m,
                pressure_pa=self.pressure_pa, temperature_k=self.temperature_k,
                orientation=orient, position=self.position,
                release_azimuth_deg=self.release_azimuth_deg,
                section_id=self.section_id,
                tag=f"{self.tag}/{prim.value}" if self.tag else prim.value,
                release_path=path, secondary_breach_probability=pb,
                relief_diameter_m=(rd if path is ReleasePath.VIA_RELIEF
                                   else None),
                upstream_line=self.upstream_line,
                discharge_coefficient=self.discharge_coefficient,
                discharge_coefficient_basis=self.discharge_coefficient_basis,
                discharge_coefficient_note=self.discharge_coefficient_note))
        return out


# Effective relief state and bore of a vacuum-jacketed line. The recorded
# discharge was initially 80--100% vapour and later 55--88% vapour. The
# lower vapour-quality edge (Q=0.55) is used as the conservative high-density
# source state, and the bore is back-solved from the one recorded rate:
# 0.10 kg/s at 6 bar gives 8.585 mm. It is a scale, not a design value, and
# a site that knows its own relief sizing/capacity should override it.
#
# The recorded 13 bar is ABOVE the hydrogen critical pressure of
# 12.86 bar, which is why the incident report describes the liquid and
# vapour densities converging after two and a half hours. The saturated
# liquid assumption does not hold there, so the bore is fitted at 6 bar,
# a normal LH2 operating pressure, rather than at the relief setting.
VJ_RELIEF_VAPOUR_QUALITY_MIN = 0.55
VJ_RELIEF_LIQUID_FRACTION_MAX = 1.0 - VJ_RELIEF_VAPOUR_QUALITY_MIN
VJ_RELIEF_DIAMETER_M = 0.008585
D, H, UP = Orientation.DOWN, Orientation.HORIZONTAL, Orientation.UP
DIR, VIA_RELIEF = ReleasePath.DIRECT, ReleasePath.VIA_RELIEF
VIA_VENT = ReleasePath.VIA_VENT

ASSEMBLY_COMPOSITION: dict[Assembly, list] = {
    # Sandia has no data for the 'vaporizer' or 'exchanger' primitives, so
    # the assembly is the only path that yields numbers.
    Assembly.VAPORIZER_UNIT: [
        (Primitive.PIPE, 4, H, DIR, 1.0),
        (Primitive.FLANGE, 4, H, DIR, 1.0),
        (Primitive.VALVE, 2, H, DIR, 1.0),
        (Primitive.INSTRUMENT, 2, H, DIR, 1.0),
    ],
    Assembly.LH2_PUMP: [
        (Primitive.PUMP_SEAL, 1, H, DIR, 1.0),
        (Primitive.FLANGE, 4, H, DIR, 1.0),
        (Primitive.VALVE, 2, H, DIR, 1.0),
        (Primitive.INSTRUMENT, 3, H, DIR, 1.0),
    ],
    Assembly.LOADING_ARM_UNIT: [
        (Primitive.HOSE, 1, D, DIR, 1.0),
        (Primitive.FLANGE, 4, D, DIR, 1.0),
        (Primitive.VALVE, 3, D, DIR, 1.0),
    ],
    Assembly.DISPENSER: [
        (Primitive.HOSE, 1, H, DIR, 1.0),
        (Primitive.VALVE, 2, H, DIR, 1.0),
        (Primitive.INSTRUMENT, 2, H, DIR, 1.0),
        (Primitive.JOINT, 4, H, DIR, 1.0),
    ],
    # Vacuum-jacketed line.
    #
    # An earlier version had the inner leak reaching atmosphere only if
    # the jacket then failed, at an invented probability of 0.1. That is
    # not how these fail. The jacket is required to carry its own pressure
    # relief, and in cryogenic service the vacuum plug doubles as that
    # relief. An actual loss-of-vacuum event on an LH2 transfer hose,
    # reported at IChemE Hazards 34, recorded the plug lifting near
    # 0.5 barg with a rise of 2 K and 0.7 barg in the hose, and the
    # hydrogen leaving as 80 to 100% vapour falling to 55 to 88%.
    #
    # So the release does reach atmosphere, at essentially unit
    # probability, but it is not saturated liquid and it is not a jacket
    # rupture: it is high-vapour two-phase flow through a designed relief
    # path. That source is routed to the LH2 dispersion model with the
    # recorded liquid-fraction bound rather than silently recast as liquid.
    #
    # The jacket brittle-fracture and fragment case is a different
    # sequence -- loss of vacuum, relief, local icing of the outer wall,
    # then fracture -- and is still not enumerated. EIGA TB 11/20 records
    # this mechanism on a 60,000 litre NITROGEN tank: transferable
    # cryogenic evidence, not an LH2 validation case.
    # Vent system.
    #
    # Added after a retrospective check against Sakamoto et al. (2016).
    # The Emeryville incident began with the nozzle sub-assembly of a
    # pressure relief valve failing, releasing about 30 kg of hydrogen in
    # the first minute; the release premixed with air inside the vent tube,
    # ignited with an audible "boom", and then burned as a jet flame at the
    # vent outlet. SAND2012-5170 does not establish detonation. Nothing in
    # this taxonomy could have enumerated the initial internal event.
    #
    # EIGA Doc 06/19 section 5.1.7 requires every vent, including those of
    # pressure relief devices, thermal relief valves and purge valves, to
    # be connected to a vent stack, and section 5.1.2 lists vent stacks
    # FIRST among the points a safety distance is measured from. So the
    # stack is not an optional extra: it is a designed release point that
    # the standard treats as a primary one.
    #
    # No leak frequency exists for a vent stack as such. It is decomposed
    # into the relief devices that feed it, which do have frequencies, and
    # the stack itself is carried as a no-data primitive so that its
    # absence stays visible rather than being silently covered by the
    # decomposition.
    Assembly.VENT_SYSTEM: [
        (Primitive.VALVE, 3, UP, VIA_VENT, 1.0),      # PRD, thermal, purge
        (Primitive.PIPE, 1, UP, VIA_VENT, 1.0),       # the stack itself
        (Primitive.FLANGE, 2, UP, VIA_VENT, 1.0),
    ],
    # The relief bore is not the line bore. HIAD event 58, a 42,000 litre
    # LH2 rail tanker at an Italian railway station in 1991, lost its
    # interspace vacuum to a micro-crack in the OUTER wall, rose to the
    # 13 bar relief setting against a 1 bar design pressure, and vented
    # its whole 2,500 kg inventory over seven hours at 0.10 kg/s through
    # the safety valves. Nothing ignited.
    #
    # At the same conservative Q=0.55 source state, modelling that as a
    # full-bore release of the 50 mm line gives 3.39 kg/s, about 34 times
    # the recorded rate. The older 6.1 kg/s / 61x comparison also assumed
    # saturated liquid and therefore combined two separate defects. A loss
    # of vacuum does not open a hole the size of the pipe: the relief
    # capacity sets the rate.
    #
    # The two documented sequences also start from opposite sides -- Goff
    # from an inner-line leak, HIAD 58 from an outer-wall crack -- and
    # both end at the same place, a designed vent at essentially unit
    # probability. That is now supported by two independent cases rather
    # than one.
    Assembly.VJ_LINE: [
        (Primitive.PIPE, 1, H, VIA_RELIEF, 1.0),
        (Primitive.JOINT, 2, H, VIA_RELIEF, 1.0),
        (Primitive.FLANGE, 2, H, DIR, 1.0),
    ],
}


class Site(BaseModel):
    name: str
    sections: list[Section]
    components: list[ComponentSpec] = Field(default_factory=list)
    assemblies: list[AssemblySpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _resolve(self):
        section_ids = [s.id.strip() for s in self.sections]
        if any(not sid for sid in section_ids):
            raise ValueError("section ids must not be empty")
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("section ids must be unique")
        known = {s.id for s in self.sections}
        items = list(self.components) + list(self.assemblies)
        tags = [c.tag.strip() for c in items]
        if any(not tag for tag in tags):
            raise ValueError("component and assembly tags must not be empty")
        if len(tags) != len(set(tags)):
            raise ValueError("component and assembly tags must be unique")
        for c in items:
            if c.section_id not in known:
                raise ValueError(f"unknown section_id {c.section_id!r}")
        return self

    def all_components(self) -> list[ComponentSpec]:
        out = list(self.components)
        for a in self.assemblies:
            out.extend(a.expand())
        return out


# --------------------------------------------------------------------------
# scenario enumeration
# --------------------------------------------------------------------------

# Density-ratio bounds for routing, rather than a temperature band.
#
# The jet correlation carries density explicitly in its effective
# diameter, d* = d (rho_j/rho_a)^(1/2), and Schefer reports its constant
# as independent of that ratio, giving 0.208 for hydrogen against 0.210
# for methane -- gases whose ratios differ eightfold, 0.070 against
# 0.556. Cold gaseous hydrogen at 150 K is 0.134 and sits between them.
#
# So most of what was refused as "COLD_GH2, 30 to 250 K" is interpolation
# inside a validated range. Refusing it as a block treated a covered case
# and an uncovered one identically.
JET_DENSITY_RATIO_MAX = 0.60      # end of the validated range, methane
DENSE_GAS_RATIO_MIN = 1.0         # heavier than air; SLAB's own territory


def route(service: Service,
          release_path: "ReleasePath" = None,
          density_ratio: Optional[float] = None) -> PhysicsRoute:
    """Physics route, by density ratio where one is available.

    Without a density ratio the service decides, which is the warm-gas
    and liquid case and is unchanged. With one, three regimes:

        <= 0.60   buoyant jet, inside the range the correlation was
                  validated over
        >= 1.00   denser than ambient air, which is what SLAB is for
        between   genuinely uncovered: too heavy for the jet correlation
                  to be interpolation, too light to be a dense gas
    """
    if density_ratio is not None:
        if density_ratio <= JET_DENSITY_RATIO_MAX:
            return PhysicsRoute.GH2_JET
        if density_ratio >= DENSE_GAS_RATIO_MIN:
            return PhysicsRoute.SLABX_LH2
        return PhysicsRoute.UNCOVERED
    if release_path is ReleasePath.VIA_VENT:
        # A vent stack discharges upward at height, which is what it is
        # designed to do: EIGA requires it to discharge in the open air
        # away from personnel and structures, and not where hydrogen can
        # accumulate. The release is warm gas from a designed opening, so
        # the jet model applies; what it does NOT capture is the internal
        # premixing and ignition that produced the initial loud boom at
        # Emeryville before the jet fire, and that is recorded on the
        # scenario. The investigation does not establish detonation.
        return PhysicsRoute.GH2_JET
    if release_path is ReleasePath.VIA_RELIEF:
        # Two-phase, high vapour fraction, through a designed relief.
        # slabx.core.source.HorizontalJet takes liquid_fraction, so the
        # recorded 80-100% vapour of the reference incident is a
        # parameter of a model already present rather than a gap.
        return PhysicsRoute.SLABX_LH2
    return {Service.GH2: PhysicsRoute.GH2_JET,
            Service.LH2: PhysicsRoute.SLABX_LH2}.get(
                service, PhysicsRoute.UNCOVERED)


def density_ratio_of(temperature_k: float, pressure_pa: float = 101325.0
                     ) -> Optional[float]:
    """rho_H2 / rho_air at the release state, once expanded to ambient."""
    try:
        import CoolProp.CoolProp as CP
        rho_j = CP.PropsSI("D", "P", 101325.0, "T", temperature_k,
                           "Hydrogen")
    except Exception:
        return None
    rho_a = 101325.0 * 0.0289 / (8.314 * 288.15)
    return rho_j / rho_a


class ReleaseKind(str, Enum):
    """Purple Book ch3 distinguishes continuous from instantaneous LOCs.
    Only an instantaneous one can reach the BLEVE branch of the ignition
    tree, so a catastrophic vessel failure has to be enumerated as such
    rather than as a full-bore hole."""
    CONTINUOUS = "CONTINUOUS"
    INSTANTANEOUS = "INSTANTANEOUS"


class Scenario(BaseModel):
    scenario_id: str
    tag: str
    primitive: Primitive
    service: Service
    bin_label: str
    hole_diameter_m: float
    frequency_per_year: float
    frequency_fuel_proxy: Optional[Fuel]
    release_path: ReleasePath
    available_mass_kg: float
    isolation_time_s: float
    pressure_pa: float
    temperature_k: float
    orientation: Orientation
    upstream_line: Optional[UpstreamLine] = None
    discharge_coefficient: float = Field(default=1.0, gt=0, le=1.0)
    discharge_coefficient_basis: DischargeCoefficientBasis = (
        DischargeCoefficientBasis.CONSERVATIVE_DEFAULT
    )
    discharge_coefficient_note: str = ""
    release_azimuth_deg: Optional[float] = Field(default=None, ge=0, lt=360)
    position: Position
    physics_route: PhysicsRoute
    release_kind: ReleaseKind = ReleaseKind.CONTINUOUS
    grade: Grade
    provenance: list[Provenance]

    @property
    def computable(self) -> bool:
        return (self.grade is not Grade.PLACEHOLDER
                and self.physics_route is not PhysicsRoute.UNCOVERED)

    @property
    def report_verified(self) -> bool:
        return all(p.transcription is TranscriptionSource.REPORT
                   for p in self.provenance)


def enumerate_scenarios(site: Site, bins=HYRAM_BINS) -> list[Scenario]:
    inv = {s.id: s for s in site.sections}
    out: list[Scenario] = []
    # A vessel losing containment at full bore is not a hole in a vessel,
    # it is the vessel failing. Purple Book ch3 treats catastrophic
    # rupture as an instantaneous release of the whole inventory, and the
    # ignition tree only reaches BLEVE from there. Enumerating it as a
    # continuous full-bore hole, which is what happened before this, made
    # the BLEVE branch unreachable for the largest inventory on the site.
    catastrophic = {Primitive.VESSEL}
    for i, c in enumerate(site.all_components()):
        res = resolve_frequency(c.primitive, c.service)
        sect = inv[c.section_id]
        for b in bins:
            provs = [res.provenance]
            if c.release_path is ReleasePath.VIA_VENT:
                provs.append(Provenance(
                    source="EIGA Doc 06/19 sections 5.1.2 and 5.1.7; "
                           "Sakamoto et al. (2016) incident analysis",
                    grade=Grade.ENGINEERING_JUDGEMENT,
                    transcription=TranscriptionSource.REPORT,
                    note=("Vent stack release. Decomposed into the relief "
                          "devices feeding it because no frequency exists "
                          "for a stack as such. Modelled as an elevated "
                          "upward jet, which is what the standard requires "
                          "it to be. NOT captured: premixing of hydrogen "
                          "and air INSIDE the vent tube, which at "
                          "Emeryville ignited with a loud boom before the "
                          "jet flame established. SAND2012-5170 does not "
                          "establish detonation. It is an internal premixed "
                          "combustion/explosion case and no model here "
                          "covers it."),
                    not_claimable_as=["coverage of internal vent "
                                      "premixing or detonation"]))
            if c.release_path is ReleasePath.VIA_RELIEF:
                provs.append(Provenance(
                    source="Goff et al., IChemE Hazards 34: loss of vacuum "
                           "in an LH2 transfer hose",
                    grade=Grade.ENGINEERING_JUDGEMENT,
                    transcription=TranscriptionSource.REPORT,
                    note=("Inner leak fills the vacuum space and lifts the "
                          "vacuum plug near 0.5 barg; the recorded event "
                          "gave a rise of 2 K and 0.7 barg and hydrogen at "
                          "80-100% vapour, falling to 55-88%. That is "
                          "two-phase with a high vapour fraction, which "
                          "slabx takes as liquid_fraction, so the case is "
                          "expressible in a model already present. The "
                          "value used is a single point from one recorded "
                          "incident and should be swept over 0.0 to 0.45 "
                          "rather than picked. Jacket brittle fracture "
                          "and fragment throw is a separate sequence and "
                          "is still not enumerated; EIGA TB 11/20 provides "
                          "a nitrogen-tank cryogenic analogue, not LH2 "
                          "validation.")))
            if c.upstream_line is not None:
                provs.append(Provenance(
                    source=("Darcy-Weisbach real-gas density integration; "
                            "Haaland (1983), Journal of Fluids Engineering "
                            "105(1), 89-90, DOI 10.1115/1.3240948"),
                    grade=Grade.PUBLISHED_UNVALIDATED,
                    transcription=TranscriptionSource.REPORT,
                    note=("Configured finite upstream line. Steady, "
                          "isothermal, constant-area and low-Mach closure; "
                          "line inventory, heat transfer, Fanno choking and "
                          "two-phase flow are outside its scope."),
                    not_claimable_as=["transient line blowdown validation",
                                      "two-phase vent-path validation"]))
            if (c.discharge_coefficient_basis
                    is not DischargeCoefficientBasis.CONSERVATIVE_DEFAULT):
                coefficient_grades = {
                    DischargeCoefficientBasis.MEASURED: Grade.MEASURED,
                    DischargeCoefficientBasis.MANUFACTURER_CERTIFIED:
                        Grade.PUBLISHED_UNVALIDATED,
                    DischargeCoefficientBasis.ENGINEERING_ASSUMPTION:
                        Grade.ENGINEERING_JUDGEMENT,
                    DischargeCoefficientBasis.CALIBRATED:
                        Grade.ENGINEERING_JUDGEMENT,
                }
                not_claimable = []
                if (c.discharge_coefficient_basis
                        is DischargeCoefficientBasis.CALIBRATED):
                    not_claimable = [
                        "independent validation on the calibration dataset"
                    ]
                elif (c.discharge_coefficient_basis
                      is DischargeCoefficientBasis.ENGINEERING_ASSUMPTION):
                    not_claimable = [
                        "measured equipment discharge coefficient"
                    ]
                provs.append(Provenance(
                    source=c.discharge_coefficient_note,
                    grade=coefficient_grades[
                        c.discharge_coefficient_basis],
                    transcription=TranscriptionSource.UNVERIFIED,
                    note=(f"Equipment-specific Cd="
                          f"{c.discharge_coefficient:g}; basis="
                          f"{c.discharge_coefficient_basis.value}."),
                    not_claimable_as=not_claimable))
            kind = (ReleaseKind.INSTANTANEOUS
                    if (c.primitive in catastrophic and b.label == "100%")
                    else ReleaseKind.CONTINUOUS)
            out.append(Scenario(
                release_kind=kind,
                scenario_id=f"S{i:03d}-{b.label}", tag=c.tag or c.primitive.value,
                primitive=c.primitive, service=c.service, bin_label=b.label,
                hole_diameter_m=b.hole_diameter(
                    c.relief_diameter_m or c.nominal_diameter_m),
                frequency_per_year=(res.values[b.label] * c.count
                                    * c.secondary_breach_probability),
                frequency_fuel_proxy=res.fuel_used,
                release_path=c.release_path,
                available_mass_kg=sect.inventory_kg,
                isolation_time_s=sect.isolation_time_s,
                pressure_pa=c.pressure_pa,
                temperature_k=c.temperature_k,
                orientation=c.orientation,
                upstream_line=c.upstream_line,
                discharge_coefficient=c.discharge_coefficient,
                discharge_coefficient_basis=c.discharge_coefficient_basis,
                discharge_coefficient_note=c.discharge_coefficient_note,
                release_azimuth_deg=c.release_azimuth_deg,
                position=c.position,
                physics_route=route(
                    c.service, c.release_path,
                    density_ratio_of(c.temperature_k)
                    if c.service is Service.COLD_GH2 else None),
                grade=Provenance.weakest(provs), provenance=provs))
    return out
