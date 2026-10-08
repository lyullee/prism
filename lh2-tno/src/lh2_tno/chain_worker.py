"""Real research-model calls for the complete, diagnostic outdoor chain.

The finite-volume observation operator is deliberately an integral/top-hat
reconstruction of SLAB's section averages. It is not the frozen FFI field
route, a CFD solver, or a newly validated transient dispersion model.
"""
from __future__ import annotations
from dataclasses import asdict
import json
import math
import time
import numpy as np
try:
    from .source_termination import effective_source_duration
    from .inventory_source import liquid_jet_rows
    from .resolved_liquid_worker import resolve_liquid_rows
except ImportError:  # isolated worker imports this module as a top-level file
    from source_termination import effective_source_duration
    from inventory_source import liquid_jet_rows
    from resolved_liquid_worker import resolve_liquid_rows

MW_H2=.002016
MW_AIR=.028965
R=8.314462618


def intervals(rows, end):
    return [(r, rows[i+1]['time_s'] if i+1<len(rows) else end) for i,r in enumerate(rows)]


def branch_mass(rows, end, quantity, at=None):
    at=end if at is None else at
    return sum(r[quantity]*max(0.,min(at,e)-r['time_s']) for r,e in intervals(rows,end))


def pulse_mass(pulses,at):
    return sum(r['rate']*max(0.,min(at,r['end'])-r['start']) for r in pulses)


def grid_axes(domain):
    edges=[]
    for key in ('downwind_bounds_m','crosswind_bounds_m','height_bounds_m'):
        a,b=domain[key]
        edges.append(np.linspace(a,b,math.ceil((b-a)/domain['cell_size_m'])+1))
    return edges


def box_fractions(edges, centre, sizes):
    """Exact overlap volume of a rectangular packet with each grid cell."""
    fractions=[]
    for axis,c,size in zip(edges,centre,sizes):
        left=c-size/2; right=c+size/2
        overlap=np.maximum(0.,np.minimum(axis[1:],right)-np.maximum(axis[:-1],left))
        fractions.append(overlap/np.diff(axis))
    return fractions[0][:,None,None]*fractions[1][None,:,None]*fractions[2][None,None,:]


def mole_fraction(hydrogen_density, air_density):
    nh=np.asarray(hydrogen_density)/MW_H2
    na=np.asarray(air_density)/MW_AIR
    return np.divide(nh,nh+na,out=np.zeros_like(nh,dtype=float),where=(nh+na)>0)


def weighted_union_harm(*effects):
    """Frechet union upper bound, requiring no independence assumption."""
    return min(1.,sum(effects))


def dose_harm(samples, stop, probit):
    """Exact dose for left-held physical flux; contact encoded separately."""
    dose=0.; contact=False
    for row,end in intervals(samples,stop):
        dt=max(0.,min(end,stop)-row['time_s'])
        if dt<=0:continue
        dose+=dt*row['flux_w_m2']**(4/3)
        contact |= row['flame_contact']
    if contact:return {'dose':dose,'harm_probability':1.,'flame_contact':True}
    pe=0. if dose<=0 else probit.probit_to_probability(probit.ThermalProbit().a+probit.ThermalProbit().b*math.log(dose))
    return {'dose':dose,'harm_probability':pe,'flame_contact':False}


