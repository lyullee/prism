"""Build a digest-bound ledger for the seven native LH2 accident adapters."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_SOURCE_STATE_COMPLETE_STATUSES = {
    "COMPLETED_ISENTROPIC_THROAT_FIELDS",
    "PROVIDER_NATIVE_SOURCE_THROAT_FIELDS",
}

_CASES = (
    ("LayeredTank", "scripts/export_lh2dt_native_layered_tank_prism_packet.py", "results/20261025/native_layered_tank_isolation/verification.json", "results/20261025/native_layered_tank_isolation/chain/verification.json", True),
    ("DynamicHEMPipe", "scripts/export_lh2dt_native_dynamic_pipe_prism_packet.py", "results/20261025/native_dynamic_pipe_isolation/verification.json", "results/20261025/native_dynamic_pipe_isolation/chain/verification.json", True),
    ("StrokeLimitedCommandedValve", "scripts/export_lh2dt_native_valve_prism_packet.py", "results/20261025/native_stroke_valve/verification.json", "results/20261025/native_stroke_valve_low_mach/chain/verification.json", False),
    ("MappedPump", "scripts/export_lh2dt_native_mapped_pump_prism_packet.py", "results/20261025/native_mapped_pump/verification.json", "results/20261025/native_mapped_pump/chain/verification.json", True),
    ("DynamicVaporizer", "scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py", "results/20261025/native_dynamic_vaporizer/verification.json", "results/20261025/native_dynamic_vaporizer/chain/verification.json", True),
    ("DynamicReliquefier", "scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py", "results/20261025/native_dynamic_reliquefier/verification.json", "results/20261025/native_dynamic_reliquefier/chain/verification.json", True),
    ("VentStack", "scripts/export_lh2dt_native_vent_stack_prism_packet.py", "results/20261025/native_vent_stack/verification.json", "results/20261025/native_vent_stack/chain/verification.json", True),
)


def _read(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} must contain a JSON object")
    return value


def build() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for model, adapter, verification_path, chain_path, same_packet in _CASES:
        verification = _read(verification_path)
        chain = _read(chain_path)
        if verification.get("status") != "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC":
            raise ValueError(f"{model} native verification is not diagnostic-executed")
        if chain.get("status") != "END_TO_END_DIAGNOSTIC_EXECUTED":
            raise ValueError(f"{model} consequence chain is not end-to-end executed")
        entries.append({
            "model_class": model,
            "adapter_script": adapter,
            "verification_record": verification_path,
            "chain_record": chain_path,
            "provider_model": verification.get("provider_model"),
            "provider_source_digest": verification.get("provider_source_digest"),
            "provider_result_digest": verification.get("provider_result_digest"),
            "native_provider_result_digest": verification.get("native_provider_result_digest"),
            "source_state_completion_status": (
                verification.get("source_state_completion", {}).get("status")
                if isinstance(verification.get("source_state_completion"), dict)
                else None
            ),
            "source_state_completion_interval_count": (
                verification.get("source_state_completion", {}).get("interval_count")
                if isinstance(verification.get("source_state_completion"), dict)
                else None
            ),
            "termination_basis": verification.get("termination_basis"),
            "duration_s": verification.get("duration_s"),
            "provider_packet_promoted": verification.get("provider_packet_promoted"),
            "physical_validation_claim": verification.get("physical_validation_claim"),
            "frequency_inference_performed": verification.get("frequency_inference_performed"),
            "facility_qra_claim": verification.get("facility_qra_claim"),
            "chain_status": chain.get("status"),
            "same_packet_chain": same_packet,
            "chain_provider_packet_promoted": chain.get("provider_packet_promoted"),
            "chain_frequency_inference": chain.get("frequency_inference"),
            "chain_physical_validation": chain.get("physical_validation_claim"),
            "chain_facility_ir_fn_claim": chain.get("facility_ir_fn_claim"),
        })
    return {
        "schema_version": "prism.native_direct_adapter_coverage.v1",
        "status": "DIRECT_NATIVE_ADAPTERS_AND_CHAINS_EXECUTED_DIAGNOSTIC",
        "native_model_count": len(entries),
        "native_model_classes": [item["model_class"] for item in entries],
        "end_to_end_chain_count": sum(item["chain_status"] == "END_TO_END_DIAGNOSTIC_EXECUTED" for item in entries),
        "same_packet_chain_count": sum(bool(item["same_packet_chain"]) for item in entries),
        "chain_variant_count": sum(not bool(item["same_packet_chain"]) for item in entries),
        "source_state_completion_count": sum(
            item["source_state_completion_status"] in _SOURCE_STATE_COMPLETE_STATUSES
            for item in entries
        ),
        "source_state_completion_blocked_count": sum(
            item["source_state_completion_status"] is None for item in entries
        ),
        "provider_packet_promoted_count": sum(bool(item["provider_packet_promoted"]) for item in entries),
        "physical_validation_claim_count": sum(bool(item["physical_validation_claim"]) for item in entries),
        "frequency_inference_count": sum(bool(item["frequency_inference_performed"]) for item in entries),
        "facility_qra_claim_count": sum(bool(item["facility_qra_claim"]) for item in entries),
        "entries": entries,
        "limitations": [
            "all seven records use synthetic or operator-declared diagnostic conditions",
            "native direct execution does not qualify provider packets or field frequencies",
            "high-speed gas cases still require a provider-resolved compressible-plane handoff",
            "facility IR/F-N remains withheld until every declared case has qualified evidence and independent validation",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "native_model_count": result["native_model_count"], "end_to_end_chain_count": result["end_to_end_chain_count"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
