"""Convert a provider-owned liquid/two-phase release into chain rows.

This module performs contract checks and bookkeeping only.  It does not solve
flash, nozzle flow, droplet motion or tank dynamics; those values must already
be present in ``ResolvedLiquidRelease``.
"""
from __future__ import annotations

import math


def resolve_liquid_rows(packet: dict, ambient_pressure: float):
    steps = packet['steps']
    ends = [x['time_s'] for x in steps[1:]] + [packet['duration_s']]
    rows = []
    mass = energy = 0.0
    for step, end in zip(steps, ends):
        if step['airborne_liquid_mass_flow_kg_s'] > 1e-12:
            raise ValueError('provider airborne liquid needs a validated droplet/flash adapter')
        rate = float(step['total_mass_flow_kg_s'])
        gas_rate = float(step['gas_mass_flow_kg_s'])
        ground_rate = float(step['ground_liquid_mass_flow_kg_s'])
        if gas_rate > 1e-12:
            pressure = float(step['gas_pressure_pa_abs'])
            if not math.isclose(pressure, ambient_pressure, rel_tol=1e-6, abs_tol=1e-3):
                raise ValueError('provider flashed gas pressure is not an atmospheric boundary')
            gas_temperature = float(step['gas_temperature_k'])
            gas_density = float(step['gas_density_kg_m3'])
            gas_area = float(step['gas_effective_area_m2'])
            gas_velocity = float(step['gas_velocity_m_s'])
            if gas_velocity <= 0:
                raise ValueError('positive flashed gas flow requires positive velocity')
            direction = packet['direction_enu']
            gas = {
                'pressure_pa': pressure, 'temperature_k': gas_temperature,
                'density_kg_m3': gas_density, 'velocity_m_s': gas_velocity,
                'enthalpy_j_kg': float(step['specific_enthalpy_j_kg']),
                'effective_area_m2': gas_area,
            }
            velocity_vector = [gas_velocity * float(x) for x in direction]
        else:
            gas_temperature = gas_density = gas_area = 0.0
            gas = None
            velocity_vector = [0.0, 0.0, 0.0]
        outcomes = [dict(outcome) for outcome in step.get('droplet_class_outcomes', ())]
        rows.append({
            'time_s': float(step['time_s']),
            'total_mass_flow_kg_s': rate,
            'gas_mass_flow_kg_s': gas_rate,
            'airborne_liquid_mass_flow_kg_s': float(step['airborne_liquid_mass_flow_kg_s']),
            'ground_liquid_mass_flow_kg_s': ground_rate,
            'mass_residual_kg_s': 0.0,
            'real_nozzle': gas,
            'fictitious_nozzle': None,
            'velocity_vector_m_s': velocity_vector,
            'gas_boundary_temperature_k': gas_temperature,
            'gas_boundary_density_kg_m3': gas_density,
            'gas_boundary_area_m2': gas_area,
            'droplet_class_outcomes': outcomes,
            'discharge_recalculated': False,
        })
        mass += rate * (end - step['time_s'])
        energy += rate * float(step['specific_enthalpy_j_kg']) * (end - step['time_s'])
    if not rows:
        raise ValueError('provider liquid release returned no interval')
    if not math.isclose(mass, packet['cumulative_mass_out_kg'], rel_tol=1e-8, abs_tol=1e-10):
        raise ValueError('provider liquid mass ledger disagrees')
    if not math.isclose(energy, packet['cumulative_specific_enthalpy_out_j'], rel_tol=1e-8, abs_tol=1e-6):
        raise ValueError('provider liquid enthalpy ledger disagrees')
    return rows, {
        'provider_boundary': packet,
        'model_name': 'equipment-resolved-atmospheric-liquid-two-phase-exit',
        'steps': rows,
        'discharge_recalculated': False,
        'equipment_dynamics_recalculated': False,
        'mass_out_kg': mass,
        'static_enthalpy_out_j': energy,
        'energy_scope': 'provider total outlet enthalpy transport checked; flash and droplet energy are provider-owned',
        'operator_limited': True,
        'limitations': [
            'provider owns liquid/two-phase flash and droplet partition',
            'airborne liquid is rejected until a validated droplet adapter is supplied',
        ],
    }
