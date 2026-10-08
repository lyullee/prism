"""Test a real equipment-network outlet as a prospective consequence boundary."""
from pathlib import Path
from dataclasses import asdict
import json,sys
ROOT=Path(__file__).resolve().parents[1]
MODEL=Path(r'C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\06_액화수소_디지털트윈_물리모델')
OUT=ROOT/'results/20261008/equipment_coupling_review'
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import tree_digest
before=tree_digest(MODEL/'src/lh2dt')
sys.path.insert(0,str(MODEL/'src'))
from lh2dt import HydrogenProperties,VentStack
from lh2dt.network import SteadyNetwork
import lh2dt
assert Path(lh2dt.__file__).resolve().is_relative_to(MODEL/'src/lh2dt')

props=HydrogenProperties('ParaHydrogen')
left=props.from_pT(400000.,150.)
right=props.from_pT(101325.,288.15)
stack=VentStack(length_m=6.,inner_diameter_m=.0254,roughness_m=1.5e-6,
    local_loss_coefficient=2.,elevation_change_m=6.,ambient_temperature_K=288.15,
    ambient_UA_W_K=5.,properties=props,integration_segments=64)
network=SteadyNetwork(props)
network.add_boundary('UPSTREAM',left);network.add_boundary('ATMOSPHERE',right)
network.add_link('VENT_OUTLET','UPSTREAM','ATMOSPHERE',stack,
    source_port_id='UPSTREAM.gas',target_port_id='ATMOSPHERE.in')
solved=network.solve()
assert solved.pressure_solver_success
flow=solved.link_flows['VENT_OUTLET']
assert flow.mass_flow_kg_s>0
outlet=props.from_ph(right.pressure_Pa,flow.transmitted_specific_enthalpy_J_kg)
native=stack.evaluate(left,right)
energy_residual=flow.mass_flow_kg_s*(outlet.specific_enthalpy_J_kg-left.specific_enthalpy_J_kg)-native.heat_into_fluid_W
assert abs(energy_residual)<1e-6
after=tree_digest(MODEL/'src/lh2dt')
if before!=after:raise RuntimeError('provider source changed during probe; do not retain an unpinned result')

packet={'schema_version':'proposed-equipment-boundary-v1','status':'boundary_export_demonstrated',
    'boundary_kind':'resolved_atmospheric_outlet','event_kind':'normal_vent',
    'input_origin':'synthetic','physical_validation_claim':False,'time_s':0.,
    'component_id':'VENT_OUTLET','source_port_id':flow.source_port_id,'target_port_id':flow.target_port_id,
    'state_owner':'equipment_twin','discharge_owner':'equipment_twin',
    'property_basis':{'fluid':props.fluid,'backend':'CoolProp-HEOS','energy_reference':f'CoolProp-HEOS:{props.fluid}:native'},
    'mass_flow_kg_s':flow.mass_flow_kg_s,'thermo_state':asdict(outlet),
    'ambient_pressure_pa':right.pressure_Pa,'velocity_m_s':None,'effective_area_m2':None,
    'position_enu_m':None,'direction_enu':None,'flow_partition':None,
    'provider_source_digest':before,'network_solution':asdict(solved),
    'heat_into_fluid_w':native.heat_into_fluid_W,'energy_residual_w':energy_residual,
    'current_consequence_chain_ready':False,
    'missing_for_current_chain':['resolved-flow input path instead of a second discharge calculation',
        'explicit outlet geometry, direction, area/velocity and receptor coordinates',
        'phase-aware gas/cryogenic outlet routing; vertical stack adapter',
        'shared fluid basis, including ParaHydrogen-compatible pool if rainout exists']}
(OUT/'actual_network_outlet_probe.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps({'mass_flow_kg_s':flow.mass_flow_kg_s,'outlet_temperature_k':outlet.temperature_K,
    'atmospheric_boundary_temperature_k':right.temperature_K,'upstream_temperature_k':left.temperature_K,
    'energy_residual_w':energy_residual,'provider_source_unchanged':before==after,
    'current_consequence_chain_ready':False},ensure_ascii=False,indent=2))
