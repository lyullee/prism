"""JSON worker. The calling process alone supplies explicit source pins."""
from __future__ import annotations
from dataclasses import asdict
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys


def module(name, root):
    mod=importlib.import_module(name)
    if not Path(mod.__file__).resolve().is_relative_to(root):
        raise ValueError(f"unexpected import origin: {name}")
    return mod


def run(request):
    for name,version in request["required_versions"].items():
        if importlib.metadata.version(name)!=version:
            raise ValueError(f"dependency version mismatch: {name}")
    roots={p["name"]:Path(p["root"]).resolve() for p in request["packages"]}
    # Preserve declared precedence. Putting site-packages first would hide a
    # pinned standalone source tree behind another installed pool version.
    for name,root in reversed(tuple(roots.items())):
        sys.path.insert(0,str(root if name=="tno" else root.parent))
    p=request["payload"]; operation=request["operation"]
    if operation=="consequence_chain":
        from chain_worker import run_chain
        return run_chain(p,roots,module)
    if operation=='facility_risk_aggregate':
        m=module('risk',roots['tno'])
        ids=p['receptor_ids']; atoms=p['atoms']
        ir={rid:[] for rid in ids}; curves=[]
        for index in range(2):
            for rid in ids:
                contributions=[m.RiskContribution(loc_id=a['event_id'],weather_class=a['annual_condition_id'],
                    sector_deg=(0.,360.),ignition_event=a['ignition_branch'],pm_pphi=a['conditional_weight'],
                    p_ignition=1.,p_death=a['receptor_harm_low_high'][rid][index],
                    frequency_per_year=a['initiating_frequency_per_year'],route=m.PdRoute.FLAMMABLE) for a in atoms]
                ir[rid].append(m.total_individual_risk(contributions))
            outcomes=[m.SocietalOutcome(frequency_per_year=a['initiating_frequency_per_year']*a['conditional_weight'],
                n_deaths=a['expected_deaths_low_high'][index]) for a in atoms]
            ns,fs=m.fn_curve(outcomes)
            curves.append({'expected_deaths':ns.tolist(),'cumulative_frequency_per_year':fs.tolist()})
        return {'data':{'ir_low_high':ir,'fn_low_high':curves},
            'limitation':'Native legacy risk.total_individual_risk and risk.fn_curve; expected-death convention; external physics/coverage must be checked separately.'}
    if operation=="integrated_source":
        m=module("slabx_lh2.integrated_lh2_source",roots["slabx_lh2"])
        duration=p["duration_s"]; dt=p["time_step_s"]
        if not 0<dt<=duration<=3600 or duration/dt>2000:
            raise ValueError("invalid source horizon or computation budget")
        inp=m.IntegratedSourceInput(m.TankState(**p["tank"]),tuple(m.PipeSection(**x) for x in p["pipe_sections"]),
              m.NozzleGeometry(**p["nozzle"]),m.AmbientState(**p["ambient"]),m.ModelChoices(**p["choices"]),duration,dt)
        data=asdict(m.evaluate_integrated_lh2_source(inp))
        data['requested_duration_s']=duration
        data['returned_history_duration_s']=(len(data['steps'])*dt if data['steps'] else 0.0)
        # These residuals are latent-evaporation accounting, not total-energy closure.
        return {"data":data,"energy_balance_scope":"latent_evaporation_accounting_only",
                "limitation":"upstream transient/source model assumptions retained; downstream dispersion not computed"}
    if operation=="liquid_jet_source":
        m=module("slabx_lh2.lh2_jet_source",roots["slabx_lh2"])
        from inventory_source import _json_safe
        spray=p["liquid_jet"]
        history=m.evaluate_liquid_jet(
            m.StorageState(pressure_pa=p["tank"]["pressure_pa"],
                temperature_k=p["tank"]["temperature_k"],
                discharge_coefficient=spray["discharge_coefficient"],
                fluid=p["tank"]["fluid"]),
            m.Nozzle(diameter_m=p["nozzle"]["diameter_m"],
                height_m=p["nozzle"]["height_m"],
                direction=tuple(p["nozzle"]["direction_enu"])),
            m.Environment(pressure_pa=p["ambient"]["pressure_pa"],
                temperature_k=p["ambient"]["temperature_k"],
                wind_speed_m_s=p["ambient"]["wind_speed_m_s"],
                wind_from_bearing_deg=p["ambient"]["wind_from_bearing_deg"]),
            p["duration_s"], time_step_s=p["time_step_s"],
            spray=m.SprayAssumptions(
                droplet_diameter_m=spray["droplet_diameter_m"],
                d2_evaporation_constant_m2_s=spray["d2_evaporation_constant_m2_s"],
                spray_half_angle_deg=spray["spray_half_angle_deg"],
                liquid_velocity_fraction=spray["liquid_velocity_fraction"]))
        return {"data":_json_safe(asdict(history)),
                "limitation":"constant upstream liquid-jet source; no tank inventory feedback; declared spray evaporation energy is open"}
    if operation=="vent_stack":
        props=module("lh2dt.properties",roots["lh2dt"])
        m=module("lh2dt.vent_stack",roots["lh2dt"])
        fluid=props.HydrogenProperties(p["fluid"])
        left=fluid.from_pT(**p["upstream"]); right=fluid.from_pT(**p["downstream"])
        stack=m.VentStack(**p["stack"],properties=fluid)
        hydraulic=stack.evaluate(left,right)
        outlet=fluid.from_ph(right.pressure_Pa,hydraulic.outlet_specific_enthalpy_J_kg)
        residual=hydraulic.mass_flow_kg_s*(outlet.specific_enthalpy_J_kg-left.specific_enthalpy_J_kg)-hydraulic.heat_into_fluid_W
        return {"data":{"hydraulic":asdict(hydraulic),"outlet":asdict(outlet),"energy_residual_w":residual},
                "limitation":"steady stack component; tank/PSV transient not computed"}
    if operation=="equipment_network_exit":
        props=module('lh2dt.properties',roots['lh2dt'])
        component=module('lh2dt.vent_stack',roots['lh2dt'])
        networkmod=module('lh2dt.network',roots['lh2dt'])
        fluid=props.HydrogenProperties(p['fluid'])
        # Explicit PH boundaries: saturation is never resolved by a T offset.
        def state(row):return fluid.from_ph(row['pressure_pa_abs'],row['specific_enthalpy_j_kg'])
        left=state(p['upstream']);right=state(p['downstream'])
        stack=component.VentStack(**p['stack'],properties=fluid)
        network=networkmod.SteadyNetwork(fluid)
        network.add_boundary('UPSTREAM',left);network.add_boundary('ATMOSPHERE',right)
        network.add_link(p['provider_link_id'],'UPSTREAM','ATMOSPHERE',stack,
            source_port_id='UPSTREAM.gas',target_port_id='ATMOSPHERE.in')
        solution=network.solve()
        if not solution.pressure_solver_success:raise ValueError('equipment network pressure solution failed')
        flow=solution.link_flows[p['provider_link_id']]
        if flow.mass_flow_kg_s<0:raise ValueError('outward release export requires outward resolved flow')
        outlet=fluid.from_ph(right.pressure_Pa,flow.transmitted_specific_enthalpy_J_kg)
        native=stack.evaluate(left,right)
        area=math.pi*stack.diameter**2/4
        velocity=flow.mass_flow_kg_s/(outlet.density_kg_m3*area)
        return {'data':{'flow':asdict(flow),'outlet':asdict(outlet),'hydraulic':asdict(native),
                'effective_area_m2':area,'velocity_m_s':velocity,
                'velocity_origin':'mass_continuity_from_declared_area',
                'upstream':asdict(left),'downstream':asdict(right),
                'state_owner':'equipment_twin','discharge_owner':'equipment_twin',
                'static_enthalpy_transport_only':True},
                'limitation':'Native steady VentStack/SteadyNetwork PH export. Terminal area is declared stack bore; velocity derived by continuity. Total kinetic-energy closure and transient feedback are not qualified.'}
    if operation=="equipment_dynamic_isolation":
        # The provider owns the transient tank, valve command, network flow,
        # and mass/energy ledger.  PRISM receives interval-start gas-boundary
        # rows; it does not re-solve the tank or infer a valve response.
        props=module('lh2dt.properties',roots['lh2dt'])
        geometrymod=module('lh2dt.geometry',roots['lh2dt'])
        tankmod=module('lh2dt.layered_tank',roots['lh2dt'])
        networkmod=module('lh2dt.network',roots['lh2dt'])
        valvemod=module('lh2dt.valve',roots['lh2dt'])
        layered_network=module('lh2dt.layered_network',roots['lh2dt'])
        fluid=props.HydrogenProperties(p.get('fluid','ParaHydrogen'))
        duration=float(p['duration_s']); dt=float(p['time_step_s'])
        if not math.isfinite(duration) or not math.isfinite(dt) or not 0.0<dt<=duration<=10.0:
            raise ValueError('dynamic isolation duration/time step outside bounded scope')
        if math.ceil(duration/dt)>100:
            raise ValueError('dynamic isolation history exceeds 100 provider intervals')
        geometry=geometrymod.HorizontalVesselGeometry(**p['geometry'])
        parameters=tankmod.LayeredTankParameters(**p['tank_parameters'])
        if parameters.vapor_cell_count<2:
            raise ValueError('dynamic isolation requires a mapped second vapor cell')
        tank=tankmod.LayeredTank(geometry,parameters,fluid)
        initial_cfg=p['initial']
        saturated=tank.initialize_saturated(float(initial_cfg['pressure_pa']),float(initial_cfg['liquid_fraction']))
        vapor_offset=float(initial_cfg.get('vapor_enthalpy_offset_j_kg',0.0))
        initial=tank.project_pressure(tankmod.LayeredTankState(
            saturated.pressure_Pa,
            saturated.liquid_masses_kg,
            saturated.liquid_specific_enthalpies_J_kg,
            saturated.vapor_masses_kg,
            tuple(value+vapor_offset for value in saturated.vapor_specific_enthalpies_J_kg),
            saturated.wall_temperatures_K,
        ))
        thermo=tank.thermo(initial)
        ambient=p['ambient']
        sink=fluid.from_pT(float(ambient['pressure_pa']),float(ambient['temperature_k']))
        network=networkmod.SteadyNetwork(fluid)
        network.add_boundary('vapor_port',thermo.vapor[1])
        network.add_boundary('ambient_sink',sink)
        valve_cfg=p['valve']
        valve=valvemod.CommandedValve(valvemod.Valve(
            float(valve_cfg['full_open_area_m2']),
            float(valve_cfg['discharge_coefficient']),
            fluid,
            pressure_samples=int(valve_cfg.get('pressure_samples',16)),
            allow_reverse=bool(valve_cfg.get('allow_reverse',False)),
            closed_leakage_CdA_m2=float(valve_cfg.get('closed_leakage_CdA_m2',0.0)),
        ))
        network.add_link('isolation_valve','vapor_port','ambient_sink',valve,
            source_port_id='TANK:V1',target_port_id='ATMOSPHERE:IN')
        isolation_cfg=p['isolation']
        outcome=isolation_cfg.get('outcome','success')
        if outcome not in {'success','failure'}:
            raise ValueError('isolation outcome must be success or failure')
        close_time=float(isolation_cfg['close_time_s'])
        if outcome=='success' and (not math.isfinite(close_time) or not 0.0<close_time<duration):
            raise ValueError('successful close_time_s must lie strictly inside the simulation horizon')
        if outcome=='failure' and (not math.isfinite(close_time) or close_time<duration):
            raise ValueError('failed isolation close_time_s must be at or beyond the simulation horizon')
        def command(time_s, _network):
            valve.set_opening(1.0 if time_s<close_time else 0.0)
        simulator=layered_network.LayeredTankNetworkSimulator(
            tank,network,
            ports=(layered_network.LayeredTankPort('vapor_port','vapor',1),),
            ambient_temperature_K=float(ambient.get('wall_ambient_temperature_k',20.0)),
            command_callback=command,
        )
        results=simulator.simulate(initial,duration_s=duration,time_step_s=dt)
        if not results:
            raise ValueError('dynamic isolation provider returned no intervals')
        # ``simulate`` returns the state at the end of each interval.  Resolve
        # one explicit t=0 network state so the exported history is left-held
        # and the commanded closure is represented at the correct boundary.
        network.set_boundary_state('vapor_port',tank.thermo(initial).vapor[1])
        command(0.0,network)
        previous_solution=network.solve()
        if not previous_solution.pressure_solver_success:
            raise ValueError('dynamic isolation initial network solve failed')
        valve_area=float(valve_cfg['full_open_area_m2'])
        area=valve_area
        rows=[]; cumulative_mass=0.0; cumulative_h=0.0
        mass_residual=[]; energy_residual=[]
        for result in results:
            flow=previous_solution.link_flows['isolation_valve']
            previous_solution=result.network_solution
            if flow.mass_flow_kg_s < -1.0e-12:
                raise ValueError('dynamic isolation export requires outward nonnegative flow')
            flow_rate=max(0.0,float(flow.mass_flow_kg_s))
            outlet=fluid.from_ph(sink.pressure_Pa,float(flow.transmitted_specific_enthalpy_J_kg))
            velocity=0.0 if flow_rate==0.0 else flow_rate/(outlet.density_kg_m3*area)
            interval_start=max(0.0,float(result.tank.time_s)-dt)
            rows.append({
                'time_s':interval_start,
                'mass_flow_kg_s':flow_rate,
                'pressure_pa_abs':outlet.pressure_Pa,
                'specific_enthalpy_j_kg':outlet.specific_enthalpy_J_kg,
                'temperature_k':outlet.temperature_K,
                'density_kg_m3':outlet.density_kg_m3,
                'effective_area_m2':area,
                'velocity_m_s':velocity,
                'upstream_pressure_pa_abs':result.tank.thermo.vapor[1].pressure_Pa,
                'upstream_temperature_k':result.tank.thermo.vapor[1].temperature_K,
                'valve_opening':1.0 if interval_start<close_time else 0.0,
            })
            cumulative_mass += flow_rate*dt
            cumulative_h += flow_rate*outlet.specific_enthalpy_J_kg*dt
            mass_residual.append(abs(float(result.tank.total_mass_residual_kg)))
            energy_residual.append(abs(float(result.tank.total_energy_residual_J)))
        if rows[0]['time_s']!=0.0 or rows[-1]['time_s']>=duration:
            raise ValueError('dynamic isolation provider clock does not cover left-held intervals')
        pre=[row['mass_flow_kg_s'] for row in rows if row['time_s']<close_time]
        post=[row['mass_flow_kg_s'] for row in rows if row['time_s']>=close_time]
        post_max=max(post) if post else None
        closure_confirmed=(outcome=='success' and post_max is not None and
                           post_max<=1.0e-14 and
                           float(valve_cfg.get('closed_leakage_CdA_m2',0.0))==0.0)
        return {'data':{
            'event_kind':'accidental_leak',
            'fluid':fluid.fluid,
            'steps':rows,
            'duration_s':duration,
            'time_step_s':dt,
            'available_mass_kg':sum(initial.liquid_masses_kg)+sum(initial.vapor_masses_kg),
            'cumulative_mass_out_kg':cumulative_mass,
            'cumulative_static_enthalpy_out_j':cumulative_h,
            'close_time_s':close_time,
            'pre_close_max_flow_kg_s':max(pre,default=0.0),
            'post_close_max_flow_kg_s':post_max,
            'post_close_observation_available':bool(post),
            'isolation_flow_zero_confirmed':closure_confirmed,
            'max_total_mass_residual_kg':max(mass_residual,default=0.0),
            'max_total_energy_residual_j':max(energy_residual,default=0.0),
            'provider_terminal_area_m2':area,
            'provider_valve_area_m2':valve_area,
            'provider_link_id':'isolation_valve',
            'state_owner':'equipment_twin',
            'discharge_owner':'equipment_twin',
            'isolation_outcome':outcome,
            'termination_basis':'reviewed_isolation_success' if closure_confirmed else 'synthetic_diagnostic_horizon',
        },'limitation':'Transient layered-tank/commanded-valve provider path with synthetic geometry and an explicit isolation command. Closure is qualified only for the supplied command and zero closed-seat leakage; no plant actuator delay, failure-on-demand probability, or two-phase liquid release is inferred.'}
    if operation=="equipment_dynamic_inventory":
        # A provider-owned homogeneous finite-storage path.  The adapter runs
        # one bounded provider interval at a time and stops at an explicit
        # positive-mass threshold; it never writes a zero-mass state into the
        # external model or extrapolates the final flow.
        props=module('lh2dt.properties',roots['lh2dt'])
        tankmod=module('lh2dt.tank',roots['lh2dt'])
        networkmod=module('lh2dt.network',roots['lh2dt'])
        valvemod=module('lh2dt.valve',roots['lh2dt'])
        dynamicmod=module('lh2dt.dynamic_network',roots['lh2dt'])
        fluid=props.HydrogenProperties(p.get('fluid','ParaHydrogen'))
        duration=float(p['duration_s']); dt=float(p['time_step_s'])
        if not math.isfinite(duration) or not math.isfinite(dt) or not 0.0<dt<=duration<=120.0:
            raise ValueError('dynamic inventory duration/time step outside bounded scope')
        if math.ceil(duration/dt)>100:
            raise ValueError('dynamic inventory history exceeds 100 provider intervals')
        geometry=tankmod.TankGeometry(**p['tank_geometry'])
        tank=tankmod.HomogeneousTank(geometry,fluid)
        initial_cfg=p['initial']
        saturated=tank.initialize_saturated(float(initial_cfg['pressure_pa']),float(initial_cfg['liquid_fraction']))
        energy_offset=float(initial_cfg.get('hydrogen_internal_energy_offset_j_kg',0.0))
        if not math.isfinite(energy_offset):
            raise ValueError('hydrogen_internal_energy_offset_j_kg must be finite')
        initial=tankmod.TankState(
            saturated.hydrogen_mass_kg,
            saturated.hydrogen_internal_energy_J+saturated.hydrogen_mass_kg*energy_offset,
            saturated.wall_temperature_K,
        )
        initial_mass=float(initial.hydrogen_mass_kg)
        threshold=float(p['depletion']['threshold_mass_kg'])
        if not math.isfinite(threshold) or threshold<=0.0 or threshold>=initial_mass:
            raise ValueError('depletion threshold must be positive and below the initial inventory')
        ambient=p['ambient']
        sink=fluid.from_pT(float(ambient['pressure_pa']),float(ambient['temperature_k']))
        valve_cfg=p['valve']
        valve_area=float(valve_cfg['full_open_area_m2'])
        if not math.isfinite(valve_area) or valve_area<=0.0:
            raise ValueError('inventory valve area must be finite and positive')
        elapsed=0.0; state=initial; rows=[]; cumulative_mass=0.0; cumulative_h=0.0
        mass_residual=[]; energy_residual=[]; provider_intervals=0
        initial_total_energy=state.hydrogen_internal_energy_J+geometry.wall_heat_capacity_J_K*state.wall_temperature_K
        while elapsed < duration-1e-12 and state.hydrogen_mass_kg>threshold:
            remaining=duration-elapsed
            step=min(dt,remaining)
            if len(rows)>=100:
                raise ValueError('inventory provider row budget exceeded before depletion')
            last_error=None
            for _attempt in range(8):
                network=networkmod.SteadyNetwork(fluid)
                network.add_boundary('tank',tank.thermo(state))
                network.add_boundary('ambient_sink',sink)
                valve=valvemod.CommandedValve(valvemod.Valve(
                    valve_area,float(valve_cfg['discharge_coefficient']),fluid,
                    pressure_samples=int(valve_cfg.get('pressure_samples',16)),
                    allow_reverse=False,
                    closed_leakage_CdA_m2=0.0,
                ))
                network.add_link('inventory_valve','tank','ambient_sink',valve,
                    source_port_id='TANK:OUT',target_port_id='ATMOSPHERE:IN')
                def command(_time_s,_network):
                    valve.set_opening(1.0)
                network.set_boundary_state('tank',tank.thermo(state))
                command(elapsed,network)
                initial_solution=network.solve()
                if not initial_solution.pressure_solver_success:
                    raise ValueError('dynamic inventory initial network solve failed')
                simulator=dynamicmod.DynamicNetworkSimulator(
                    network,{'tank':dynamicmod.homogeneous_tank_node('tank',tank,state,20.0)},
                    command_callback=command,
                )
                try:
                    result=simulator.simulate(step,step)[-1]
                    break
                except (ValueError,RuntimeError,OverflowError) as error:
                    last_error=error
                    step*=0.5
                    if step<=dt/256.0:
                        raise
            else:
                raise ValueError(f'dynamic inventory interval failed: {last_error}')
            provider_intervals+=1
            end_state=result.states['tank']
            signed_mass=float(result.cumulative_boundary_mass_kg['tank'])
            signed_transport=float(result.cumulative_boundary_transport_energy_J['tank'])
            mass_out=-signed_mass
            energy_out=-signed_transport
            if not math.isfinite(mass_out) or mass_out< -1e-12:
                raise ValueError('dynamic inventory provider returned non-outward mass')
            mass_out=max(0.0,mass_out)
            if mass_out>1e-15:
                mean_h=energy_out/mass_out
            else:
                mean_h=float(initial_solution.link_flows['inventory_valve'].transmitted_specific_enthalpy_J_kg)
            outlet=fluid.from_ph(sink.pressure_Pa,mean_h)
            mean_rate=mass_out/step
            velocity=0.0 if mean_rate==0.0 else mean_rate/(outlet.density_kg_m3*valve_area)
            rows.append({
                'time_s':elapsed,
                'mass_flow_kg_s':mean_rate,
                'pressure_pa_abs':outlet.pressure_Pa,
                'specific_enthalpy_j_kg':outlet.specific_enthalpy_J_kg,
                'temperature_k':outlet.temperature_K,
                'density_kg_m3':outlet.density_kg_m3,
                'effective_area_m2':valve_area,
                'velocity_m_s':velocity,
                'upstream_pressure_pa_abs':tank.thermo(state).pressure_Pa,
                'upstream_temperature_k':tank.thermo(state).temperature_K,
                'interval_value_origin':'provider_interval_average_from_dynamic_network',
                'valve_opening':1.0,
            })
            previous_energy=state.hydrogen_internal_energy_J+geometry.wall_heat_capacity_J_K*state.wall_temperature_K
            current_energy=end_state.hydrogen_internal_energy_J+geometry.wall_heat_capacity_J_K*end_state.wall_temperature_K
            mass_residual.append(abs(float(end_state.hydrogen_mass_kg-state.hydrogen_mass_kg+mass_out)))
            energy_residual.append(abs(float(current_energy-previous_energy-result.cumulative_boundary_energy_J['tank'])))
            cumulative_mass+=mass_out
            cumulative_h+=energy_out
            state=end_state
            elapsed+=step
        if not rows:
            raise ValueError('dynamic inventory provider returned no intervals')
        depleted=state.hydrogen_mass_kg<=threshold
        termination='inventory_depletion' if depleted else 'synthetic_diagnostic_horizon'
        basis_provenance=(
            f'provider positive-mass depletion threshold reached; remaining inventory {state.hydrogen_mass_kg:.17g} kg'
            if depleted else
            'provider horizon ended above the declared positive-mass depletion threshold; no extrapolation'
        )
        return {'data':{
            'event_kind':'accidental_leak',
            'fluid':fluid.fluid,
            'steps':rows,
            'duration_s':elapsed,
            'requested_duration_s':duration,
            'time_step_s':dt,
            'available_mass_kg':initial_mass,
            'remaining_inventory_kg':float(state.hydrogen_mass_kg),
            'depletion_threshold_kg':threshold,
            'inventory_depletion_detected':depleted,
            'cumulative_mass_out_kg':cumulative_mass,
            'cumulative_static_enthalpy_out_j':cumulative_h,
            'max_total_mass_residual_kg':max(mass_residual,default=0.0),
            'max_total_energy_residual_j':max(energy_residual,default=0.0),
            'provider_intervals':provider_intervals,
            'provider_terminal_area_m2':valve_area,
            'provider_valve_area_m2':valve_area,
            'provider_link_id':'inventory_valve',
            'state_owner':'equipment_twin',
            'discharge_owner':'equipment_twin',
            'termination_basis':termination,
            'termination_provenance':basis_provenance,
        },'limitation':'Provider-owned homogeneous finite-storage tank and commanded full-open valve. Depletion is an explicit positive-mass numerical threshold, not a claim that the external EOS admits a zero-mass state; no liquid two-phase tank feedback or plant calibration is inferred.'}
    if operation=="declared_pool":
        m=module("dynamiclh2poolx",roots["dynamiclh2poolx"])
        if p["inflow_origin"] not in {"synthetic_declared_ground", "reviewed_ground_measurement"}:
            raise ValueError("explicit ground deposition origin required")
        times=p["output_times_s"]
        if not times or times[-1]>120 or len(times)>500:
            raise ValueError("pool computation budget exceeded")
        surface=m.SolidSemiInfiniteSurface(**p["surface"])
        numerics=m.ShallowLayerNumerics(**p["numerics"])
        inflow=m.DeclaredInflow(tuple(p["inflow_times_s"]),tuple(p["inflow_rates_kg_s"]))
        result=m.run_dynamic_pool(m.DynamicPoolConfig(surface=surface,numerics=numerics),inflow,tuple(times))
        return {"data":result.to_dict(),"limitation":"declared ground inflow only; jet deposition/footprint not inferred",
                "inflow_origin":p["inflow_origin"]}
    if operation=="assurance":
        pa=module("physics_assurance",roots["tno"]); er=module("evidence_registry",roots["tno"])
        outputs=[]
        for row in p["outputs"]:
            row=dict(row); row["status"]=pa.EvidenceStatus(row["status"])
            for name in ["evidence_ids","conditions","warnings","shared_limitations"]:
                row[name]=tuple(row.get(name,[]))
            if row.get("interval") is not None: row["interval"]=tuple(row["interval"])
            outputs.append(pa.ComponentOutput(**row))
        records=[]
        for row in p["records"]:
            row=dict(row); row["use"]=er.EvidenceUse(row["use"]); row["replay"]=er.ReplayLevel(row["replay"])
            row["maximum_status"]=pa.EvidenceStatus(row["maximum_status"])
            row["artifacts"]=tuple(er.Artifact(**x) for x in row["artifacts"])
            row["conditions"]=tuple(row.get("conditions",[]))
            records.append(er.EvidenceRecord(**row))
        result=er.assess_registered_outputs(tuple(outputs),er.EvidenceRegistry(tuple(records)))
        return {"data":asdict(result),"limitation":"metadata qualification does not establish physical accuracy"}
    if operation=="thermal_damage":
        m=module("risk",roots["tno"])
        flux=p["equivalent_heat_flux_w_m2"]; duration=p["exposure_s"]
        if not math.isfinite(flux) or flux<0 or not math.isfinite(duration) or duration<=0:
            raise ValueError("nonnegative flux and positive duration required")
        probit=None if flux==0 else m.ThermalProbit().probit(flux,duration)
        return {"data":{"harm_probability":0 if flux==0 else m.probit_to_probability(probit),"probit":probit},
                "limitation":"TNO damage transformation only; input radiation and exposure require independent validation"}
    raise ValueError("unsupported operation")


if __name__=="__main__":
    try:
        request=json.load(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr): result=run(request)
        versions={name:importlib.metadata.version(name) for name in request["required_versions"]}
        print(json.dumps({"ok":True,**result,"environment":{"python":sys.version,"dependencies":versions}},ensure_ascii=False,allow_nan=False))
    except Exception as e:
        print(json.dumps({"ok":False,"error":f"{type(e).__name__}: {e}"},ensure_ascii=False))
