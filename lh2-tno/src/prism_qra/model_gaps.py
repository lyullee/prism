"""Phenomena that the current QRA must refuse rather than approximate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeclaredModelGap:
    gap_id: str
    phenomenon: str
    status: str
    current_allowed_output: str
    prohibited_claims: tuple[str, ...]
    reason: str
    required_inputs: tuple[str, ...]
    minimum_closure_evidence: tuple[str, ...]
    primary_basis: str


VENT_INTERNAL_PREMIXING = DeclaredModelGap(
    gap_id="VENT_INTERNAL_PREMIXING",
    phenomenon="premixed ignition or explosion inside a hydrogen vent line",
    status="REFUSED_UNTIL_MODEL_AND_VALIDATION_DATA",
    current_allowed_output=(
        "external upward jet dispersion and jet-fire consequence from the "
        "vent outlet only"
    ),
    prohibited_claims=(
        "vent-line ignition probability",
        "deflagration or detonation pressure inside the vent",
        "deflagration-to-detonation transition prediction",
        "vent structural adequacy under an internal explosion",
    ),
    reason=(
        "The current source, dispersion and fire models begin at the vent "
        "outlet and contain no oxygen ingress, premixing, ignition location "
        "or reactive compressible pipe-flow physics.  SAND2012-5170 confirms "
        "premixing and ignition with a loud boom at Emeryville, but does not "
        "establish detonation or provide a validation dataset."
    ),
    required_inputs=(
        "vent internal diameter, length, diameter changes, bends and branches",
        "inlet and outlet boundary conditions and relief flow versus time",
        "roughness, obstacles, valves, flame arresters and open/closed states",
        "initial hydrogen, oxygen and inert-gas composition along the line",
        "purge procedure, air-ingress paths and purge failure state",
        "ignition time, location and credible ignition-energy range",
        "vent material, wall thickness, supports, design pressure and relief",
    ),
    minimum_closure_evidence=(
        "a declared 1-D reactive or 3-D compressible combustion model",
        "mesh/time-step and reaction-mechanism convergence evidence",
        "independent hydrogen vent-line pressure/flame-speed tests spanning "
        "the facility L/D, obstacles, mixture and initial pressure",
        "blind commissioning or dedicated rig comparison of pressure-time "
        "and flame-arrival histories",
    ),
    primary_basis=(
        "Harris et al. (2012), SAND2012-5170, Investigation of the Hydrogen "
        "Release Incident at the AC Transit Emeryville Facility"
    ),
)


JACKET_BRITTLE_FRACTURE = DeclaredModelGap(
    gap_id="JACKET_BRITTLE_FRACTURE",
    phenomenon=(
        "outer-jacket brittle fracture and fragment ejection after an inner "
        "cryogenic leak into a vacuum annulus"
    ),
    status="REFUSED_UNTIL_MODEL_AND_VALIDATION_DATA",
    current_allowed_output=(
        "designed vacuum-relief discharge; a conditional fragment range may "
        "be calculated only when released mechanical energy is supplied, "
        "without assigning sequence frequency"
    ),
    prohibited_claims=(
        "frequency of outer-jacket brittle fracture",
        "time from inner leak to jacket failure",
        "fragment mass, direction or lethality from an LH2 jacket failure",
        "validation of the sequence using hydrogen incident data",
    ),
    reason=(
        "The pipeline has relief and generic fragment calculations but no "
        "annulus heat transfer, local cryogenic impingement, fracture "
        "mechanics or sequence frequency.  EIGA TB 11/20 documents a "
        "60,000 litre nitrogen-tank outer-jacket brittle fracture.  It is "
        "transferable cryogenic mechanism evidence, not LH2 validation."
    ),
    required_inputs=(
        "inner-pipe geometry, welds, supports, thermal cycles and inspection",
        "vacuum-annulus geometry, insulation, vacuum and relief capacity",
        "credible inner leak location, size, phase and time-dependent rate",
        "cryogenic impingement area and conjugate heat-transfer boundary",
        "outer-jacket material certificate, thickness, weld map and residual stress",
        "temperature-dependent Charpy/fracture-toughness and crack data",
        "nearby targets needed for fragment hit and escalation assessment",
    ),
    minimum_closure_evidence=(
        "transient annulus pressure and jacket-temperature model",
        "fracture-mechanics limit state tied to certified material data",
        "validated fragment generation/trajectory model or a justified bound",
        "cryogenic test or incident reconstruction independent of calibration",
        "a sourced initiating frequency or an explicitly conditional analysis",
    ),
    primary_basis=(
        "EIGA TB 11/20 (2020), Loss of Vacuum on Vacuum Insulated Cryogenic "
        "Storage Tanks Due to Inner Vessel or Internal Piping Leak"
    ),
)


DECLARED_GAPS = (VENT_INTERNAL_PREMIXING, JACKET_BRITTLE_FRACTURE)


def by_id(gap_id: str) -> DeclaredModelGap:
    for gap in DECLARED_GAPS:
        if gap.gap_id == gap_id:
            return gap
    raise KeyError(gap_id)
