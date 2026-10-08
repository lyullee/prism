"""Adapters for explicit finite-inventory liquid-jet source histories.

The upstream ``slabx_lh2.lh2_jet_source`` returns a rich dataclass history
whose final sample is an endpoint at ``duration_s``.  PRISM's chain uses
left-held intervals, so this adapter drops only that endpoint and preserves
the gas/ground mass partition and impact timing.  It does not infer a leak
rate or add a tank feedback model.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def liquid_jet_rows(history, duration_s: float) -> tuple[list[dict], dict]:
    """Convert an external liquid-jet history into PRISM source rows."""
    if not is_dataclass(history):
        raise ValueError("liquid-jet history must be a dataclass result")
    raw = _json_safe(asdict(history))
    steps = raw.get("steps", [])
    if not steps:
        raise ValueError("liquid-jet source returned no history")
    starts = [float(s["time_s"]) for s in steps if float(s["time_s"]) < duration_s - 1e-12]
    if not starts or not math.isclose(starts[0], 0.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError("liquid-jet source must provide a left-held interval at zero")
    if any(b <= a for a, b in zip(starts, starts[1:])):
        raise ValueError("liquid-jet source times must increase")
    rows = []
    for step in steps:
        t = float(step["time_s"])
        if t >= duration_s - 1e-12:
            continue
        gas = step["gas"]
        ground = step["ground"]
        conservation = step["conservation"]
        total = float(conservation["mass_in_kg_s"])
        gas_rate = float(gas["mass_flow_kg_s"])
        ground_rate = float(ground["mass_flow_kg_s"])
        if total < 0 or gas_rate < 0 or ground_rate < 0:
            raise ValueError("liquid-jet source rates must be nonnegative")
        if not math.isclose(total, gas_rate + ground_rate, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError("liquid-jet mass partition does not close")
        outcomes = []
        if ground_rate > 1e-12:
            flight = ground["flight_time_s"]
            impact = ground["impact_position_m"]
            if flight is None or impact is None or not all(math.isfinite(float(x)) for x in impact):
                raise ValueError("positive ground liquid requires finite flight time and impact position")
            outcomes.append({'ground_liquid_mass_flow_kg_s': ground_rate,
                             'flight_time_s': float(flight),
                             'impact_position_m': list(impact),
                             'droplet': {'smd_m': None}})
        direction = gas["direction"]
        velocity = float(gas["velocity_m_s"])
        rows.append({
            'time_s': t,
            'total_mass_flow_kg_s': total,
            'gas_mass_flow_kg_s': gas_rate,
            'airborne_liquid_mass_flow_kg_s': 0.0,
            'ground_liquid_mass_flow_kg_s': ground_rate,
            'mass_residual_kg_s': float(conservation["mass_residual_kg_s"]),
            'real_nozzle': gas,
            'fictitious_nozzle': None,
            'velocity_vector_m_s': [velocity * float(x) for x in direction],
            'gas_boundary_temperature_k': float(gas["temperature_k"]),
            'gas_boundary_density_kg_m3': float(gas["density_kg_m3"]),
            'gas_boundary_area_m2': float(gas["effective_area_m2"]),
            'droplet_class_outcomes': outcomes,
            'discharge_recalculated': True,
        })
    if not rows:
        raise ValueError("liquid-jet source returned no interval before its endpoint")
    if max(abs(float(x['mass_residual_kg_s'])) for x in rows) > 1e-8:
        raise ValueError("liquid-jet mass conservation residual exceeds tolerance")
    return rows, raw
