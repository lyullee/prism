"""Run one external LayeredTank diagnostic through the common adapter runner.

This is an operator-limited integration smoke.  The constructor arguments are
explicitly supplied by the host and the resulting packet remains synthetic
diagnostic evidence; the command never assigns frequency or facility QRA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
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
    opening_diameter_m = (4.0 * args.full_open_area_m2 / 3.141592653589793) ** 0.5
    component_id = args.component_id
    port_id = f"{component_id}.accident-out"
    event_id = f"{component_id}/{port_id}/{opening_diameter_m:.12g}m"
    state_payload = {
        "time_step_s": args.time_step_s,
        "target_release_kg": args.target_release_kg,
        "max_intervals": args.max_intervals,
        "full_open_area_m2": args.full_open_area_m2,
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
    runner.register_provider_from_config(
        "storage_tank",
        {
            "lh2dt_root": root,
            "time_step_s": args.time_step_s,
            "target_release_kg": args.target_release_kg,
            "max_intervals": args.max_intervals,
            "full_open_area_m2": args.full_open_area_m2,
            "request": request,
        },
    )
    execution = runner.execute("storage_tank", request, release_kind="liquid")
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    release = execution.result.release
    payload = {
        "schema_version": "prism.diagnostic_adapter_runner_smoke.v1",
        "status": "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC",
        "adapter_execution": execution.audit_record(),
        "provider_instance_count": 1,
        "qualified_provider_packet_count": 0,
        "provider_packet_promoted": execution.promoted,
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
