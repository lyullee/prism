"""Run one external LayeredTank diagnostic through the common adapter runner.

This is an operator-limited integration smoke.  The constructor arguments are
explicitly supplied by the host and the resulting packet remains synthetic
diagnostic evidence; the command never assigns frequency or facility QRA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.diagnostic_adapter_runner import DiagnosticAdapterRunner  # noqa: E402
from scripts.export_lh2dt_layered_tank_prism_packet import (  # noqa: E402
    _request,
    _tree_digest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider-worklist", type=Path)
    parser.add_argument("--worklist-event-id")
    parser.add_argument("--run-consequence-chain", action="store_true")
    parser.add_argument(
        "--backend-config",
        type=Path,
        default=ROOT / "results" / "20261009" / "backend_config_current.json",
    )
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--target-release-kg", type=float, default=1.0e-4)
    # The strict liquid packet intentionally caps its left-held history at
    # 100 rows.  These diagnostic defaults reach the provider's positive
    # inventory threshold within that cap; the opening is synthetic.
    parser.add_argument("--max-intervals", type=int, default=100)
    parser.add_argument("--full-open-area-m2", type=float, default=1.0e-6)
    parser.add_argument("--component-id", default="layered-tank-runner-smoke")
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument("--model-revision", default="external-library-layered-tank-0.1.1")
    args = parser.parse_args()

    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    worklist_item = None
    if args.provider_worklist is not None:
        try:
            worklist = json.loads(args.provider_worklist.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SystemExit(f"cannot read provider worklist: {error}") from error
        items = worklist.get("work_items") if isinstance(worklist, dict) else None
        if not isinstance(items, list):
            raise SystemExit("provider worklist must contain work_items")
        candidates = [
            item for item in items
            if isinstance(item, dict)
            and item.get("component_id") == args.component_id
            and (args.worklist_event_id is None or item.get("event_id") == args.worklist_event_id)
        ]
        if len(candidates) != 1:
            raise SystemExit(
                "worklist selection must identify exactly one item; "
                f"got {len(candidates)}"
            )
        worklist_item = candidates[0]
        ports = worklist_item.get("accident_port_ids")
        diameter = worklist_item.get("required_opening_diameter_m")
        if len(ports or []) != 1 or diameter is None:
            raise SystemExit("selected worklist item must declare one port and an opening diameter")
        component_id = str(worklist_item["component_id"])
        port_id = str(ports[0])
        event_id = str(worklist_item["event_id"])
        opening_diameter_m = float(diameter)
        full_open_area_m2 = 3.141592653589793 * opening_diameter_m**2 / 4.0
    else:
        opening_diameter_m = (4.0 * args.full_open_area_m2 / 3.141592653589793) ** 0.5
        component_id = args.component_id
        port_id = f"{component_id}.accident-out"
        event_id = f"{component_id}/{port_id}/{opening_diameter_m:.12g}m"
        full_open_area_m2 = args.full_open_area_m2
    state_payload = {
        "time_step_s": args.time_step_s,
        "target_release_kg": args.target_release_kg,
        "max_intervals": args.max_intervals,
        "full_open_area_m2": full_open_area_m2,
    }
    request = _request(
        provider_source_digest=source_digest,
        component_id=component_id,
        port_id=port_id,
        event_id=event_id,
        opening_diameter_m=opening_diameter_m,
        position_enu_m=[0.0, 0.0, args.nozzle_height_m],
        direction_enu=[2.0**-0.5, 0.0, -2.0**-0.5],
        model_revision=args.model_revision,
        state_snapshot_digest=canonical_digest(state_payload),
    )

    runner = DiagnosticAdapterRunner.from_binding_catalog(
        ROOT / "examples" / "generic_lh2_model_binding.json"
    )
    start = time.perf_counter()
    constructor_kwargs = {
        "lh2dt_root": root,
        "time_step_s": args.time_step_s,
        "target_release_kg": args.target_release_kg,
        "max_intervals": args.max_intervals,
        "full_open_area_m2": full_open_area_m2,
        "request": request,
    }
    provider_instance_id = component_id if worklist_item is not None else None
    if provider_instance_id is None:
        runner.register_provider_from_config("storage_tank", constructor_kwargs)
    else:
        runner.register_provider_instance_from_config(
            provider_instance_id, "storage_tank", constructor_kwargs
        )
    execution = runner.execute(
        "storage_tank",
        request,
        provider_instance_id=provider_instance_id,
        release_kind="liquid",
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    release = execution.result.release
    consequence_defaults = json.loads(
        (ROOT / "examples" / "equipment_consequence_template.json").read_text(
            encoding="utf-8"
        )
    )
    consequence_defaults.update(
        component_id=release.component_id,
        source_input=None,
        available_mass_kg=release.available_mass_kg,
        resolved_release=None,
        resolved_release_set=None,
        resolved_liquid_release=None,
        source_operator="equipment_liquid_release",
        release_termination={
            "basis": "provider_declared",
            "time_s": "provider_duration",
            "provenance": "explicit diagnostic provider termination",
        },
    )
    consequence_request = runner.to_consequence_request(
        execution, consequence_defaults
    )
    exact_worklist_match = None
    if worklist_item is not None:
        exact_worklist_match = {
            "event_id": release.event_id == worklist_item["event_id"],
            "component_id": release.component_id == worklist_item["component_id"],
            "port_id": release.port_id == worklist_item["accident_port_ids"][0],
            "opening_diameter_m": abs(
                float(release.failure_opening_diameter_m)
                - float(worklist_item["required_opening_diameter_m"])
            ) <= 1.0e-12,
        }
        if not all(exact_worklist_match.values()):
            raise RuntimeError(f"runner release did not exact-match worklist: {exact_worklist_match}")
    consequence_chain_verification = None
    consequence_chain_result = None
    if args.run_consequence_chain:
        chain_dir = args.output.parent / f"{args.output.stem}_consequence_chain"
        packet_path = chain_dir / "runner_resolved_release.json"
        packet_path.parent.mkdir(parents=True, exist_ok=True)
        packet_path.write_text(
            json.dumps(release.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        chain_script = ROOT / "scripts" / "validate_lh2dt_prism_packet_chain.py"
        completed = subprocess.run(
            [
                sys.executable,
                str(chain_script),
                "--packet",
                str(packet_path),
                "--output-dir",
                str(chain_dir),
                "--backend-config",
                str(args.backend_config),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"runner consequence chain failed (exit {completed.returncode}): {detail}"
            )
        verification_path = chain_dir / "verification.json"
        consequence_chain_verification = json.loads(
            verification_path.read_text(encoding="utf-8")
        )
        consequence_result_path = chain_dir / "consequence_result.json"
        consequence_chain_result = json.loads(
            consequence_result_path.read_text(encoding="utf-8")
        )
    payload = {
        "schema_version": "prism.diagnostic_adapter_runner_smoke.v1",
        "status": "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC",
        "adapter_execution": execution.audit_record(),
        "provider_instance_count": 1,
        "qualified_provider_packet_count": 0,
        "provider_packet_promoted": execution.promoted,
        "worklist_item_id": None if worklist_item is None else worklist_item["id"],
        "worklist_exact_match": exact_worklist_match,
        "worklist_frequency_bound": False,
        "consequence_context_attached": True,
        "consequence_context_component_id": consequence_request.component_id,
        "consequence_context_event_id": (
            consequence_request.resolved_liquid_release.event_id
            if consequence_request.resolved_liquid_release is not None
            else None
        ),
        "consequence_context_frequency_bound": (
            consequence_request.annual_frequency_per_year is not None
            or consequence_request.frequency_event is not None
        ),
        "consequence_chain_executed": consequence_chain_verification is not None,
        "consequence_chain_status": (
            None if consequence_chain_verification is None
            else consequence_chain_verification.get("status")
        ),
        "consequence_chain_record": (
            None if consequence_chain_verification is None
            else str(args.output.parent / f"{args.output.stem}_consequence_chain")
        ),
        "consequence_chain_elapsed_ms": (
            None if consequence_chain_result is None
            else consequence_chain_result.get("elapsed_ms")
        ),
        "fresh_execution_elapsed_ms": elapsed_ms,
        "strict_packet_duration_s": release.duration_s,
        "strict_packet_mass_residual_kg": release.cumulative_mass_out_kg - release.integrated_mass_kg,
        "strict_packet_energy_residual_j": release.cumulative_specific_enthalpy_out_j - release.integrated_specific_enthalpy_out_j,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "limitations": [
            "synthetic LayeredTank geometry, opening and atmospheric boundary",
            "provider evidence_status is synthetic_diagnostic",
            "no frequency or facility IR/F-N was attached",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
