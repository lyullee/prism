"""Experimental comparisons and their independence limits mapped to GH2 models.

The matrix deliberately separates three things that are often collapsed:
an identified dataset, a numerical benchmark, and validation of this code.
Most source plots still need machine-readable values before residuals can be
calculated. Until then they are coverage evidence, not validation scores.
"""

from __future__ import annotations

from dataclasses import dataclass


SANDIA_REPORT = (
    "SAND2024-14886, HyRAM+ Version 5.1 Technical Reference and Validation "
    "of Physics Models (2024)"
)


@dataclass(frozen=True)
class Evidence:
    phenomenon: str
    source: str
    conditions: str
    quantity: str
    finding: str
    status: str
    next_action: str


EVIDENCE: tuple[Evidence, ...] = (
    Evidence(
        "GH2 centerline dispersion", "Molkov (2012) compilation",
        "d=0.16-100 mm; P about 0.257-40 MPa; T=35-298 K",
        "centerline H2 mass fraction",
        "HyRAM+ generally agrees; some Ruffin and Kuznetsov points are "
        "slightly underpredicted",
        "DATASET_IDENTIFIED",
        "transcribe the original point data and calculate residuals for "
        "Schefer equation 9"),
    Evidence(
        "GH2 radial dispersion", "Houf and Schefer (2008)",
        "d=1.905 mm; ambient pressure and 294 K; vertical slow leaks",
        "radial mass-fraction profiles and centerline decay",
        "centerline decay is good downstream, but radial profiles disagree",
        "KNOWN_MODEL_LIMIT",
        "compare equation 11 half-width and LFL width point by point"),
    Evidence(
        "GH2 radial dispersion", "Ruggles and Ekoto (2012)",
        "d=1.5 mm; P0=0.9832 MPa; T0=295.4 K; pressure ratio 10:1",
        "inverse centerline mass fraction and jet half-width",
        "virtual-origin slope comparison: half-width NMB -2.4%, nRMSE 3.5%; "
        "inverse centerline mass fraction NMB +33.7%, nRMSE 34.0%; "
        "operating-profile coordinate mapping is unresolved",
        "NUMERIC_BENCHMARK_MIXED",
        "obtain original machine-readable data and test a pressure-dependent "
        "centerline applicability boundary"),
    Evidence(
        "GH2 LFL distance", "Han et al. (2013)",
        "d=0.5, 0.7, 1.0 mm; P=100-400 bar; distances 1-9 m",
        "centerline mole fraction and distance to LFL, LFL/2, LFL/4",
        "current full chain at LFL: NMB +10.2%, nRMSE 11.3%, FAC2 1.0; "
        "the original 30 mm hole length is outside the sharp-hole premise",
        "NUMERIC_BENCHMARK_PASS",
        "obtain original flow data to separate long-hole source error from "
        "dispersion error"),
    Evidence(
        "jet flame length and heat flux", "Ekoto et al. (2014)",
        "horizontal; 60 barg; d=20.9 and 52.5 mm",
        "visible flame length and one radiometer heat flux per test",
        "current measured-flow flame scores: Delichatsios nRMSE 5.6%, "
        "Molkov fit 20.5%, both pass; Cd=1 source nRMSE 20.0%; "
        "radiometer heat flux is not yet scored; Molkov eq.8 results are "
        "two extrapolation checks beyond its 0.4-10.1 mm development range",
        "NUMERIC_BENCHMARK_PASS_COMPONENT",
        "digitize detector geometry and measured heat flux; keep source, "
        "flame length and radiation scores separate"),
    Evidence(
        "medium-diameter jet flame", "Royle & Willoughby (2009)",
        "horizontal free jet; nominal 205 bar; d=1.5, 3.2, 6.4, 9.5 mm",
        "unattached/attached flame length and ignition-delay overpressure",
        "current 288 K Delichatsios sensitivities: Cd=1 nRMSE 45.1%; "
        "Cd=0.61 nRMSE 18.2%; release T and flow are missing and restrictor "
        "length conflicts between 12 and 20 mm",
        "NUMERIC_SENSITIVITY_MIXED",
        "obtain raw pressure, temperature, mass flow and final restrictor "
        "drawing; do not treat the passing Cd sensitivity as validation"),
    Evidence(
        "jet flame blowdown", "Schefer et al. (2006); Houf and Schefer (2007)",
        "d=3.175 mm; initial P=15.5 MPaa; vertical blowdown",
        "flame length and axial/radial heat flux over time",
        "flame decay is captured; peak heat-flux bias changes with time",
        "DATASET_IDENTIFIED",
        "couple the transient discharge profile before scoring residuals"),
    Evidence(
        "small jet flame", "Imamura et al. (2008)",
        "d=1-4 mm; spouting P=0.5-3.0 MPa",
        "mass flow and flame length",
        "HyRAM+ flame lengths are slightly long, especially at larger d",
        "DATASET_IDENTIFIED",
        "digitize Figure 3-13 and score source-term and flame errors separately"),
    Evidence(
        "high-pressure jet flame", "Mogi et al. (2005)",
        "d=0.4-5 mm; P=0.01-40 MPa",
        "flame length, width, and radiant heat flux",
        "trend is captured; some low-flow heat fluxes are overpredicted",
        "DATASET_IDENTIFIED",
        "digitize flame-length and detector-location heat-flux data"),
    Evidence(
        "very-high-pressure jet flame", "Proust et al. (2011)",
        "horizontal; d=1-3 mm; blowdown to 900 bar",
        "flame length versus pressure and heat flux versus time",
        "with digitized measured flow, Delichatsios nRMSE 10.5%, Molkov fit "
        "16.3%, conservative Molkov 31.2%; three-model envelope coverage 100%; "
        "Cd=1 source flow still fails after the reported 10 m pipe is included "
        "(NMB +76.4%, nRMSE 94.1%); fixed Cd=0.61 sensitivity passes "
        "(NMB +9.9%, nRMSE 20.0%) but is not apparatus validation; "
        "Proust/INERIS families were used to develop Molkov eq.8, so "
        "the Molkov comparison is not independent validation",
        "NUMERIC_BENCHMARK_MIXED",
        "obtain original pressure/temperature/tank-mass time series, the "
        "differentiation method and unreported nozzle/restriction geometry; "
        "seek matched 6-25 mm tests rather "
        "than extrapolating this 3 mm result"),
)


