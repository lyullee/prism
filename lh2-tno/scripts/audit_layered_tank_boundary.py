"""Audit an exported LayeredTank network boundary for PRISM promotion.

The export is intentionally small and contains only values emitted by the
optional equipment provider: solved link flow, endpoint states and the tank
mass/energy ledger.  The script never fills in flash, spray or atmospheric
geometry fields.  It is therefore safe to run on a screening export while a
provider-side atmospheric outlet adapter is being developed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.layered_network_boundary import audit_layered_liquid_boundary


def _namespace(raw: dict, packet: dict) -> SimpleNamespace:
    flow = SimpleNamespace(**raw["flow"])
    states = {
        name: SimpleNamespace(**state)
        for name, state in {
            packet["source_node"]: raw["source_state"],
            packet["target_node"]: raw["target_state"],
        }.items()
    }
    network = SimpleNamespace(link_flows={packet["link_name"]: flow}, node_states=states)
    tank_data = raw.get("tank")
    tank = None if tank_data is None else SimpleNamespace(**tank_data)
    return SimpleNamespace(time_s=raw["time_s"], network_solution=network, tank=tank)


def audit_export(packet: dict):
    results = [_namespace(row, packet) for row in packet["steps"]]
    return audit_layered_liquid_boundary(
        results,
        component_id=packet["component_id"],
        source_node=packet["source_node"],
        target_node=packet["target_node"],
        source_phase=packet["source_phase"],
        ambient_pressure_pa=packet["ambient_pressure_pa"],
        link_name=packet["link_name"],
        pressure_tolerance_pa=packet.get("pressure_tolerance_pa", 250.0),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    packet = json.loads(args.export.read_text(encoding="utf-8"))
    audit = audit_export(packet)
    output = {
        "provider_project": packet.get("provider_project"),
        "provider_script": packet.get("provider_script"),
        **audit.to_dict(),
    }
    destination = args.output or args.export.with_name("layered_tank_boundary_audit.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
