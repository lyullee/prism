#!/usr/bin/env python3
"""Run the pinned external TNO scenario generator and audit the PRISM handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.contracts import Facility
from lh2_tno.legacy_frequency_bridge import bridge_digest, bridge_legacy_scenarios


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_demo_site(T):
    """Use a small, declared LH2 receiving-site case from the legacy package."""
    return T.Site(
        name="LH2 station (PRISM bridge audit)",
        sections=[
            T.Section(id="LH2_TANK", inventory_kg=5000, isolation_time_s=1800, service=T.Service.LH2),
            T.Section(id="LH2_TRANSFER", inventory_kg=80, isolation_time_s=30, service=T.Service.LH2),
            T.Section(id="GH2_HP", inventory_kg=120, isolation_time_s=15, service=T.Service.GH2),
        ],
        components=[
            T.ComponentSpec(
                primitive=T.Primitive.VESSEL, service=T.Service.LH2, tag="TK-101",
                nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
                position=T.Position(x=0, y=0), section_id="LH2_TANK",
            ),
            T.ComponentSpec(
                primitive=T.Primitive.VALVE, service=T.Service.GH2, count=12, tag="HP-V",
                nominal_diameter_m=0.012, pressure_pa=4.5e7, temperature_k=288,
                position=T.Position(x=30, y=5), section_id="GH2_HP",
            ),
        ],
        assemblies=[
            T.AssemblySpec(
                assembly=T.Assembly.VJ_LINE, service=T.Service.LH2, tag="LP-201", count=3,
                nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
                position=T.Position(x=12, y=0), section_id="LH2_TRANSFER",
            ),
            T.AssemblySpec(
                assembly=T.Assembly.LH2_PUMP, service=T.Service.LH2, tag="P-401",
                nominal_diameter_m=0.04, pressure_pa=8e5, temperature_k=22,
                position=T.Position(x=18, y=2), section_id="LH2_TRANSFER",
            ),
            T.AssemblySpec(
                assembly=T.Assembly.VAPORIZER_UNIT, service=T.Service.COLD_GH2, tag="VAP-501",
                nominal_diameter_m=0.025, pressure_pa=3e7, temperature_k=150,
                position=T.Position(x=24, y=2), section_id="GH2_HP",
            ),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-code", type=Path, required=True,
                        help="directory containing the pinned legacy taxonomy.py")
    parser.add_argument("--facility", type=Path,
                        default=ROOT / "examples/lh2_frequency_facility.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    legacy_code = args.legacy_code.resolve()
    taxonomy_path = legacy_code / "taxonomy.py"
    if not taxonomy_path.is_file():
        parser.error(f"legacy taxonomy.py not found under {legacy_code}")
    # Import only the explicitly supplied, hash-recorded external module.
    sys.path.insert(0, str(legacy_code))
    import taxonomy as T  # type: ignore[import-not-found]

    site = _legacy_demo_site(T)
    scenarios = [scenario.model_dump(mode="json") for scenario in T.enumerate_scenarios(site)]
    prefix_map = {
        "TK-101": "tank",
        "LP-201": "transfer",
        "P-401": "pump",
        "VAP-501": "vaporizer",
        "HP-V": "valves",
    }
    component_map: dict[str, str] = {}
    basis_map: dict[str, str] = {}
    for row in scenarios:
        tag = str(row.get("tag", ""))
        prefix = tag.split("/", 1)[0]
        if prefix not in prefix_map:
            raise RuntimeError(f"bridge audit has no explicit tag mapping for {tag}")
        component_map[str(row["scenario_id"])] = prefix_map[prefix]
        basis_map[str(row["scenario_id"])] = (
            "LH2_LITERATURE" if str(row.get("service")) == "LH2" else "TNO_PURPLE_LOC"
        )

    facility = Facility.model_validate_json(args.facility.read_text(encoding="utf-8"))
    events, audit = bridge_legacy_scenarios(
        scenarios,
        component_map,
        plan_id="legacy-tno-demo3",
        source=f"legacy taxonomy.py enumerate_scenarios ({taxonomy_path})",
        source_sha256=_sha256(taxonomy_path),
        facility=facility,
        basis=basis_map,
    )
    audit.update({
        "legacy_source_path": str(taxonomy_path),
        "legacy_site_name": site.name,
        "explicit_tag_to_component_map": prefix_map,
        "legacy_generator": "taxonomy.enumerate_scenarios",
        "legacy_resolver": "taxonomy.resolve_frequency (called by enumerate_scenarios)",
        "legacy_source_sha256": _sha256(taxonomy_path),
    })
    result = {
        "schema_version": "prism.legacy_tno_frequency_bridge_audit.v1",
        "status": "BRIDGED_DIAGNOSTIC_ONLY",
        "bridge_audit": audit,
        "bridge_audit_digest": bridge_digest(audit),
        "events": [event.model_dump(mode="json") for event in events],
        "frequency_inference_performed": False,
        "provider_packet_created": False,
        "facility_qra_promotion": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "output": str(args.output.resolve()),
        "legacy_scenario_count": audit["legacy_scenario_count"],
        "bridged_event_count": audit["bridged_event_count"],
        "mapped_component_ids": audit["mapped_component_ids"],
        "frequency_inference_performed": False,
        "facility_qra_promotion": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