DESIGN_CASES: tuple[tuple[float, float], ...] = (
    (3.0, 100.0), (6.0, 350.0), (12.0, 450.0), (25.0, 700.0))


def dispersion_joint_coverage(d_mm: float, p_bar: float) -> str:
    """Coverage by data that explicitly reports LFL distance."""
    if 0.5 <= d_mm <= 1.0 and 100.0 <= p_bar <= 400.0:
        return "JOINT_LFL_RANGE"
    if 100.0 <= p_bar <= 400.0:
        return "PRESSURE_ONLY"
    return "OUTSIDE_LFL_RANGE"


def flame_joint_coverage(d_mm: float, p_bar: float) -> str:
    """Joint diameter/pressure overlap in the listed flame experiments."""
    if 1.0 <= d_mm <= 3.0 and p_bar <= 900.0:
        return "PROUST_JOINT_RANGE"
    if 20.9 <= d_mm <= 52.5 and abs(p_bar - 60.0) <= 1.0:
        return "EKOTO_JOINT_RANGE"
    if 1.5 <= d_mm <= 9.5 and abs(p_bar - 205.0) <= 5.0:
        return "ROYLE_JOINT_RANGE_SOURCE_INCOMPLETE"
    if 0.4 <= d_mm <= 5.0 and p_bar <= 400.0:
        return "MOGI_JOINT_RANGE"
    if 6.0 <= d_mm <= 9.5:
        return "ROYLE_DIAMETER_ONLY_PRESSURE_OUTSIDE"
    if 20.9 <= d_mm <= 52.5:
        return "EKOTO_DIAMETER_ONLY_PRESSURE_OUTSIDE"
    return "AXES_ONLY_NO_JOINT_POINT"


def ekoto_hyram_ratios() -> dict[str, float]:
    """Published HyRAM+/measurement ratios from Sandia Table 3-4."""
    return {
        "20p9mm_length": 19.9 / 17.4,
        "20p9mm_heat_flux": 6.3 / 4.7,
        "52p5mm_length": 47.7 / 45.9,
        "52p5mm_heat_flux": 27.2 / 23.9,
    }
