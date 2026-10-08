from dataclasses import dataclass

import pytest

from lh2_tno.inventory_source import liquid_jet_rows


@dataclass
class Gas:
    mass_flow_kg_s: float = 2.0
    temperature_k: float = 20.0
    pressure_pa: float = 101325.0
    density_kg_m3: float = 0.08
    velocity_m_s: float = 10.0
    direction: tuple = (1.0, 0.0, 0.0)
    effective_area_m2: float = 2.5


@dataclass
class Ground:
    mass_flow_kg_s: float = 1.0
    temperature_k: float = 20.0
    pressure_pa: float = 101325.0
    density_kg_m3: float = 70.0
    velocity_m_s: float = 10.0
    impact_position_m: tuple = (2.0, 0.0, 0.0)
    footprint_radius_m: float = .1
    footprint_area_m2: float = .03
    flight_time_s: float = .2


@dataclass
class Conservation:
    mass_in_kg_s: float = 3.0
    mass_out_kg_s: float = 3.0
    mass_residual_kg_s: float = 0.0


@dataclass
class Step:
    time_s: float
    gas: Gas
    ground: Ground
    conservation: Conservation


@dataclass
class History:
    steps: tuple


def test_liquid_jet_adapter_drops_only_endpoint_and_preserves_partition():
    rows, raw = liquid_jet_rows(History((Step(0.0, Gas(), Ground(), Conservation()),
                                         Step(.2, Gas(), Ground(), Conservation()))), .2)
    assert len(rows) == 1
    assert rows[0]['gas_mass_flow_kg_s'] == 2.0
    assert rows[0]['ground_liquid_mass_flow_kg_s'] == 1.0
    assert rows[0]['droplet_class_outcomes'][0]['flight_time_s'] == .2
    assert len(raw['steps']) == 2


def test_liquid_jet_adapter_rejects_open_mass_partition():
    bad = Conservation(mass_in_kg_s=3.0, mass_out_kg_s=2.0, mass_residual_kg_s=0.0)
    with pytest.raises(ValueError, match='partition'):
        liquid_jet_rows(History((Step(0.0, Gas(mass_flow_kg_s=1.0), Ground(), bad),)), .2)
