"""Convert a provider-owned liquid/two-phase release into chain rows.

This module performs contract checks and bookkeeping only.  It does not solve
flash, nozzle flow, droplet motion or tank dynamics; those values must already
be present in ``ResolvedLiquidRelease``.
"""
from __future__ import annotations

import math
import re


_DYNAMIC_TERMINATION_BASES = {
    'reviewed_isolation_success',
    'inventory_depletion',
    # A provider-owned finite 600 s history is a valid bounded diagnostic
    # closure, but it is not equivalent to full inventory depletion.
    'inventory_over_600s',
    'emergency_relief_discharge',
    # DynamicHEMPipe may terminate when its provider-owned finite-volume
    # pressure reaches the declared boundary.  This is a physical closure
    # basis when the accompanying state-history and mass ledger checks pass.
    'model_pressure_equalization',
}
_MASS_TOLERANCE_KG = 1.0e-8


def dynamic_state_closure_status(packet: dict) -> dict:
    """Audit the optional provider-owned dynamic pressure/inventory closure.

    The default is intentionally closed (not ready).  A provider must opt in
    with the nested ``provider_mass_balance.dynamic_state_closure`` record and
    also provide a closed initial/final/outgoing mass ledger.  This function
    is kept independent of the atmospheric dispersion calculation so a
    missing or malformed provider field cannot be repaired downstream.
    """

    checks = {
        'record_present': False,
        'inventory_feedback_closed': False,
        'pressure_feedback_closed': False,
        'state_history_digest_present': False,
        'inventory_residual_within_tolerance': False,
        'pressure_residual_within_tolerance': False,
        'mass_ledger_present': False,
        'mass_ledger_closed': False,
        'termination_basis_compatible': False,
    }
    reasons: list[str] = []
    balance = packet.get('provider_mass_balance')
    closure = balance.get('dynamic_state_closure') if isinstance(balance, dict) else None
    checks['record_present'] = isinstance(closure, dict)
    if not checks['record_present']:
        reasons.append('provider dynamic pressure/inventory closure evidence is missing')
        return {'ready': False, 'checks': checks, 'blocking_reasons': reasons}

    checks['inventory_feedback_closed'] = closure.get('inventory_feedback_closed') is True
    checks['pressure_feedback_closed'] = closure.get('pressure_feedback_closed') is True
    checks['state_history_digest_present'] = bool(
        isinstance(closure.get('state_history_digest'), str)
        and re.fullmatch(r'[0-9a-f]{64}', closure['state_history_digest'])
    )
    if not checks['inventory_feedback_closed']:
        reasons.append('provider inventory feedback is not explicitly closed')
    if not checks['pressure_feedback_closed']:
        reasons.append('provider pressure feedback is not explicitly closed')
    if not checks['state_history_digest_present']:
        reasons.append('provider dynamic state history digest is missing or malformed')

    max_inventory = closure.get('max_abs_inventory_residual_kg')
    inventory_tolerance = closure.get('inventory_tolerance_kg')
    checks['inventory_residual_within_tolerance'] = (
        _finite_nonnegative(max_inventory)
        and _finite_positive(inventory_tolerance)
        and max_inventory <= inventory_tolerance
    )
    max_pressure = closure.get('max_abs_pressure_residual_pa')
    pressure_tolerance = closure.get('pressure_tolerance_pa')
    checks['pressure_residual_within_tolerance'] = (
        _finite_nonnegative(max_pressure)
        and _finite_positive(pressure_tolerance)
        and max_pressure <= pressure_tolerance
    )
    if not checks['inventory_residual_within_tolerance']:
        reasons.append('provider dynamic inventory residual is outside its declared tolerance')
    if not checks['pressure_residual_within_tolerance']:
        reasons.append('provider dynamic pressure residual is outside its declared tolerance')

    initial = balance.get('initial_mass_kg')
    final = balance.get('final_mass_kg')
    released = balance.get('cumulative_mass_out_kg')
    cumulative_in = balance.get('cumulative_mass_in_kg')
    if cumulative_in is None:
        cumulative_in = 0.0
    residual = balance.get('derived_accounting_residual_kg')
    checks['mass_ledger_present'] = all(
        _finite_nonnegative(value)
        for value in (initial, final, released, cumulative_in)
    )
    if checks['mass_ledger_present']:
        expected = float(final) + float(released) - float(initial) - float(cumulative_in)
        checks['mass_ledger_closed'] = (
            _finite(residual)
            and abs(expected) <= _MASS_TOLERANCE_KG
            and abs(float(residual)) <= _MASS_TOLERANCE_KG
        )
    if not checks['mass_ledger_present'] or not checks['mass_ledger_closed']:
        reasons.append('provider dynamic state mass ledger is missing or not closed')

    basis = packet.get('termination_basis')
    checks['termination_basis_compatible'] = basis in _DYNAMIC_TERMINATION_BASES
    if not checks['termination_basis_compatible']:
        reasons.append('dynamic source requires a reviewed isolation, inventory depletion, or relief termination basis')
    if basis == 'reviewed_isolation_success' and balance.get('isolation_success') is not True:
        checks['termination_basis_compatible'] = False
        reasons.append('reviewed isolation termination requires provider isolation_success=true')
    if basis == 'inventory_depletion' and (not checks['mass_ledger_present'] or float(final) > _MASS_TOLERANCE_KG):
        checks['termination_basis_compatible'] = False
        reasons.append('inventory depletion requires provider final mass at or below tolerance')

    reasons = list(dict.fromkeys(reasons))
    return {'ready': not reasons, 'checks': checks, 'blocking_reasons': reasons}


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _finite_nonnegative(value) -> bool:
    return _finite(value) and float(value) >= 0.0


def _finite_positive(value) -> bool:
    return _finite(value) and float(value) > 0.0


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
    dynamic_closure = dynamic_state_closure_status(packet)
    return rows, {
        'provider_boundary': packet,
        'model_name': 'equipment-resolved-atmospheric-liquid-two-phase-exit',
        'steps': rows,
        'discharge_recalculated': False,
        'equipment_dynamics_recalculated': False,
        'mass_out_kg': mass,
        'static_enthalpy_out_j': energy,
        'energy_scope': 'provider total outlet enthalpy transport checked; flash and droplet energy are provider-owned',
        'dynamic_state_closure': dynamic_closure,
        'operator_limited': not dynamic_closure['ready'],
        'limitations': [
            'provider owns liquid/two-phase flash and droplet partition',
            'airborne liquid is rejected until a validated droplet adapter is supplied',
        ] + dynamic_closure['blocking_reasons'],
    }
