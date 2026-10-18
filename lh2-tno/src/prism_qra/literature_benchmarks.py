"""Numerical literature benchmarks for the implemented GH2 models.

The observations below are graph digitizations, not calibration constants.
Pixel-to-axis transforms and the retained marker coordinates are kept here so
that every value can be reconstructed.  The three sources exercise different
parts of the chain:

* Ruggles--Ekoto: centreline decay and radial half-width at one steady jet;
* Han et al.: LFL centreline distance for 12 diameter-pressure combinations;
* Proust et al.: measured mass flow and visible flame length during a 3 mm
  high-pressure blowdown;
* Royle--Willoughby: unattached flame lengths at 1.5--9.5 mm and 205 bar;
* Ekoto et al.: measured-flow flame lengths at 20.9 and 52.5 mm near 60 barg.

Sandia's 2024 validation report supplies the plotted Ruggles--Ekoto and Han
points.  Proust's open ICHS 2009 paper supplies the original flame and flow
plots.  No value in this module was fitted to this implementation.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from functools import lru_cache
from typing import Iterable

import CoolProp.CoolProp as CP
import numpy as np

from fire import flame_length, molkov_flame_length, notional_nozzle
from gh2_jet import (
    C1_MASS,
    C2_HALF_RADIUS,
    LFL_MASS_FRACTION,
    centreline_distance_to_mass,
    effective_diameter,
)
from source_term import (P_AMB, discharge, haaland_friction_factor,
                         line_discharge)
from validation_metrics import Observation, metrics


SANDIA_SOURCE = (
    "Devin, Ehrhart & Hecht (2024), SAND2024-14886, Figures 3-8 and 3-9"
)
PROUST_SOURCE = (
    "Proust, Jamois & Studer (2009), High pressure hydrogen fires, "
    "ICHS 2009, Figures 5 and 8; journal version DOI "
    "10.1016/j.ijhydene.2010.04.055"
)
VENETSANOS_SOURCE = (
    "Venetsanos et al. (2021), Cryogenic and Ambient Gaseous Hydrogen "
    "Blowdown with Discharge Line Effects, ICHS 2021 paper 178"
)
ROYLE_SOURCE = (
    "Royle & Willoughby (2009), Releases of unignited hydrogen into the "
    "atmosphere, ICHS 2009 paper 200, Tables 1--4; journal version DOI "
    "10.1016/j.ijhydene.2010.03.141"
)
EKOTO_SOURCE = (
    "Ekoto et al. (2014), Updated jet flame radiation modeling with "
    "buoyancy corrections, DOI 10.1016/j.ijhydene.2014.03.235, Table 1; "
    "cross-checked against SAND2024-14886 Tables 3-4 and A-14"
)
PROUST_CD_SENSITIVITY = 0.61

# The project screening criteria were declared before these values were
# scored.  They are research-team rules, not regulatory acceptance limits.
SCREENING = {
    "absolute_normalized_mean_bias_max": 0.20,
    "normalized_rmse_max": 0.30,
    "fraction_within_factor_two_min": 0.90,
}


def _linear_axis(pixel: float, anchors: Iterable[tuple[float, float]]) -> float:
    pairs = tuple(anchors)
    x_mean = sum(x for x, _ in pairs) / len(pairs)
    y_mean = sum(y for _, y in pairs) / len(pairs)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in pairs) / sum(
        (x - x_mean) ** 2 for x, _ in pairs
    )
    return y_mean + slope * (pixel - x_mean)


def _interpolate(x: float, table: tuple[tuple[float, float], ...]) -> float:
    ordered = tuple(sorted(table))
    if not ordered[0][0] <= x <= ordered[-1][0]:
        raise ValueError(f"{x:g} is outside interpolation range")
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if x <= x1:
            fraction = (x - x0) / (x1 - x0)
            return y0 + fraction * (y1 - y0)
    return ordered[-1][1]


def _throat_density(result) -> float:
    return result.mass_flux_kg_m2s / result.velocity_m_s


# Figure 3-9b LFL-circle values.  The graph-reading resolution is about
# 0.05 m.  It is not entered as measurement_std because the paper did not
# report it as physical measurement uncertainty.
HAN_LFL_M: dict[float, tuple[float, ...]] = {
    0.5: (1.14, 1.64, 2.08, 2.35),
    0.7: (1.65, 2.36, 2.82, 3.25),
    1.0: (2.29, 3.13, 3.93, 4.55),
}
HAN_PRESSURES_BAR = (100.0, 200.0, 300.0, 400.0)


# Circle centres digitized from SAND2024-14886 Figure 3-8 at a 5x render.
# Axes: normalized axial distance z/r; inverse centreline mass fraction;
# half-width in mm.  The first and last markers are retained, rather than
# fitting a line to the plot, so residual scatter remains visible.
RUGGLES_INVERSE_PIXELS = (
    (1318, 1097), (1336, 1087), (1354, 1078), (1376, 1063),
    (1396, 1050), (1417, 1040), (1436, 1030), (1460, 1016),
    (1477, 1004), (1501, 996), (1520, 984), (1541, 968),
    (1561, 958), (1581, 948), (1601, 934), (1623, 919),
    (1643, 901), (1661, 882), (1682, 880), (1703, 871),
    (1723, 853), (1743, 849), (1762, 837), (1780, 814),
    (1804, 806), (1825, 793), (1843, 776), (1863, 760),
    (1885, 747), (1904, 742), (1925, 728), (1944, 720),
)
RUGGLES_HALF_WIDTH_PIXELS = (
    (1297, 1665), (1315, 1650), (1334, 1639), (1356, 1635),
    (1377, 1619), (1397, 1608), (1417, 1593), (1437, 1594),
    (1458, 1583), (1479, 1564), (1499, 1553), (1520, 1547),
    (1539, 1532), (1560, 1523), (1582, 1512), (1601, 1505),
    (1622, 1489), (1640, 1465), (1661, 1449), (1684, 1454),
    (1703, 1453), (1725, 1412), (1742, 1410), (1765, 1408),
    (1786, 1376), (1805, 1381), (1825, 1371), (1845, 1360),
    (1867, 1345), (1886, 1329), (1907, 1334), (1928, 1316),
    (1946, 1318),
)
RUGGLES_X_AXIS = ((1257.0, 100.0), (1568.0, 200.0),
                  (1875.5, 300.0))
RUGGLES_INVERSE_AXIS = (
    (633.0, 60.0), (739.5, 50.0), (844.0, 40.0),
    (951.0, 30.0), (1056.0, 20.0), (1163.0, 10.0),
)
RUGGLES_HALF_WIDTH_AXIS = (
    (1214.0, 30.0), (1321.0, 25.0), (1425.0, 20.0),
    (1533.0, 15.0), (1636.0, 10.0), (1744.0, 5.0),
)


# Proust Figure 5, 3 mm green curve.  Axis-line calibration at the same 5x
# render was x=(663,2579) for 0--1000 bar and y=(3065,1927) for 0--180 g/s.
# Values are curve-centre readings at the Table 1 pressures.
PROUST_MASS_FLOW_G_S = (
    (100.0, 26.968), (125.0, 34.798), (150.0, 44.446),
    (175.0, 52.039), (200.0, 59.315), (250.0, 72.759),
    (300.0, 84.306), (400.0, 103.445), (500.0, 118.629),
    (600.0, 130.018), (700.0, 141.722), (800.0, 152.953),
    (900.0, 165.132),
)

# Proust Table 1, 3 mm measured temperature.  Figure 4 calls the temperature
# the value just upstream of the orifice, while the surrounding Table 1 text
# calls it a reservoir value; that location ambiguity is retained.  The minus
# signs in the PDF text layer follow the number, so the values were checked
# against the rendered table.
PROUST_TEMPERATURE_C = (
    (20.0, -76.0), (30.0, -78.0), (40.0, -80.0), (60.0, -77.0),
    (80.0, -70.0), (100.0, -61.0), (125.0, -47.0), (150.0, -30.0),
    (175.0, -20.0), (200.0, -11.0), (250.0, -4.0), (300.0, 15.0),
    (400.0, 28.0), (500.0, 35.0), (600.0, 39.0), (700.0, 42.0),
    (800.0, 44.0), (900.0, 46.0),
)

# Individual orange-circle centres retained from Proust Figure 8.  Connected
# marker clusters were excluded by a predeclared 65--100 pixel component-size
# rule; hence the scored range begins at 137.6 bar.  Rows are (bar, m).
PROUST_FLAME_3MM = (
    (137.6, 3.961), (138.7, 4.055), (153.7, 4.081), (166.3, 4.296),
    (170.0, 4.001), (172.8, 4.431), (184.2, 4.587), (195.7, 4.069),
    (200.6, 4.268), (204.2, 4.510), (207.1, 4.361), (209.1, 4.735),
    (214.0, 4.458), (218.7, 4.537), (224.3, 4.788), (229.0, 5.228),
    (247.2, 4.787), (265.3, 4.936), (273.0, 5.472), (279.6, 4.828),
    (287.5, 4.976), (292.0, 4.843), (300.7, 4.828), (308.1, 4.844),
    (316.8, 4.844), (326.5, 5.455), (340.6, 5.563), (351.3, 5.445),
    (351.3, 5.255), (357.0, 5.616), (368.4, 5.618), (373.1, 5.164),
    (378.9, 5.618), (391.2, 5.471), (397.8, 4.844), (404.6, 5.245),
    (411.2, 4.830), (424.6, 5.229), (432.2, 5.456), (439.7, 5.603),
    (462.6, 4.843), (470.2, 4.844), (478.9, 5.230), (497.1, 5.136),
    (505.9, 5.005), (515.0, 5.578), (535.0, 5.592), (544.9, 5.871),
    (556.7, 5.284), (567.4, 5.256), (590.4, 5.752), (601.9, 5.616),
    (614.3, 5.872), (640.1, 6.098), (654.4, 5.897), (666.6, 5.926),
    (682.1, 5.963), (711.3, 6.485), (726.8, 6.273), (742.9, 6.043),
    (759.0, 6.152), (759.1, 6.872), (775.3, 7.073), (792.4, 7.232),
)

# Royle Table 4.  These are the unattached flames, not the longer flames
# attached to the ground or wall.  All tests were nominally 205 bar with an
# 800 ms ignition delay.  The paper says the restrictor insert was 12 mm long
# in section 2.3 but labels it 20 mm long in Figure 2; it also omits release
# temperature and measured mass flow.  Consequently these rows are explicit
# 288.15 K source-term sensitivities, not full-chain validation observations.
ROYLE_UNATTACHED_FLAME_M = (
    (1.5, 3.0),
    (3.2, 6.0),
    (6.4, 9.0),
    (9.5, 11.0),
)
ROYLE_PRESSURE_BAR = 205.0
ROYLE_ASSUMED_TEMPERATURE_K = 288.15


# Ekoto Table 1 conditions.  Pressure is reported as gauge pressure, so the
# measured ambient pressure is added before calling the absolute-pressure
# source model.  Measured mass flow is used to isolate flame-model error;
# Cd=1 source predictions are retained as their own QOI.
EKOTO_LARGE_FLAMES = (
    {
        "label": "20p9",
        "diameter_mm": 20.9,
        "mass_flow_kg_s": 1.0,
        "pressure_barg": 59.8,
        "temperature_k": 308.7,
        "ambient_pressure_bar": 1.022,
        "visible_flame_length_m": 17.4,
    },
    {
        "label": "52p5",
        "diameter_mm": 52.5,
        "mass_flow_kg_s": 7.4,
        "pressure_barg": 62.1,
        "temperature_k": 287.8,
        "ambient_pressure_bar": 1.011,
        "visible_flame_length_m": 45.9,
    },
)


def _han_observations() -> list[Observation]:
    observations = []
    for diameter_mm, measured_values in HAN_LFL_M.items():
        diameter_m = diameter_mm / 1000.0
        for pressure_bar, measured in zip(HAN_PRESSURES_BAR, measured_values):
            result = discharge(
                pressure_bar * 1e5, 293.0, "Hydrogen", diameter_m
            )
            nozzle = notional_nozzle(
                result.rate_kg_s,
                result.throat_pressure_pa,
                result.velocity_m_s,
                _throat_density(result),
                diameter_m,
            )
            predicted = centreline_distance_to_mass(
                LFL_MASS_FRACTION, nozzle
            )
            observations.append(Observation(
                test_id=f"HAN-d{diameter_mm:g}-p{pressure_bar:g}",
                qoi="han_lfl_distance_m",
                measured=measured,
                predicted=predicted,
                unit="m",
                source=SANDIA_SOURCE,
                condition_note=(
                    f"d={diameter_mm:g} mm; P0={pressure_bar:g} bara; "
                    "T0=293 K; graph-reading resolution about 0.05 m; "
                    "original test hole length 30 mm, while the source-term "
                    "model assumes a sharp hole"
                ),
            ))
    return observations


def _ruggles_observations() -> list[Observation]:
    result = discharge(983_200.0, 295.4, "Hydrogen", 0.0015, Cd=0.979)
    nozzle = notional_nozzle(
        result.rate_kg_s,
        result.throat_pressure_pa,
        result.velocity_m_s,
        _throat_density(result),
        0.0015,
    )
    d_effective = effective_diameter(nozzle)
    observations = []
    common_note = (
        "d=1.5 mm; P0=0.9832 MPa; T0=295.4 K; Cd=0.979; "
        "Pamb=98.37 kPa in the experiment versus 101.325 kPa in this model; "
        "z is measured from the plotted virtual origin"
    )
    for index, (x_pixel, y_pixel) in enumerate(RUGGLES_INVERSE_PIXELS):
        normalized_z = _linear_axis(x_pixel, RUGGLES_X_AXIS)
        measured = _linear_axis(y_pixel, RUGGLES_INVERSE_AXIS)
        z_m = normalized_z * 0.00075
        predicted = float(C1_MASS) * z_m / d_effective
        observations.append(Observation(
            test_id=f"RUG-INV-{index + 1:02d}",
            qoi="ruggles_inverse_centerline_mass_fraction",
            measured=measured,
            predicted=predicted,
            unit="1",
            source=SANDIA_SOURCE,
            condition_note=f"{common_note}; z/r={normalized_z:.3f}",
        ))
    for index, (x_pixel, y_pixel) in enumerate(RUGGLES_HALF_WIDTH_PIXELS):
        normalized_z = _linear_axis(x_pixel, RUGGLES_X_AXIS)
        measured = _linear_axis(y_pixel, RUGGLES_HALF_WIDTH_AXIS)
        predicted = float(C2_HALF_RADIUS) * normalized_z * 0.75
        observations.append(Observation(
            test_id=f"RUG-HW-{index + 1:02d}",
            qoi="ruggles_half_width_mm",
            measured=measured,
            predicted=predicted,
            unit="mm",
            source=SANDIA_SOURCE,
            condition_note=f"{common_note}; z/r={normalized_z:.3f}",
        ))
    return observations


def _required_equivalent_minor_loss_k(
        pressure_pa: float, temperature_k: float, target_rate_kg_s: float
        ) -> tuple[float, float]:
    """Equivalent extra K needed if the reported 10 mm line and Cd=1 stand.

    This is an inverse diagnostic, not an apparatus reconstruction.  The
    terminal pressure is first found from the current Cd=1 source.  The same
    isothermal real-gas energy balance used by ``line_discharge`` then gives
    the total loss coefficient, from which the smooth-pipe Darcy term is
    removed.  A very large result means ordinary unreported fittings are an
    implausible sole explanation; it does not identify the actual nozzle.
    """
    outlet = max(P_AMB * 1.001, 0.5 * pressure_pa)
    for _ in range(7):
        rate = discharge(
            outlet, temperature_k, "Hydrogen", 0.003, n_scan=120
        ).rate_kg_s
        outlet = min(
            max(outlet * target_rate_kg_s / rate, P_AMB * 1.001),
            pressure_pa,
        )
    pressures = np.linspace(outlet, pressure_pa, 160)
    densities = np.asarray([
        CP.PropsSI("D", "P", float(p), "T", temperature_k, "Hydrogen")
        for p in pressures
    ])
    density_integral = float(np.trapezoid(densities, pressures))
    line_diameter_m = 0.010
    line_area_m2 = math.pi * line_diameter_m ** 2 / 4.0
    viscosity = CP.PropsSI(
        "V", "P", math.sqrt(pressure_pa * outlet), "T", temperature_k,
        "Hydrogen",
    )
    reynolds = (
        4.0 * target_rate_kg_s / (math.pi * line_diameter_m * viscosity)
    )
    darcy = haaland_friction_factor(reynolds)
    total_k = (
        2.0 * line_area_m2 ** 2 * density_integral / target_rate_kg_s ** 2
    )
    equivalent_minor_k = total_k - darcy * 10.0 / line_diameter_m
    return outlet, equivalent_minor_k


@lru_cache(maxsize=1)
def _proust_source_data() -> tuple[tuple[Observation, ...], tuple[dict, ...]]:
    observations = []
    diagnostics = []
    for pressure_bar, measured_g_s in PROUST_MASS_FLOW_G_S:
        temperature_c = _interpolate(pressure_bar, PROUST_TEMPERATURE_C)
        predicted_g_s = 1000.0 * discharge(
            pressure_bar * 1e5,
            temperature_c + 273.15,
            "Hydrogen",
            0.003,
        ).rate_kg_s
        common = dict(
            test_id=f"PROUST-FLOW-p{pressure_bar:g}",
            measured=measured_g_s,
            unit="g/s",
            source=PROUST_SOURCE,
        )
        observations.append(Observation(
            **common,
            qoi="proust_mass_flow_g_s",
            predicted=predicted_g_s,
            condition_note=(
                f"d=3 mm; P={pressure_bar:g} bar; Table 1 measured "
                f"temperature={temperature_c:g} degC (reservoir/upstream "
                "location wording is ambiguous); 25 L vessel and "
                "10 m, 10 mm-ID feed pipe; sharp-hole source excludes pipe "
                "loss; graph-reading "
                "resolution about 1 g/s"
            ),
        ))
        line_predicted_g_s = 1000.0 * line_discharge(
            pressure_bar * 1e5,
            temperature_c + 273.15,
            "Hydrogen",
            0.003,
            line_length_m=10.0,
            line_diameter_m=0.010,
            # Proust does not report roughness or fitting K.  Zero/zero is
            # retained as the auditable hydraulically-smooth upper-flow case,
            # not fitted to the observations.
            roughness_m=0.0,
            minor_loss_k=0.0,
            n_scan=120,
            n_integral=160,
        ).rate_kg_s
        observations.append(Observation(
            **common,
            qoi="proust_mass_flow_line_loss_g_s",
            predicted=line_predicted_g_s,
            condition_note=(
                f"d=3 mm; P={pressure_bar:g} bar; Table 1 measured "
                f"temperature={temperature_c:g} degC; 10 m, 10 mm-ID "
                "constant-area isothermal real-gas line; hydraulically "
                "smooth and K=0 because the paper does not report "
                "roughness/fittings; no calibration; graph-reading "
                "resolution about 1 g/s"
            ),
        ))
        observations.append(Observation(
            **common,
            qoi="proust_mass_flow_cd061_sensitivity_g_s",
            predicted=PROUST_CD_SENSITIVITY * predicted_g_s,
            condition_note=(
                f"d=3 mm; P={pressure_bar:g} bar; Table 1 measured "
                f"temperature={temperature_c:g} degC; fixed Cd=0.61 "
                "declared sensitivity, not fitted to these points and not "
                "a confirmed property of the unreported nozzle geometry; "
                "graph-reading resolution about 1 g/s"
            ),
        ))
        outlet_pa, required_minor_k = _required_equivalent_minor_loss_k(
            pressure_bar * 1e5,
            temperature_c + 273.15,
            measured_g_s / 1000.0,
        )
        effective_cd_direct = measured_g_s / predicted_g_s
        diagnostics.append({
            "pressure_bar": pressure_bar,
            "temperature_c": temperature_c,
            "measured_g_s": measured_g_s,
            "direct_cd1_g_s": predicted_g_s,
            "reported_line_cd1_g_s": line_predicted_g_s,
            "fixed_cd061_g_s": PROUST_CD_SENSITIVITY * predicted_g_s,
            "effective_cd_direct": effective_cd_direct,
            "effective_cd_reported_line": measured_g_s / line_predicted_g_s,
            "equivalent_orifice_diameter_mm": (
                3.0 * math.sqrt(effective_cd_direct)
            ),
            "required_line_outlet_pressure_bar": outlet_pa / 1e5,
            "required_equivalent_minor_loss_k": required_minor_k,
        })
    return tuple(observations), tuple(diagnostics)


def _proust_mass_flow_observations() -> list[Observation]:
    return list(_proust_source_data()[0])


def proust_source_residual_diagnostics() -> list[dict]:
    """Pressure-resolved Proust source residual audit rows."""
    return [dict(row) for row in _proust_source_data()[1]]


def proust_source_residual_summary() -> dict:
    """Aggregates that keep sensitivity, calibration and validation apart."""
    rows = proust_source_residual_diagnostics()
    measured = np.asarray([row["measured_g_s"] for row in rows])
    direct = np.asarray([row["direct_cd1_g_s"] for row in rows])
    with_line = np.asarray([row["reported_line_cd1_g_s"] for row in rows])
    fitted_cd = float(np.dot(measured, direct) / np.dot(direct, direct))
    fitted_rows = [Observation(
        test_id=f"PROUST-FITTED-p{row['pressure_bar']:g}",
        qoi="proust_mass_flow_fitted_cd_diagnostic_g_s",
        measured=row["measured_g_s"],
        predicted=fitted_cd * row["direct_cd1_g_s"],
        unit="g/s",
        source=PROUST_SOURCE,
        condition_note="same-series least-squares fit; calibration diagnostic",
    ) for row in rows]
    fitted_metrics = asdict(metrics(fitted_rows))
    return {
        "fitted_constant_cd_same_series": fitted_cd,
        "fitted_constant_cd_metrics": fitted_metrics,
        "effective_cd_direct_min": min(
            row["effective_cd_direct"] for row in rows),
        "effective_cd_direct_max": max(
            row["effective_cd_direct"] for row in rows),
        "equivalent_orifice_diameter_mm_min": min(
            row["equivalent_orifice_diameter_mm"] for row in rows),
        "equivalent_orifice_diameter_mm_max": max(
            row["equivalent_orifice_diameter_mm"] for row in rows),
        "required_equivalent_minor_loss_k_min": min(
            row["required_equivalent_minor_loss_k"] for row in rows),
        "required_equivalent_minor_loss_k_max": max(
            row["required_equivalent_minor_loss_k"] for row in rows),
        "reported_line_residual_explained_fraction": float(
            np.sum(direct - with_line) / np.sum(direct - measured)),
    }


PROUST_MODEL_QOIS = (
    "proust_flame_molkov_fit_measured_flow",
    "proust_flame_molkov_conservative_measured_flow",
    "proust_flame_delichatsios_measured_flow",
    "proust_flame_molkov_fit_predicted_flow",
    "proust_flame_molkov_conservative_predicted_flow",
    "proust_flame_delichatsios_predicted_flow",
)


def _proust_flame_observations() -> list[Observation]:
    observations = []
    for index, (pressure_bar, measured_length_m) in enumerate(
            PROUST_FLAME_3MM, start=1):
        temperature_c = _interpolate(pressure_bar, PROUST_TEMPERATURE_C)
        measured_flow = _interpolate(
            pressure_bar, PROUST_MASS_FLOW_G_S
        ) / 1000.0
        source = discharge(
            pressure_bar * 1e5,
            temperature_c + 273.15,
            "Hydrogen",
            0.003,
        )
        density = _throat_density(source)
        measured_flow_nozzle = notional_nozzle(
            measured_flow,
            source.throat_pressure_pa,
            source.velocity_m_s,
            density,
            0.003,
        )
        predicted_flow_nozzle = notional_nozzle(
            source.rate_kg_s,
            source.throat_pressure_pa,
            source.velocity_m_s,
            density,
            0.003,
        )
        predictions = {
            "proust_flame_molkov_fit_measured_flow": molkov_flame_length(
                measured_flow, 0.003, conservative=False
            ),
            "proust_flame_molkov_conservative_measured_flow": (
                molkov_flame_length(measured_flow, 0.003, conservative=True)
            ),
            "proust_flame_delichatsios_measured_flow": flame_length(
                measured_flow,
                measured_flow_nozzle,
                0.003,
                model="delichatsios",
            ).length_m,
            "proust_flame_molkov_fit_predicted_flow": molkov_flame_length(
                source.rate_kg_s, 0.003, conservative=False
            ),
            "proust_flame_molkov_conservative_predicted_flow": (
                molkov_flame_length(
                    source.rate_kg_s, 0.003, conservative=True
                )
            ),
            "proust_flame_delichatsios_predicted_flow": flame_length(
                source.rate_kg_s,
                predicted_flow_nozzle,
                0.003,
                model="delichatsios",
            ).length_m,
        }
        measured_envelope = (
            min(predictions[name] for name in PROUST_MODEL_QOIS[:3]),
            max(predictions[name] for name in PROUST_MODEL_QOIS[:3]),
        )
        predicted_envelope = (
            min(predictions[name] for name in PROUST_MODEL_QOIS[3:]),
            max(predictions[name] for name in PROUST_MODEL_QOIS[3:]),
        )
        for qoi, predicted in predictions.items():
            low, high = (
                measured_envelope if qoi.endswith("measured_flow")
                else predicted_envelope
            )
            observations.append(Observation(
                test_id=f"PROUST-FLAME-{index:02d}",
                qoi=qoi,
                measured=measured_length_m,
                predicted=predicted,
                unit="m",
                measurement_std=0.20,
                model_low=low,
                model_high=high,
                source=PROUST_SOURCE,
                condition_note=(
                    f"d=3 mm; P={pressure_bar:g} bar; interpolated "
                    f"T={temperature_c:.3f} degC; interpolated measured "
                    f"flow={1000 * measured_flow:.3f} g/s; visible-flame "
                    "uncertainty +/-0.20 m; retained isolated marker from "
                    "the digitized blowdown series"
                ),
            ))
    return observations


ROYLE_MODEL_QOIS = (
    "royle_unattached_flame_delichatsios_cd1_assumed_288k",
    "royle_unattached_flame_delichatsios_cd061_assumed_288k",
)


def _royle_flame_observations() -> list[Observation]:
    """Royle flame-length source sensitivities with missing inputs exposed."""
    rows = []
    for diameter_mm, measured_length_m in ROYLE_UNATTACHED_FLAME_M:
        diameter_m = diameter_mm / 1000.0
        source = discharge(
            ROYLE_PRESSURE_BAR * 1e5,
            ROYLE_ASSUMED_TEMPERATURE_K,
            "Hydrogen",
            diameter_m,
        )
        density = _throat_density(source)
        predictions = {}
        for qoi, cd in zip(ROYLE_MODEL_QOIS, (1.0, PROUST_CD_SENSITIVITY)):
            rate = cd * source.rate_kg_s
            nozzle = notional_nozzle(
                rate,
                source.throat_pressure_pa,
                source.velocity_m_s,
                density,
                diameter_m,
            )
            predictions[qoi] = flame_length(
                rate, nozzle, diameter_m, model="delichatsios"
            ).length_m
        low, high = min(predictions.values()), max(predictions.values())
        for qoi, predicted in predictions.items():
            rows.append(Observation(
                test_id=f"ROYLE-d{diameter_mm:g}",
                qoi=qoi,
                measured=measured_length_m,
                predicted=predicted,
                unit="m",
                model_low=low,
                model_high=high,
                source=ROYLE_SOURCE,
                condition_note=(
                    f"unattached visible flame; d={diameter_mm:g} mm; "
                    "nominal P=205 bar; ignition delay=800 ms; assumed "
                    "T=288.15 K because release temperature and measured "
                    "mass flow are not reported; restrictor length is "
                    "internally inconsistent (12 mm in section 2.3 versus "
                    "20 mm in Figure 2); Cd sensitivity, not full-chain "
                    "validation"
                ),
            ))
    return rows


EKOTO_MODEL_QOIS = (
    "ekoto_flame_molkov_fit_measured_flow",
    "ekoto_flame_molkov_conservative_measured_flow",
    "ekoto_flame_delichatsios_measured_flow",
)


def _ekoto_observations() -> list[Observation]:
    """Large-scale source and flame observations at reported conditions."""
    rows = []
    for test in EKOTO_LARGE_FLAMES:
        diameter_m = test["diameter_mm"] / 1000.0
        absolute_pressure_pa = (
            test["pressure_barg"] + test["ambient_pressure_bar"]
        ) * 1e5
        source = discharge(
            absolute_pressure_pa,
            test["temperature_k"],
            "Hydrogen",
            diameter_m,
        )
        common_note = (
            f"horizontal; d={test['diameter_mm']:g} mm; "
            f"P={test['pressure_barg']:g} barg; T={test['temperature_k']:g} K; "
            f"Pamb={test['ambient_pressure_bar']:g} bar; measured flow="
            f"{test['mass_flow_kg_s']:g} kg/s"
        )
        rows.append(Observation(
            test_id=f"EKOTO-{test['label']}-FLOW",
            qoi="ekoto_source_mass_flow_kg_s",
            measured=test["mass_flow_kg_s"],
            predicted=source.rate_kg_s,
            unit="kg/s",
            source=EKOTO_SOURCE,
            condition_note=(
                f"{common_note}; current sharp-hole Cd=1 source; source-term "
                "score is separate from measured-flow flame score"
            ),
        ))
        density = _throat_density(source)
        measured_nozzle = notional_nozzle(
            test["mass_flow_kg_s"],
            source.throat_pressure_pa,
            source.velocity_m_s,
            density,
            diameter_m,
        )
        predictions = {
            "ekoto_flame_molkov_fit_measured_flow": molkov_flame_length(
                test["mass_flow_kg_s"], diameter_m, conservative=False
            ),
            "ekoto_flame_molkov_conservative_measured_flow": (
                molkov_flame_length(
                    test["mass_flow_kg_s"], diameter_m, conservative=True
                )
            ),
            "ekoto_flame_delichatsios_measured_flow": flame_length(
                test["mass_flow_kg_s"],
                measured_nozzle,
                diameter_m,
                model="delichatsios",
            ).length_m,
        }
        low, high = min(predictions.values()), max(predictions.values())
        for qoi, predicted in predictions.items():
            rows.append(Observation(
                test_id=f"EKOTO-{test['label']}-FLAME",
                qoi=qoi,
                measured=test["visible_flame_length_m"],
                predicted=predicted,
                unit="m",
                model_low=low,
                model_high=high,
                source=EKOTO_SOURCE,
                condition_note=(
                    f"{common_note}; measured flow isolates flame-length "
                    "correlation; two-camera visible flame length"
                ),
            ))
    return rows


def observations() -> list[Observation]:
    """Return all immutable reference-versus-current-model rows."""
    return (
        _han_observations()
        + _ruggles_observations()
        + _proust_mass_flow_observations()
        + _proust_flame_observations()
        + _royle_flame_observations()
        + _ekoto_observations()
    )


def metric_summary(rows: list[Observation] | None = None) -> dict:
    """Metrics, screening decisions, and interpretation boundaries."""
    rows = observations() if rows is None else rows
    grouped: dict[str, list[Observation]] = {}
    for row in rows:
        grouped.setdefault(row.qoi, []).append(row)
    metric_rows = {
        qoi: asdict(metrics(values)) for qoi, values in sorted(grouped.items())
    }
    screening = {}
    for qoi, values in metric_rows.items():
        checks = {
            "normalized_mean_bias": (
                abs(values["normalized_mean_bias"])
                <= SCREENING["absolute_normalized_mean_bias_max"]
            ),
            "normalized_rmse": (
                values["normalized_rmse"]
                <= SCREENING["normalized_rmse_max"]
            ),
            "fraction_within_factor_two": (
                values["fraction_within_factor_two"]
                >= SCREENING["fraction_within_factor_two_min"]
            ),
        }
        screening[qoi] = {"checks": checks, "passes_all": all(checks.values())}
    return {
        "n_rows": len(rows),
        "screening_thresholds": SCREENING,
        "metrics_by_qoi": metric_rows,
        "screening_by_qoi": screening,
        "applicability": {
            "han_lfl": "d=0.5-1.0 mm, P=100-400 bar, T=293 K",
            "ruggles_dispersion": (
                "d=1.5 mm, P0=0.9832 MPa, T0=295.4 K, pressure ratio 10:1"
            ),
            "proust_mass_flow": (
                "d=3 mm, P=100-900 bar, blowdown through a 10 m feed pipe"
            ),
            "proust_flame": (
                "d=3 mm, retained markers P=137.6-792.4 bar, horizontal "
                "blowdown"
            ),
            "royle_flame": (
                "d=1.5, 3.2, 6.4 and 9.5 mm at nominal 205 bar; source "
                "temperature, measured flow and consistent restrictor length "
                "are unavailable"
            ),
            "ekoto_flame": (
                "d=20.9 and 52.5 mm near 60 barg; reported boundary "
                "conditions and measured mass flow"
            ),
        },
        "interpretation": [
            "Proust/INERIS test families occur in the development data for "
            "Molkov-Saffers eq.8: these Molkov scores are not independent validation.",
            "Molkov eq.8 was developed at d=0.4-10.1 mm; the 20.9/52.5 mm "
            "Ekoto comparisons are two extrapolation checks, not a jointly validated range.",
            "Ruggles scores use virtual-origin slope comparisons, not a direct "
            "operating-profile validation until the coordinate mapping is resolved.",
            "Graph digitization adds reading error and is not raw instrument data.",
            "Proust flame markers belong to one blowdown series and are not "
            "64 independent experiments.",
            "Measured-flow scores remove predicted-flow bias; Delichatsios "
            "still depends on the reconstructed notional-nozzle state. "
            "Predicted-flow scores combine source-term and flame-model errors.",
            "Agreement of the combined chain can arise from cancellation and "
            "does not validate either submodel separately.",
            "Adding the reported 10 m, 10 mm-ID feed line reduces predicted "
            "Proust flow only slightly and does not explain the source-term "
            "residual; the earlier pipe-loss explanation is rejected.",
            "The Cd=0.61 Proust sensitivity passes the screening rule, but "
            "the original paper does not report nozzle length or inlet "
            "geometry, so this is not apparatus validation.",
            "Pressure-resolved effective Cd is not constant; a fitted Cd "
            "absorbs unresolved nozzle, transient and mass-derivative effects.",
            "Royle 6.4/9.5 mm and Ekoto 20.9 mm reduce the diameter-only "
            "flame gap, but no independent test jointly covers the current "
            "6-25 mm leaks at their 350-700 bar design pressures.",
            "Royle rows are source sensitivities because temperature, "
            "measured flow and consistent restriction geometry are missing; "
            "they are not full-chain validation.",
            "Ekoto measured-flow scores isolate flame length and do not "
            "validate the source term or dispersion model.",
        ],
        "proust_source_residual": proust_source_residual_summary(),
    }
