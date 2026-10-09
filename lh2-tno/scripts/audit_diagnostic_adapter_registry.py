"""Audit the common PRISM-side diagnostic adapter execution registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from lh2_tno.diagnostic_adapter_runner import DiagnosticAdapterRunner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runner = DiagnosticAdapterRunner.from_binding_catalog(args.binding)
    rows = []
    for spec in runner.specs:
        provider_class = runner.resolve_provider_class(spec.component_kind)
        rows.append({
            "component_kind": spec.component_kind,
            "module": spec.module,
            "provider_class": spec.provider_class,
            "resolved_class": f"{provider_class.__module__}.{provider_class.__qualname__}",
            "export_method": "export_accident_history",
            "evidence_status": spec.evidence_status,
            "provider_instance_registered": False,
            "qualified_provider_packet": False,
        })
    payload = {
        "schema_version": "prism.diagnostic_adapter_registry_audit.v1",
        "status": "DECLARED_ADAPTERS_RESOLVED_PROVIDER_INSTANCES_REQUIRED",
        "binding_catalog": str(args.binding),
        "adapter_count": len(rows),
        "resolved_adapter_count": len(rows),
        "provider_instance_count": 0,
        "qualified_provider_packet_count": 0,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "rows": rows,
        "policy": {
            "provider_instance_must_be_registered_by_host": True,
            "normal_state_model_is_not_an_accident_provider": True,
            "evaluate_simulate_fallback": False,
            "synthetic_or_screening_evidence_is_not_qualified": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
