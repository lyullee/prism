"""Audit finite-release provider handoff preservation through the chain.

The command is a diagnostic replay.  It never changes provider flow or
thermodynamic history.  ``--rebase-to-manifest-position`` is explicit because
older saved packets can carry a local origin while the facility manifest uses
the reviewed equipment position; the output records the transformed request
digest and keeps facility-QRA qualification closed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.contracts import canonical_digest
from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.pipeline import ResearchPipeline


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _component_position(manifest: EquipmentManifest, component_id: str) -> list[float]:
    for component in manifest.components:
        if component.id == component_id:
            return list(component.position_enu_m)
    raise ValueError(f"component {component_id!r} is not present in the manifest")


def audit(
    request_path: Path,
    manifest_path: Path,
    backend_config_path: Path,
    *,
    rebase_to_manifest_position: bool = False,
) -> dict[str, Any]:
    raw = _load(request_path)
    manifest = EquipmentManifest.from_json(manifest_path)
    component_id = raw.get("component_id")
    if not isinstance(component_id, str) or not component_id:
        raise ValueError("request.component_id must be a non-empty string")
    reviewed_position = _component_position(manifest, component_id)
    original_position = raw.get("source_position_enu_m")
    if original_position != reviewed_position:
        if not rebase_to_manifest_position:
            raise ValueError(
                "provider request position disagrees with the manifest; "
                "pass --rebase-to-manifest-position for an explicit diagnostic replay"
            )
        raw["source_position_enu_m"] = reviewed_position
        for key in ("resolved_release", "resolved_liquid_release"):
            release = raw.get(key)
            if isinstance(release, dict):
                release["position_enu_m"] = reviewed_position

    request = ConsequenceRequest.model_validate_json(
        json.dumps(raw, ensure_ascii=False, allow_nan=False)
    )
    config = _load(backend_config_path)
    for pin in config.get("packages", ()):
        if not isinstance(pin, dict):
            raise ValueError("backend_config.packages entries must be objects")
        root = Path(pin["root"])
        if root.exists():
            pin["sha256"] = tree_digest(root)
    backend = IsolatedBackend(
        BackendConfig.model_validate_json(
            json.dumps(config, ensure_ascii=False, allow_nan=False)
        )
    )

    started = time.perf_counter()
    result = ResearchPipeline(manifest.to_facility(), backend).consequences(request)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    data = result.get("data", {})
    fallbacks = data.get("dispersion_handoff_fallbacks", [])
    if not isinstance(fallbacks, list):
        raise ValueError("chain result dispersion_handoff_fallbacks must be an array")
    methods = [row.get("method") for row in fallbacks if isinstance(row, dict)]
    finite_count = sum(method == "finite_provider_handoff_native_puff" for method in methods)
    instantaneous_count = sum(method == "instantaneous_provider_handoff_native_puff" for method in methods)
    return {
        "schema_version": "prism.finite_release_puff_handoff_replay.v1",
        "status": data.get("status"),
        "source_request_record": str(request_path),
        "source_request_digest_after_rebase": canonical_digest(raw),
        "component_id": component_id,
        "original_position_enu_m": original_position,
        "reviewed_manifest_position_enu_m": reviewed_position,
        "location_rebase_applied": original_position != reviewed_position,
        "case_count": len(fallbacks),
        "finite_clock_native_puff_case_count": finite_count,
        "instantaneous_fallback_case_count": instantaneous_count,
        "full_chain_executed_case_count": sum(
            1 for _ in fallbacks
        ) if data.get("full_chain_executed") else 0,
        "dispersion_handoff_fallbacks": fallbacks,
        "elapsed_ms": elapsed_ms,
        "diagnostic_only": True,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rebase-to-manifest-position", action="store_true")
    args = parser.parse_args()
    result = audit(
        args.request,
        args.manifest,
        args.backend_config,
        rebase_to_manifest_position=args.rebase_to_manifest_position,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