def run_chain(p,roots,module):
    timings={}
    def mark(name,started):timings[name]=(time.perf_counter()-started)*1000
    start=time.perf_counter()
    cp=__import__('CoolProp.CoolProp',fromlist=['PropsSI'])
    source=p['source_input']; requested_duration=source['duration_s']
    duration=requested_duration
    duration_mode=p.get('source_duration_mode','declared')
    source_operator=p.get('source_operator','integrated_transient')
    resolved=p.get('resolved_release')
    resolved_liquid=p.get('resolved_liquid_release')
    equipment_resolved = resolved is not None or resolved_liquid is not None
    if resolved is not None and resolved_liquid is not None:
        raise ValueError('gas and liquid provider releases cannot be supplied together')
    if resolved is not None:
        from resolved_gas_worker import resolve_gas_rows
        rows,source_history=resolve_gas_rows(resolved,source['ambient']['pressure_pa'],cp)
    elif resolved_liquid is not None:
        rows,source_history=resolve_liquid_rows(resolved_liquid,source['ambient']['pressure_pa'])
        duration=source['duration_s']
        source_history.update(source_operator=source_operator,
            requested_duration_s=duration,effective_duration_s=duration,
            source_duration_mode='declared',
            termination_basis=p.get('release_termination',{}).get('basis'),
            operator_limited=True)
    elif source_operator == 'inventory_liquid_jet':
        jetmod=module('slabx_lh2.lh2_jet_source',roots['slabx_lh2'])
        spray=source['liquid_jet']
        history=jetmod.evaluate_liquid_jet(
            jetmod.StorageState(pressure_pa=source['tank']['pressure_pa'],
                temperature_k=source['tank']['temperature_k'],
                discharge_coefficient=spray['discharge_coefficient'],
                fluid=source['tank']['fluid']),
            jetmod.Nozzle(diameter_m=source['nozzle']['diameter_m'],
                height_m=source['nozzle']['height_m'],
                direction=tuple(source['nozzle']['direction_enu'])),
            jetmod.Environment(pressure_pa=source['ambient']['pressure_pa'],
                temperature_k=source['ambient']['temperature_k'],
                wind_speed_m_s=source['ambient']['wind_speed_m_s'],
                wind_from_bearing_deg=source['ambient']['wind_from_bearing_deg']),
            requested_duration, time_step_s=source['time_step_s'],
            spray=jetmod.SprayAssumptions(
                droplet_diameter_m=spray['droplet_diameter_m'],
                d2_evaporation_constant_m2_s=spray['d2_evaporation_constant_m2_s'],
                spray_half_angle_deg=spray['spray_half_angle_deg'],
                liquid_velocity_fraction=spray['liquid_velocity_fraction']))
        rows,raw_history=liquid_jet_rows(history,requested_duration)
        source_history=raw_history
        source_history.update(source_operator=source_operator,
            requested_duration_s=requested_duration,
            effective_duration_s=requested_duration,
            termination_basis=p.get('release_termination',{}).get('basis'),
            operator_limited=True,
            limitations=['constant upstream liquid-jet state; tank pressure/inventory feedback is not solved',
                         'declared d2 droplet evaporation and spray geometry; source energy closure remains open'])
        if not math.isclose(branch_mass(rows,requested_duration,'total_mass_flow_kg_s'),
                            p['available_mass_kg'],rel_tol=1e-6,abs_tol=1e-8):
            raise ValueError('inventory liquid-jet duration does not close the declared inventory')
    else:
        srcmod=module('slabx_lh2.integrated_lh2_source',roots['slabx_lh2'])
        inp=srcmod.IntegratedSourceInput(srcmod.TankState(**source['tank']),
            tuple(srcmod.PipeSection(**x) for x in source['pipe_sections']),
            srcmod.NozzleGeometry(**source['nozzle']),srcmod.AmbientState(**source['ambient']),
            srcmod.ModelChoices(**source['choices']),requested_duration,source['time_step_s'])
        history=srcmod.evaluate_integrated_lh2_source(inp)
        source_history=asdict(history)
        rows=source_history['steps']
        duration=effective_source_duration(requested_duration,source['time_step_s'],
            [r['time_s'] for r in rows],duration_mode)
        source_history.update(requested_duration_s=requested_duration,
            effective_duration_s=duration,source_duration_mode=duration_mode,
            natural_termination_detected=duration < requested_duration - 1e-12,
            termination_basis=p.get('release_termination',{}).get('basis'))
        clock_duration=next((t for t in p['evaluation_times_s']
            if math.isclose(t,duration,rel_tol=0,abs_tol=1e-10)),None)
        if clock_duration is None:
            raise ValueError('effective source termination must be an explicit evaluation timestamp')
        duration=clock_duration
        source_history['effective_duration_s']=duration
    if source_operator == 'inventory_liquid_jet' and duration not in p['evaluation_times_s']:
        raise ValueError('inventory depletion duration must be an explicit evaluation timestamp')
    if source_operator == 'equipment_liquid_release' and duration not in p['evaluation_times_s']:
        raise ValueError('equipment liquid release duration must be an explicit evaluation timestamp')
    mass=branch_mass(rows,duration,'total_mass_flow_kg_s')
    if mass>p['available_mass_kg']+1e-9:raise ValueError('release exceeds available inventory')
    if max(abs(r['mass_residual_kg_s']) for r in rows)>1e-8:
        raise ValueError('source partition does not close')
    if any(r['airborne_liquid_mass_flow_kg_s']>1e-9 for r in rows):
        raise ValueError('unresolved airborne liquid cannot silently become vapour')
    mark('source',start)
    weather=p['weather']; times=p['evaluation_times_s']; horizon=times[-1]
    ambient=source['ambient']; fluid=source['tank']['fluid']
    origin=np.asarray(p['source_position_enu_m'],float)
    vertical_handoff=source.get('vertical_handoff') if resolved is not None else None
    if vertical_handoff is not None:
        # The provider has already resolved the vertical momentum into a
        # horizontal carrier section.  Dispersion starts at that declared
        # handoff position; PRISM does not rotate the vertical exit itself.
        origin=np.asarray(vertical_handoff['position_enu_m'],float)
    to=math.radians((weather['wind_from_bearing_deg']+180)%360)
    down=np.array([math.sin(to),math.cos(to),0.])
    cross=np.array([math.cos(to),-math.sin(to),0.])
    def to_frame(pos):return np.array([np.dot(pos,down),np.dot(pos,cross),pos[2]])
    def to_enu(pos):return (down*pos[0]+cross*pos[1]+np.array([0.,0.,pos[2]])).tolist()
    # Ground transfer rate is solely the upstream source-model result.
    start=time.perf_counter(); pool=None; pool_origin=None; pool_packets=[];ground_pulses=[]
    if branch_mass(rows,duration,'ground_liquid_mass_flow_kg_s')>0:
        if p['pool'] is None:raise ValueError('positive rainout requires an explicit resolved pool footprint')
        if fluid!='Hydrogen':raise ValueError('native DynamicLH2PoolX uses Hydrogen; ParaHydrogen pool basis unsupported')
        m=module('dynamiclh2poolx',roots['dynamiclh2poolx'])
        boundary=p['pool']
        surface=m.SolidSemiInfiniteSurface(name=boundary['footprint_origin'],
            conductivity_W_mK=boundary['conductivity_w_mk'],diffusivity_m2_s=boundary['diffusivity_m2_s'],
            initial_temperature_K=boundary['initial_temperature_k'])
        numerics=m.ShallowLayerNumerics(domain_radius_m=boundary['domain_radius_m'],
            source_radius_m=boundary['radius_m'],radial_step_m=boundary['radial_step_m'],
            maximum_time_step_s=boundary['maximum_time_step_s'])
        positions=[]
        for row,end in intervals(rows,duration):
            outcomes=[o for o in row['droplet_class_outcomes'] if o['ground_liquid_mass_flow_kg_s']>0]
            if not math.isclose(sum(o['ground_liquid_mass_flow_kg_s'] for o in outcomes),row['ground_liquid_mass_flow_kg_s'],abs_tol=1e-9):
                raise ValueError('ground arrival classes do not close the rainout rate')
            for o in outcomes:
                delay=o['flight_time_s']
                if delay is None or delay<0 or o['impact_position_m'] is None:
                    raise ValueError('rainout lacks resolved flight time/impact position')
                ground_pulses.append({'start':row['time_s']+delay,'end':end+delay,
                                      'rate':o['ground_liquid_mass_flow_kg_s'],'flight_time_s':delay})
                positions.append(o['impact_position_m'])
        if not positions:raise ValueError('rainout lacks resolved arrival boundary')
        if max(r['end'] for r in ground_pulses)>horizon:
            raise ValueError('consequence horizon must cover the final ground arrival')
        if any(math.dist(positions[0],x)>1e-6 for x in positions[1:]):
            raise ValueError('moving deposition footprint needs a spatially moving pool solver')
        pool_origin=origin+np.asarray(positions[0])-np.array([0.,0.,origin[2]])
        knots=sorted(set([0.,horizon]+[r[k] for r in ground_pulses for k in ('start','end')]))
        inflow=m.DeclaredInflow(tuple(knots),tuple(sum(r['rate'] for r in ground_pulses if r['start']<=t<r['end']) for t in knots))
        pool=m.run_dynamic_pool(m.DynamicPoolConfig(surface=surface,numerics=numerics,
                    ambient_pressure_Pa=ambient['pressure_pa']),inflow,tuple(times)).to_dict()
        if abs(pool['mass_balance_residual_kg'])>max(1e-8,mass*1e-8):
            raise ValueError('pool mass balance failed')
        for a,b in zip(pool['ledger'],pool['ledger'][1:]):
            evaporated=b['cumulative_evaporation_kg']-a['cumulative_evaporation_kg']
            if evaporated>1e-12:
                area=max(a['wet_area_m2'],b['wet_area_m2'])
                if area<=0:raise ValueError('pool vapour has no wet surface area')
                pool_packets.append({'start':a['time_s'],'end':b['time_s'],'mass':evaporated,
                                     'area':area,'temperature':b['pool_temperature_K']})
    mark('pool',start)
    # Resolve vector bending and carrier entrainment before SLAB handoff.
    start=time.perf_counter()
    transition=module('slabx_lh2.lh2_jet_cloud_transition',roots['slabx_lh2'])
    handmod=module('slabx_lh2.freejet_handoff',roots['slabx_lh2'])
    plume=module('slabx.core.plume',roots['slabx'])
    sourcemod=module('slabx.core.source',roots['slabx'])
    atm_mod=module('slabx.submodels.atmosphere',roots['slabx'])
    base=module('slabx.thermo.base',roots['slabx'])
    thermo=module('slabx.thermo.coolprop',roots['slabx'])
    ice=module('slabx_lh2.water_ice',roots['slabx_lh2'])
    atm=atm_mod.Atmosphere(u_ref=weather['wind_speed_m_s'],z_ref=weather['measurement_height_m'],
            T=ambient['temperature_k'],rh=weather['relative_humidity'],z0=weather['roughness_m'],stability=weather['stability'])
    substance=base.Substance(name='H2',mw=MW_H2,cp_vapour=14300.,cp_liquid=9800.,dh_vap=445000.,T_boil=20.3,rho_liquid=70.8)
    emission=thermo.CoolPropThermo(substance,fluid=fluid); water=ice.with_sublimation(thermo.coolprop_water())
    tsat=cp.PropsSI('T','P',ambient['pressure_pa'],'Q',1,fluid)
    rho_g=cp.PropsSI('D','P',ambient['pressure_pa'],'Q',1,fluid)
    rho_l=cp.PropsSI('D','P',ambient['pressure_pa'],'Q',0,fluid)
    rho_air=cp.PropsSI('D','P',ambient['pressure_pa'],'T',ambient['temperature_k'],'Air')
    direction=np.asarray(source['nozzle']['direction_enu'],float);direction/=np.linalg.norm(direction)
    release_bearing=math.degrees(math.atan2(direction[0],direction[1]))%360
    packets=[]; traj_cache={}; traces=[]
    def vertical_handoff_state(row):
        if vertical_handoff is None:
            return None
        states = vertical_handoff.get('states') or ()
        if not states:
            return vertical_handoff
        selected = states[0]
        for state in states:
            if state['time_s'] > row['time_s']:
                break
            selected = state
        return selected
    def trajectory(kind,rate,area,span,row=None):
        velocity=0. if row is None else max(1e-5,float(np.linalg.norm(row['velocity_vector_m_s'])))
        gas_temperature=tsat if row is None else row.get('gas_boundary_temperature_k',tsat)
        gas_density=rho_g if row is None else row.get('gas_boundary_density_kg_m3',rho_g)
        gas_area=None if row is None else row.get('gas_boundary_area_m2')
        handoff = vertical_handoff_state(row) if kind == 'jet' and row is not None else None
        handoff_key = None if handoff is None else json.dumps(handoff, sort_keys=True, separators=(',', ':'))
        key=(kind,rate,area,span,velocity,gas_temperature,gas_density,gas_area,handoff_key)
        if key in traj_cache:return traj_cache[key]
        near=[]; tt=0.; cross_offset=0.; base_origin=origin if kind=='jet' else pool_origin
        if kind=='jet' and handoff is not None:
            handoff_direction=np.asarray(handoff['direction_enu'],float)
            downvelocity=float(handoff['velocity_m_s']*np.dot(handoff_direction,down))
            if downvelocity<=0:
                raise ValueError('vertical handoff has no positive downwind velocity for this weather condition')
            total=rate/handoff['h2_mass_fraction']
            hs=handmod.FreeJetHandoffState(handoff_distance_m=0.01,duration_s=span,
                total_rate_kg_s=total,h2_mass_fraction=handoff['h2_mass_fraction'],
                temperature_K=handoff['temperature_k'],density_kg_m3=handoff['density_kg_m3'],
                velocity_m_s=downvelocity,centre_height_m=vertical_handoff['position_enu_m'][2],
                half_width_m=handoff['half_width_m'],depth_m=handoff['depth_m'],
                mixture_cp_J_kgK=handoff['h2_mass_fraction']*14300.+(1-handoff['h2_mass_fraction'])*1006.,
                source_model='equipment-resolved-vertical-gas + provider-horizontal-handoff',
                geometry_closure='provider-resolved horizontal handoff section')
            source_model=handmod.NearFieldHandoff(substance,hs,mass_tolerance=1e-8)
            traces.append({'branch':kind,'handoff':asdict(hs),'handoff_age_s':0.,
                           'entry_temperature_k':gas_temperature,'entry_density_kg_m3':gas_density,
                           'mass_residual_relative':hs.mass_residual_relative(),
                           'transition_mass_residual_kg_s':None,
                           'transition_energy_residual_w':None,
                           'provider_vertical_adapter':True})
        elif kind=='jet':
            transition_input=transition.TransitionInput(
                h2_rate_kg_s=rate,flash_vapour_mass_fraction=1.,flash_velocity_m_s=velocity,
                flash_area_m2=gas_area if gas_area is not None else rate/(gas_density*velocity),
                droplet_diameter_m=max(row.get('droplet',{}).get('smd_m',0.),1e-8),
                evaporation_kb_m2_s=1e-6,liquid_density_kg_m3=rho_l,h2_temperature_K=gas_temperature,
                ambient_temperature_K=ambient['temperature_k'],ambient_density_kg_m3=rho_air,
                ambient_wind_m_s=weather['wind_speed_m_s'],release_height_m=origin[2],
                friction_velocity_m_s=atm.u_star,release_bearing_deg=release_bearing,
                wind_from_bearing_deg=weather['wind_from_bearing_deg'],
                wind_measurement_height_m=weather['measurement_height_m'],surface_roughness_length_m=weather['roughness_m'],
                ambient_relative_humidity_percent=100*weather['relative_humidity'],
                resolve_cryogenic_air_phase=True,advanced_jet_physics=transition.AdvancedJetPhysics(),
                release_duration_s=span)
            # Do not compute a complete 100-m cryogenic transition when the
            # conservative SLAB handoff has already been reached at 5 cm.
            hand=None
            for limit in sorted(set(min(x,p['transition_x_max_m']) for x in (.5,2.,10.,50.,p['transition_x_max_m']))):
                near=transition.integrate_transition(transition_input,x_max_m=limit,
                            dx_m=p['transition_dx_m'],stop_on_passive=False)
                try:
                    hand=transition.select_handoff(near,h2_rate_kg_s=rate,ground_contact_required=False,
                                wind_alignment_tolerance_deg=10.)
                    break
                except RuntimeError:
                    continue
            if hand is None:raise ValueError('vector transition never reached a qualified downwind handoff')
            # Keep only the pre-handoff series: no overlapping near/far fields.
            near=[r for r in near if r.time_s<=hand.time_s]
            tt=hand.time_s
            downvelocity=hand.velocity_east_m_s*down[0]+hand.velocity_north_m_s*down[1]
            if downvelocity<=0:raise ValueError('handoff has no positive downwind velocity')
            total=rate/hand.h2_mass_fraction
            width=hand.effective_half_width_m
            depth=total/(hand.density_kg_m3*downvelocity*2*width)
            start_x=float(np.dot([hand.east_m,hand.north_m,0.],down))
            cross_offset=float(np.dot([hand.east_m,hand.north_m,0.],cross))
            if start_x<=0:raise ValueError('handoff remains upwind; no silent rotation into a downwind source')
            hs=handmod.FreeJetHandoffState(handoff_distance_m=start_x,duration_s=span,
                total_rate_kg_s=total,h2_mass_fraction=hand.h2_mass_fraction,temperature_K=hand.temperature_K,
                density_kg_m3=hand.density_kg_m3,velocity_m_s=downvelocity,centre_height_m=hand.height_m,
                half_width_m=width,depth_m=depth,mixture_cp_J_kgK=hand.h2_mass_fraction*14300.+(1-hand.h2_mass_fraction)*1006.,
                source_model='equipment-resolved-gas + vector-transition' if equipment_resolved else 'integrated-source-terminal-gas + vector-cryogenic-transition',
                geometry_closure='mass and downwind momentum preserving section')
            source_model=handmod.NearFieldHandoff(substance,hs,mass_tolerance=1e-8)
            traces.append({'branch':kind,'handoff':asdict(hs),'handoff_age_s':tt,
                           'entry_temperature_k':gas_temperature,'entry_density_kg_m3':gas_density,
                           'mass_residual_relative':hs.mass_residual_relative(),
                           'transition_mass_residual_kg_s':hand.mass_residual_kg_s,
                           'transition_energy_residual_w':hand.energy_residual_W})
        else:
            source_model=sourcemod.EvaporatingPool(substance,rate,area,duration=span,T_source=tsat)
        traj,used=plume.run_dispersion(source_model,atm,emission,water,x_max=p['dispersion_x_max_m'],
                                    t_max=max(horizon-tt,span+1e-3),n_puff_steps=p['n_puff_steps'])
        if not np.all(np.isfinite(traj.vol_frac)):raise ValueError('nonfinite dispersion state')
        result=(near,traj,tt,cross_offset,base_origin)
        traj_cache[key]=result
        return result
    for row,end in intervals(rows,duration):
        rate=row['gas_mass_flow_kg_s']
        if rate>1e-12:
            packets.append({'start':row['time_s'],'end':end,'mass':rate*(end-row['time_s']),
                            'trajectory':trajectory('jet',rate,0.,end-row['time_s'],row)})
    for pack in pool_packets:
        span=pack['end']-pack['start']
        packets.append({**pack,'trajectory':trajectory('pool',pack['mass']/span,pack['area'],span)})
    mark('near_field_and_dispersion',start)
    # Observation operator: causal finite inventories; exact grid-cell overlap.
    edges=grid_axes(p['domain']); dv=np.diff(edges[0])[:,None,None]*np.diff(edges[1])[None,:,None]*np.diff(edges[2])[None,None,:]
    centres=np.meshgrid(*( (a[:-1]+a[1:])/2 for a in edges),indexing='ij')
    receptors=p['receptors']; receptor_frames=[to_frame(np.asarray(r['position_enu_m'])) for r in receptors]
    def state(packet,t):
        fraction=min(1.,max(0.,(t-packet['start'])/(packet['end']-packet['start'])))
        amount=packet['mass']*fraction
        if amount<=0:return None
        # Midpoint of the emitted portion: no future inventory is introduced.
        birth=packet['start']+.5*min(t-packet['start'],packet['end']-packet['start'])
        age=t-birth
        near,traj,tt,offset,base_origin=packet['trajectory']
        if near and age<tt:
            def value(k):return float(np.interp(age,[r.time_s for r in near],[getattr(r,k) for r in near]))
            centre=to_frame(base_origin+np.array([value('east_m'),value('north_m'),value('height_m')-origin[2]]))
            width=value('effective_half_width_m');depth=value('layer_depth_m');rho=value('density_kg_m3');y=value('h2_mass_fraction')
        else:
            far_age=max(0.,age-tt)
            if far_age>float(traj.t[-1])+1e-8:raise ValueError('dispersion trajectory does not cover observation horizon')
            def value(k):return float(np.interp(far_age,traj.t,getattr(traj,k)))
            centre=to_frame(base_origin)+np.array([value('x'),offset,value('z_c')-base_origin[2]])
            width=value('b_half');depth=value('h');rho=value('rho');y=value('mass_frac')
        if not 0<y<=1 or min(width,depth,rho)<=0:raise ValueError('invalid carrier section')
        # The finite length is determined by H2 inventory and carrier density,
        # instead of an unlimited stationary footprint or an LFL mass proxy.
        length=amount/(rho*y*2*width*depth)
        centre[2]=max(depth/2,centre[2])
        sizes=np.array([length,2*width,depth])
        return {'mass':amount,'centre':centre,'sizes':sizes,'rho_h':rho*y,'rho_a':rho*(1-y)}
    cloud=[]; cloud_at={}; rec_history=[[] for _ in receptors]
    start=time.perf_counter()
    for t in times:
        dh=np.zeros_like(dv);da=np.zeros_like(dv);occupancy=np.zeros_like(dv)
        rh=np.zeros(len(receptors));ra=np.zeros(len(receptors));ro=np.zeros(len(receptors))
        emitted=0.
        for packet in packets:
            s=state(packet,t)
            if s is None:continue
            emitted+=s['mass']
            f=box_fractions(edges,s['centre'],s['sizes'])
            dh+=f*s['rho_h'];da+=f*s['rho_a'];occupancy+=f
            for i,r in enumerate(receptor_frames):
                if np.all(np.abs(r-s['centre'])<=s['sizes']/2):
                    rh[i]+=s['rho_h'];ra[i]+=s['rho_a'];ro[i]+=1
        # Superposed packets conserve H2, while entrained carriers overlap.
        # Ambient air fills uncovered volume. Carrier overlap is reported;
        # pressure/temperature equilibration of overlapping packets is open.
        da+=np.maximum(0.,1-occupancy)*rho_air
        ra+=np.maximum(0.,1-ro)*rho_air
        concentration=mole_fraction(dh,da);receptor_c=mole_fraction(rh,ra)
        inside=(concentration>=.04)&(concentration<=.75)
        fm=float(np.sum(dh*dv*inside));in_domain=float(np.sum(dh*dv))
        if in_domain>emitted+max(1e-9,emitted*1e-8):raise ValueError('cloud grid inventory exceeds emitted vapour')
        outside=max(0.,emitted-in_domain)
        centroid=[float(np.sum(centres[j]*dh*dv*inside)/fm) for j in range(3)] if fm>0 else to_frame(origin).tolist()
        bounds=None
        if np.any(inside):
            indices=np.where(inside)
            bounds=[[float(edges[j][indices[j].min()]),float(edges[j][indices[j].max()+1])] for j in range(3)]
        row={'time_s':t,'vapour_emitted_kg':emitted,'hydrogen_in_domain_kg':in_domain,
             'hydrogen_outside_domain_kg':outside,'mass_residual_kg':emitted-in_domain-outside,
             'flammable_mass_in_domain_kg':fm,'flammable_centroid_enu_m':to_enu(centroid),
             'flammable_bounds_wind_frame_m':bounds,'maximum_mole_fraction':float(np.max(concentration)),
             'overlapping_carrier_cells':int(np.sum(occupancy>1+1e-8)),
             'ground_liquid_in_flight_kg':branch_mass(rows,duration,'ground_liquid_mass_flow_kg_s',t)-pulse_mass(ground_pulses,t),
             'outside_domain_inventory_nonzero':outside>max(1e-8,emitted*1e-6)}
        cloud.append(row);cloud_at[t]=(row,receptor_c)
        for i,c in enumerate(receptor_c):rec_history[i].append({'time_s':t,'h2_mole_fraction':float(c),'h2_volume_percent':float(c)*100})
    mark('cloud_observation',start)
    # Physical fire radiation -> left-held dose -> TNO thermal probit.
    start=time.perf_counter();fire=module('fire',roots['tno']);risk=module('risk',roots['tno']);ignmod=module('ignition',roots['tno']);damage=module('damage',roots['tno'])
    ignition=p['ignition'];td=ignition['delayed_time_s'];burn=ignition['burn_back_duration_s']
    ign_cloud,ign_c=cloud_at[td]
    fm=ign_cloud['flammable_mass_in_domain_kg'];cloud_centre=np.asarray(ign_cloud['flammable_centroid_enu_m'])
    r03,r01=ignmod.multi_energy_radii(fm*fire.H2_HEAT_OF_COMBUSTION,ignition['obstructed_energy_fraction'])
    prob=p['ignition'];pd=prob['direct_probability'];pl=(1-pd)*prob['delayed_probability_given_no_direct'];px=pl*prob['explosion_probability_given_delayed']
    branch_probs={'direct_fire':pd,'delayed_flash_fire':pl-px,'delayed_explosion':px,
                  'no_ignition':(1-pd)*(1-prob['delayed_probability_given_no_direct'])}
    if not math.isclose(sum(branch_probs.values()),1,abs_tol=1e-10):raise ValueError('ignition probabilities do not close')
    def held(rows,t):
        return next((r for r,e in intervals(rows,duration) if r['time_s']<=t<e),None)
    def pool_rate(t):
        return sum(pack['mass']/(pack['end']-pack['start']) for pack in pool_packets if pack['start']<=t<pack['end'])
    weights=np.asarray(fire.weights_hankinson(25))
    def flux_at(pos,t,xrad):
        row=held(rows,t);flux=0.;contact=False
        if row and row['gas_mass_flow_kg_s']>0:
            rate=row['gas_mass_flow_kg_s']
            # Geometry from actual/fictitious source; do not reconstruct a
            # second notional nozzle with an incompatible energy closure.
            nozzle=row['fictitious_nozzle'] or row['real_nozzle']
            diameter=nozzle.get('diameter_m',source['nozzle']['diameter_m'])
            n=fire.NotionalNozzle(diameter,nozzle['velocity_m_s'],nozzle['density_kg_m3'],nozzle['temperature_k'],diameter/source['nozzle']['diameter_m'])
            fr=fire.flame_froude(n)
            if fr<float(fire.FR_TRANSITION):
                lstar=float(fire.C_FLAME_LOW)*fr**float(fire.C_FLAME_EXP)/(1+float(fire.C_FLAME_DAMP)*fr**2)**.2
            else:lstar=float(fire.C_FLAME_HIGH)
            length=lstar*diameter*math.sqrt(n.density_kg_m3/rho_air)/fire.H2_STOICH_MASS_FRACTION
            s=length*(np.arange(25)+.5)/25
            points=origin[None,:]+s[:,None]*direction[None,:]
            # Declared geometric deflection after flat-ground intersection.
            if direction[2]<0:
                hit=origin[2]/(-direction[2]);after=s>hit
                hdir=direction.copy();hdir[2]=0.;hdir/=np.linalg.norm(hdir)
                points[after]=origin+hit*direction+(s[after]-hit)[:,None]*hdir
            distances=np.linalg.norm(points-pos,axis=1)
            contact=bool(np.any(distances<float(fire.FLAME_RADIUS_RATIO)*length))
            flux+=float(sum(w*xrad*rate*fire.H2_HEAT_OF_COMBUSTION*fire.transmissivity(max(float(d),1e-3),weather['relative_humidity'],ambient['temperature_k'])/(4*math.pi*max(float(d),1e-3)**2) for w,d in zip(weights,distances)))
        evaporation=pool_rate(t)
        if evaporation>0:
            radius=max((r['reported_radius_m'] for r in pool['ledger'] if r['time_s']<=t),default=0.)
            d=float(np.linalg.norm(pos-pool_origin));contact |= d<=radius
            flux+=xrad*evaporation*fire.H2_HEAT_OF_COMBUSTION*fire.transmissivity(max(d,1e-3),weather['relative_humidity'],ambient['temperature_k'])/(4*math.pi*max(d,radius,1e-3)**2)
        return flux,contact
    result_receptors=[]
    # Include every physical discontinuity; no loss of thermal dose at stop.
    heat_clock=sorted(set([0.,horizon,duration,td,td+burn]+[r['time_s'] for r in rows]+[r['time_s'] for r in pool['ledger']] if pool else [0.,horizon,duration,td,td+burn]+[r['time_s'] for r in rows]))
    for i,receptor in enumerate(receptors):
        pos=np.asarray(receptor['position_enu_m'],float)
        qdirect=[];qdelayed=[];direct_results=[];delay_results=[]
        flash=damage.flash_fire(float(ign_c[i]>=.04)).pe if fm>0 else 0.
        distance=float(np.linalg.norm(pos-cloud_centre))
        if fm>0 and distance<=r03:
            band='>=0.3 barg';blast_damage=damage.overpressure(.3)
        elif fm>0 and distance<=r01:
            band='0.1 to 0.3 barg';blast_damage=damage.overpressure(.1)
        else:band='<0.1 barg';blast_damage=damage.overpressure(0.)
        for xrad in p['radiative_fraction_range']:
            direct=[];delayed=[]
            for t in heat_clock:
                q,contact=flux_at(pos,t,xrad)
                direct.append({'time_s':t,'flux_w_m2':q,'flame_contact':contact})
                q2,contact2=(q,contact) if t>=td else (0.,False)
                if td<=t<td+burn and fm>0:
                    q2+=xrad*fm*fire.H2_HEAT_OF_COMBUSTION/burn*fire.transmissivity(max(distance,1e-3),weather['relative_humidity'],ambient['temperature_k'])/(4*math.pi*max(distance,p['domain']['cell_size_m']/2)**2)
                delayed.append({'time_s':t,'flux_w_m2':q2,'flame_contact':contact2})
            # Purple Book shelter cap is applied on each event's own clock.
            direct_result=dose_harm(direct,min(20.,horizon),risk)
            delay_window=[r for r in delayed if r['time_s']>=td]
            delayed_result=dose_harm(delay_window,min(td+20.,horizon),risk)
            direct_results.append(direct_result);delay_results.append(delayed_result)
            qdirect.append(direct);qdelayed.append(delayed)
        combined=[];branch_harm=[]
        for a,b in zip(direct_results,delay_results):
            # Same initial cloud cannot supply both explosion energy and a
            # second full-cloud burn-back energy. Blast branch uses the
            # residual source fire only plus the Frechet union upper bound.
            residual=[{**r,'flux_w_m2':r['flux_w_m2']} for r in qdirect[len(combined)] if r['time_s']>=td]
            residual_harm=dose_harm(residual,min(td+20.,horizon),risk)['harm_probability']
            h={'direct_fire':a['harm_probability'],
               'delayed_flash_fire':weighted_union_harm(flash,b['harm_probability']),
               'delayed_explosion':weighted_union_harm(flash,blast_damage.pe,residual_harm),'no_ignition':0.}
            branch_harm.append(h);combined.append(sum(branch_probs[k]*h[k] for k in branch_probs))
        occupancy=p['occupancy_probability'];frequency=p['annual_frequency_per_year'];intensity=p['initiation_intensity_per_s']
        future_risk=None
        if intensity is not None:
            future_risk=[]
            for index in range(2):
                total=0.
                for a,b in zip(times,times[1:]):
                    remaining=horizon-a
                    direct=dose_harm(qdirect[index],min(20.,remaining),risk)['harm_probability']
                    delayed=blast=0.
                    if remaining>td:
                        samples=[r for r in qdelayed[index] if r['time_s']>=td]
                        delayed=weighted_union_harm(flash,dose_harm(samples,min(td+20.,remaining),risk)['harm_probability'])
                        residual=[r for r in qdirect[index] if r['time_s']>=td]
                        blast=weighted_union_harm(flash,blast_damage.pe,dose_harm(residual,min(td+20.,remaining),risk)['harm_probability'])
                    conditional=branch_probs['direct_fire']*direct+branch_probs['delayed_flash_fire']*delayed+branch_probs['delayed_explosion']*blast
                    # First-event probability on disjoint initiation intervals;
                    # consequence horizon is shortened by the initiation clock.
                    total+=math.exp(-intensity*a)*(-math.expm1(-intensity*(b-a)))*conditional
                future_risk.append(total*occupancy)
        result_receptors.append({'id':receptor['id'],'position_enu_m':receptor['position_enu_m'],
            'concentration_history':rec_history[i], 'thermal_flux_direct_low_high':qdirect,
            'thermal_flux_delayed_flash_low_high':qdelayed,'thermal_direct_low_high':direct_results,
            'thermal_delayed_low_high':delay_results,'flash_fire_envelope_harm':flash,
            'explosion_overpressure_band':band,'blast_individual_harm':blast_damage.pe,
            'blast_indoor_fraction_of_deaths':blast_damage.fe_in,
            'branch_harm_low_high':branch_harm,'harm_given_observed_release_low_high':combined,
            'annual_current_weather_contribution_low_high':None if frequency is None else [frequency*x*occupancy for x in combined],
            'first_initiation_harm_probability_low_high':future_risk})
    mark('fire_explosion_damage_risk',start)
    gas_mass=branch_mass(rows,duration,'gas_mass_flow_kg_s');ground_mass=branch_mass(rows,duration,'ground_liquid_mass_flow_kg_s')
    last_pool=pool['ledger'][-1] if pool else None
    evaporated=last_pool['cumulative_evaporation_kg'] if pool else 0.
    liquid=last_pool['liquid_mass_kg'] if pool else 0.
    escape=last_pool['escaped_domain_mass_kg'] if pool else 0.
    adjustment=last_pool['cumulative_numerical_mass_adjustment_kg'] if pool else 0.
    ground_in_flight=ground_mass-pulse_mass(ground_pulses,horizon)
    residual=mass+adjustment-gas_mass-evaporated-liquid-escape-ground_in_flight
    if abs(residual)>max(1e-8,mass*1e-8):raise ValueError('end-to-end hydrogen mass ledger failed')
    return {'data':{
        'status':'END_TO_END_DIAGNOSTIC_EXECUTED','full_chain_executed':True,
        'physical_validation_claim':False,'facility_validation':'WITHHELD','realtime_requirement_demonstrated':False,
            'stages':['equipment_resolved_liquid_two_phase_exit' if resolved_liquid is not None else
                      'equipment_resolved_gas_exit' if resolved is not None else 'integrated_release',
                  'rainout_and_dynamic_pool','vector_cryogenic_near_field','SLABx_dispersion',
                  'finite_inventory_cloud','ignition_branches','fire_radiation','multi_energy_blast_zones','TNO_human_damage','conditional_risk'],
        'source':source_history,'pool':pool,'ground_arrival_pulses':ground_pulses,
        'source_operator':source_operator,
        'operator_limited':bool(source_history.get('operator_limited',False) or vertical_handoff is not None),
        'source_ownership':{'state_owner':'equipment_twin' if equipment_resolved else 'integrated_source',
            'discharge_owner':'equipment_twin' if equipment_resolved else 'integrated_source',
            'discharge_recalculated':not equipment_resolved},
        'handoffs':traces,'cloud_history_unignited_counterfactual':cloud,
        'ignition_branch_probabilities':branch_probs,
        'explosion':{'ignition_time_s':td,'flammable_mass_in_domain_kg':fm,'cloud_centroid_enu_m':cloud_centre.tolist(),
             'combustion_energy_j':fm*fire.H2_HEAT_OF_COMBUSTION,'obstructed_energy_fraction':ignition['obstructed_energy_fraction'],
             'radius_0_3_barg_m':r03,'radius_0_1_barg_m':r01,'model':'TNO multi-energy strength-10 anchor zones; deflagration only',
             'outside_domain_h2_kg_at_ignition':ign_cloud['hydrogen_outside_domain_kg'],
             'domain_truncated':ign_cloud['outside_domain_inventory_nonzero']},
        'mass_ledger':{'released_kg':mass,'direct_gas_kg':gas_mass,'ground_inflow_kg':ground_mass,
            'pool_evaporated_kg':evaporated,'pool_remaining_kg':liquid,'pool_domain_escape_kg':escape,
            'ground_liquid_in_flight_kg':ground_in_flight,
            'pool_numerical_adjustment_kg':adjustment,'end_to_end_residual_kg':residual},
        'receptors':result_receptors,'stage_elapsed_ms':timings,
        'risk_semantics':{'observed_release':'conditional harm, no initiating-frequency multiplier',
            'annual':'single initiating event under current weather; not weather-integrated total annual IR',
            'initiation':'constant supplied hazard; disjoint first-event intervals; remaining consequence horizon; interval-left consequence approximation',
            'effect_combination':'Frechet union upper bound min(1,sum(harm)) within one event branch; no independence assumed'},
        'limitations':[
            'If resolved gas equipment input is selected: horizontal atmospheric gas plane at Mach <=0.3; PH/continuity/static enthalpy checked, provider kinetic-energy closure is not certified.',
            'If resolved liquid/two-phase equipment input is selected: provider flash, gas/ground partition and total enthalpy are consumed; airborne liquid and provider flash/droplet physics remain outside this route.',
            'Outdoor flat ground, non-calm wind, horizontal nozzle or provider-resolved vertical handoff, known leak geometry only.',
            'A vertical provider exit is accepted only with a declared horizontal handoff section; the handoff is operator-limited and is not a PRISM rotation or independent vertical-jet validation.',
            'Ground deposition uses resolved per-class flight delays; distributed in-flight vapour generation is still collapsed to the terminal gas boundary at release time.',
            'The gas branch enters a gas-only vector/cryogenic transition; nozzle vertical momentum is represented in fire geometry but not in this transition.',
            'Rainout footprint is explicitly declared; it is not inferred from a single impact point or fitted to LFL/sensors.',
            'Finite-volume top-hat reconstruction of native section averages; not the frozen seven-test FFI observation operator or independent transient validation.',
            'Superposed carrier packets preserve H2 mass but overlapping air/temperature/pressure equilibration remains open.',
            'Ignition probabilities, burn-back duration, radiation range and obstruction fraction are declared scenario inputs.',
            'Fire does not feed heat back into the unignited pool evaporation model; ground flame deflection is a geometric approximation.',
            'Quasi-steady flame geometry is used for short releases; flame establishment and propagation are unresolved.',
            'Radiation uses the explicitly supplied fraction range; unexplained legacy Molina factor 22.7 is not used.',
            'Blast uses two TNO anchor zones, not a continuous pressure/impulse curve; detonation and DDT unsupported.',
            'Gas outside the configured spatial domain is explicitly ledgered; its flammable contribution and blast harm are uncomputed.',
            'Hydrogen source mass accounting closes; total source-to-cloud energy closure and facility calibration are unqualified.',
            'Numerical connection and timing measurements do not establish IJHE validation or 1-Hz fresh-physics capability.'
        ]},'limitation':'Executable complete diagnostic chain within declared assumptions; engineering/facility validation remains withheld.'}
