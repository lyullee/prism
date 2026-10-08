"""Audit a generic equipment-twin manifest before PRISM facility risk use.

Examples
--------
  python scripts/validate_equipment_manifest.py --manifest examples/equipment_manifest.json
  python scripts/validate_equipment_manifest.py --center-root <external model root>

The second form is an evidence adapter for the inspection-centre project.  It
does not copy screening values into PRISM and intentionally reports the
current centre export as PARTIAL when P&ID ports, positions or controls are
not declared.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Keep the source checkout directly runnable without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.equipment_manifest import EquipmentManifest, audit_manifest


def _digest_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(path.name.encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


def _centre_manifest(root: Path) -> EquipmentManifest:
    configs = root / "configs"
    topology = json.loads((configs / "center_topology.json").read_text(encoding="utf-8"))
    assets = json.loads((configs / "center_assets.json").read_text(encoding="utf-8"))
    netlist = json.loads((configs / "center_port_netlist.json").read_text(encoding="utf-8"))
    scenarios = json.loads((configs / "scenarios.json").read_text(encoding="utf-8"))
    asset_models = {x["asset_id"]: x.get("component_model", "boundary") for x in assets.get("assets", [])}
    kind_map = {
        "homogeneous_tank": "storage_tank", "stratified_tank": "storage_tank",
        "vaporizer": "vaporizer", "reliquefier": "reliquefier",
        "virtual_pump": "pump", "pump": "pump", "pipe": "pipe", "valve": "valve",
    }
    components = []
    for node in topology.get("nodes", []):
        model = asset_models.get(node, "boundary")
        components.append({
            "id": node, "kind": kind_map.get(model, "boundary"),
            "source_status": "candidate" if node not in asset_models else "declared",
            "source_provenance": "center_topology.json/center_assets.json",
        })
    port_rows: dict[str, dict] = {}
    edge_rows = []
    for connection in netlist.get("connections", []):
        source_id = connection.get("source_port_id")
        target_id = connection.get("target_port_id")
        for port_id in (source_id, target_id):
            if not port_id or port_id in port_rows:
                continue
            component_id = port_id.split(":", 1)[0]
            port_rows[port_id] = {
                "id": port_id, "component_id": component_id, "phase": "any",
                "direction": "bidirectional",
                "source_status": "candidate" if connection.get("status") != "declared" else "declared",
                "source_provenance": "center_port_netlist.json",
            }
        if source_id and target_id:
            edge_rows.append({
                "id": connection.get("connection_id", connection["edge_id"]),
                "source_port": source_id, "target_port": target_id,
                "source_status": "candidate" if connection.get("status") != "declared" else "declared",
                "source_provenance": "center_port_netlist.json",
            })
    scenario_rows = []
    for item in scenarios.get("scenarios", []):
        required_controls = tuple(
            control["control_id"] for control in item.get("control_contract", [])
            if control.get("required") is True
        )
        scenario_rows.append({
            "id": item["scenario_id"], "status": "screening_only",
            "required_controls": required_controls, "observed_controls": (),
            "limitations": tuple(item.get("known_limits", ())),
            "provenance": "configs/scenarios.json",
        })
    digest_paths = [configs / name for name in (
        "center_topology.json", "center_assets.json", "center_port_netlist.json", "scenarios.json",
    ) if (configs / name).exists()]
    return EquipmentManifest(
        facility_id="center-equipment-twin-screening",
        environment="outdoor", configuration_origin="reviewed_design",
        components=tuple(components), ports=tuple(port_rows.values()), edges=tuple(edge_rows),
        scenarios=tuple(scenario_rows), provider_source_digest=_digest_files(digest_paths),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest", type=Path)
    group.add_argument("--center-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path)
    args = parser.parse_args()
    manifest = EquipmentManifest.from_json(args.manifest) if args.manifest else _centre_manifest(args.center_root)
    if args.manifest_output:
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = audit_manifest(manifest)
    result["input_kind"] = "generic_manifest" if args.manifest else "external_centre_screening_adapter"
    result["provider_source_digest"] = manifest.provider_source_digest
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output), "blocking_reasons": result["blocking_reasons"]}, ensure_ascii=False))
    return 0 if result["status"] == "EXECUTABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
