import json
import pytest
from pydantic import ValidationError
from lh2_tno.contracts import Facility, PartitionStep, PropertyBasis, SourceLedger


def facility_data():
    basis={"fluid":"ParaHydrogen","energy_reference":"CoolProp-HEOS:ParaHydrogen:native"}
    return {"id":"generic","configuration_origin":"synthetic","environment":"outdoor",
            "components":[{"id":"tank","kind":"storage_tank","position_enu_m":[0,0,0],"property_basis":basis,"parameters_si":{"volume_m3":10}},
                          {"id":"valve","kind":"valve","position_enu_m":[1,0,0],"property_basis":dict(basis)}],
            "ports":[{"id":"tank.out","component_id":"tank","phase":"liquid","direction":"out"},
                     {"id":"valve.in","component_id":"valve","phase":"liquid","direction":"in"}],
            "edges":[{"id":"line","source_port":"tank.out","target_port":"valve.in"}],
            "receptors":[{"id":"person","position_enu_m":[10,0,1.8]}]}


def parse(data):return Facility.model_validate_json(json.dumps(data))


def test_roundtrip_preserves_topology_and_digest():
    f=parse(facility_data())
    assert Facility.model_validate_json(f.model_dump_json()).digest()==f.digest()


@pytest.mark.parametrize("fault",["energy","phase","direction","orphan","duplicate","volume","nan","bool"])
def test_unsafe_facility_connections_rejected(fault):
    d=facility_data()
    if fault=="energy":d["components"][1]["property_basis"]["energy_reference"]="unknown"
    elif fault=="phase":d["ports"][1]["phase"]="vapour"
    elif fault=="direction":d["ports"][0]["direction"]="in"
    elif fault=="orphan":d["edges"][0]["target_port"]="missing"
    elif fault=="duplicate":d["edges"].append({**d["edges"][0],"id":"second"})
    elif fault=="volume":d["components"][0]["parameters_si"]["volume_m3"]=0
    elif fault=="nan":d["components"][0]["position_enu_m"][0]=float("nan")
    elif fault=="bool":d["components"][0]["parameters_si"]["volume_m3"]=True
    with pytest.raises(ValidationError):parse(d)


def ledger(**kw):
    values=dict(source_stage="nozzle_to_ground_partition",property_basis=PropertyBasis(fluid="Hydrogen",energy_reference="native"),
                position_enu_m=(0.,0.,1.),direction_enu=(1.,0.,0.),duration_s=3.,integration_rule="left_constant",
                initial_available_mass_kg=10.,model_revision="test",request_digest="test",energy_balance_scope="unverified",
                limitations=("synthetic",),steps=(PartitionStep(time_s=0.,total_kg_s=2.,gas_kg_s=1.,airborne_liquid_kg_s=.25,ground_liquid_kg_s=.75),
                                                PartitionStep(time_s=1.,total_kg_s=1.,gas_kg_s=.5,airborne_liquid_kg_s=.25,ground_liquid_kg_s=.25)))
    values.update(kw);return SourceLedger(**values)


def test_partition_and_inventory_close_over_unequal_intervals():
    x=ledger()
    assert x.released_mass_kg==4
    assert sum(x.branch_mass_kg(b) for b in ("gas_kg_s","airborne_liquid_kg_s","ground_liquid_kg_s"))==4


def test_double_counted_mass_is_rejected():
    with pytest.raises(ValidationError):PartitionStep(time_s=0.,total_kg_s=1.,gas_kg_s=1.,airborne_liquid_kg_s=0.,ground_liquid_kg_s=.1)


@pytest.mark.parametrize("change",[{"initial_available_mass_kg":3.},{"direction_enu":(0.,0.,0.)},{"duration_s":.5}])
def test_bad_history_cannot_be_forwarded(change):
    with pytest.raises(ValidationError):ledger(**change)
