"""PH checks for a provider gas exit; standalone worker has no Pydantic need."""
import math


def resolve_gas_rows(packet,ambient_pressure,cp):
    fluid=packet['property_basis']['fluid']
    rows=[];checks=[];mass=energy=0.
    steps=packet['steps']
    ends=[x['time_s'] for x in steps[1:]]+[packet['duration_s']]
    for step,end in zip(steps,ends):
        pressure=step['pressure_pa_abs'];enthalpy=step['specific_enthalpy_j_kg']
        rate=step['mass_flow_kg_s'];velocity=step['velocity_m_s'];area=step['effective_area_m2']
        if not math.isclose(pressure,ambient_pressure,rel_tol=1e-6,abs_tol=1e-3):
            raise ValueError('underexpanded outlet requires its own expansion adapter; no second discharge calculation')
        temperature=cp.PropsSI('T','P',pressure,'H',enthalpy,fluid)
        density=cp.PropsSI('D','P',pressure,'H',enthalpy,fluid)
        quality=cp.PropsSI('Q','P',pressure,'H',enthalpy,fluid)
        tsat=cp.PropsSI('T','P',pressure,'Q',1,fluid)
        if (0<=quality<1) or temperature<tsat-1e-6:
            raise ValueError('resolved liquid/two-phase exit needs flash and droplet partition; cannot be labelled gas')
        if not math.isclose(step['temperature_k'],temperature,rel_tol=1e-7,abs_tol=1e-5) or not math.isclose(step['density_kg_m3'],density,rel_tol=1e-7,abs_tol=1e-9):
            raise ValueError('provider PH/temperature/density disagree under the declared fluid basis')
        if not math.isclose(rate,density*velocity*area,rel_tol=1e-7,abs_tol=1e-12):
            raise ValueError('resolved flow continuity fails against EOS density')
        sound=cp.PropsSI('A','P',pressure,'H',enthalpy,fluid)
        mach=velocity/sound
        if mach>.3:
            raise ValueError('resolved low-Mach gas exit scope exceeded; compressible/underexpanded plane adapter required')
        nozzle={'pressure_pa':pressure,'temperature_k':temperature,'density_kg_m3':density,
            'velocity_m_s':velocity,'enthalpy_j_kg':enthalpy,'diameter_m':math.sqrt(4*area/math.pi)}
        rows.append({'time_s':step['time_s'],'total_mass_flow_kg_s':rate,'gas_mass_flow_kg_s':rate,
            'airborne_liquid_mass_flow_kg_s':0.,'ground_liquid_mass_flow_kg_s':0.,'mass_residual_kg_s':0.,
            'real_nozzle':nozzle,'fictitious_nozzle':None,
            'velocity_vector_m_s':[velocity*x for x in packet['direction_enu']],
            'gas_boundary_temperature_k':temperature,'gas_boundary_density_kg_m3':density,
            'gas_boundary_area_m2':area,'droplet_class_outcomes':[],'discharge_recalculated':False})
        checks.append({'time_s':step['time_s'],'PH_temperature_k':temperature,'PH_density_kg_m3':density,
            'quality':quality,'mach_number':mach,'static_enthalpy_j_kg':enthalpy,
            'specific_kinetic_energy_j_kg':.5*velocity**2})
        mass+=rate*(end-step['time_s']);energy+=rate*enthalpy*(end-step['time_s'])
    if not math.isclose(mass,packet['cumulative_mass_out_kg'],rel_tol=1e-8,abs_tol=1e-10) or not math.isclose(energy,packet['cumulative_static_enthalpy_out_j'],rel_tol=1e-8,abs_tol=1e-6):
        raise ValueError('provider time-integrated boundary ledger disagrees')
    return rows,{'provider_boundary':packet,'thermodynamic_checks':checks,
        'model_name':'equipment-resolved-atmospheric-gas-exit','steps':rows,
        'discharge_recalculated':False,'equipment_dynamics_recalculated':False,
        'mass_out_kg':mass,'static_enthalpy_out_j':energy,
        'energy_scope':'provider static-enthalpy transport checked; kinetic energy reported separately; full source-to-cloud energy not qualified'}
