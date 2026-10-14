"""Run one source-state-bound compressible gas packet end to end.

This command is a diagnostic chain runner for an outdoor LH2 facility.  It
attaches an externally resolved compressible-plane handoff to one exact gas
release, binds it to a facility manifest and context, and executes the existing
near-field -> SLABx-LH2 -> ignition/exposure -> damage chain.  It deliberately
rejects initiating-frequency fields and never promotes provider, physical, or
facility evidence.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.compressible_handoff import (  # noqa: E402
    CompressibleHandoffExportError,
    attach_compressible_plane_handoff,
)
from lh2_tno.contracts import Facility  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    ProviderReleaseContractError,
    build_consequence_request_from_provider_release,
    load_provider_release,
)
from lh2_tno.resolved_gas_worker import resolve_gas_rows  # noqa: E402


class CompressiblePlaneChainError(ValueError):
    """Raised when the diagnostic chain cannot be bound without guessing."""


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompressiblePlaneChainError(f"cannot read JSON {path}: {error}") from error


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _same_vector(left: Any, right: Any, *, field: str) -> bool:
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
        raise CompressiblePlaneChainError(f"{field} must be a three-value vector")
    if len(left) != 3 or len(right) != 3:
        raise CompressiblePlaneChainError(f"{field} must be a three-value vector")
    return all(math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1.0e-12) for a, b in zip(left, right))


def bind_facility(facility_path: Path, release: Any) -> Facility:
    """Load an outdoor manifest and require exact provider component/port binding."""
    raw = _load(facility_path)
    try:
        facility = Facility.model_validate_json(json.dumps(raw, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise CompressiblePlaneChainError(f"facility manifest failed strict validation: {error}") from error
    if facility.environment != "outdoor":
        raise CompressiblePlaneChainError("compressible-plane diagnostic chain requires an outdoor facility")
    components = {item.id: item for item in facility.components}
    ports = {item.id: item for item in facility.ports}
    component = components.get(release.component_id)
    if component is None:
        raise CompressiblePlaneChainError(
            f"facility manifest has no provider component {release.component_id}"
        )
    port = ports.get(release.port_id)
    if port is None:
        raise CompressiblePlaneChainError(f"facility manifest has no provider port {release.port_id}")
    if port.component_id != release.component_id:
        raise CompressiblePlaneChainError("provider port component identity disagrees with facility manifest")
    if port.direction not in {"out", "bidirectional"}:
        raise CompressiblePlaneChainError("provider gas packet requires an outward facility port")
    if port.phase not in {"vapour", "two_phase", "any"}:
        raise CompressiblePlaneChainError("provider gas packet requires a vapour-compatible facility port")
    if not _same_vector(component.position_enu_m, release.position_enu_m, field="component.position_enu_m"):
        raise CompressiblePlaneChainError(
            "provider release position does not match the facility component; no coordinate override is implicit"
        )
    if port.position_enu_m is not None and not _same_vector(
        port.position_enu_m, release.position_enu_m, field="port.position_enu_m"
    ):
        raise CompressiblePlaneChainError(
            "provider release position does not match the facility port; no coordinate override is implicit"
        )
    if component.property_basis.fluid != release.property_basis.fluid:
        raise CompressiblePlaneChainError("provider fluid disagrees with facility property basis")
    return facility


def _source_operator(release: Any, context: Mapping[str, Any]) -> str:
    explicit = context.get("source_operator")
    if explicit is not None:
        return str(explicit)
    basis = release.termination_basis
    return {
        "inventory_depletion": "equipment_inventory_depletion",
        "inventory_over_600s": "equipment_inventory_over_600s",
        "model_pressure_equalization": "integrated_transient",
        "reviewed_isolation_success": "integrated_transient",
        "synthetic_diagnostic_horizon": "integrated_transient",
    }.get(basis, "integrated_transient")


def build_request(release: Any, context_path: Path) -> Any:
    """Bind provider duration and source operator without adding frequency."""
    context = _load(context_path)
    if not isinstance(context, dict):
        raise CompressiblePlaneChainError("request context must be a JSON object")
    forbidden = (
        "source_input", "resolved_release", "resolved_release_set", "resolved_liquid_release",
        "annual_frequency_per_year", "annual_frequency_provenance", "frequency_event",
        "initiation_intensity_per_s",
    )
    for key in forbidden:
        if context.get(key) is not None:
            raise CompressiblePlaneChainError(
                f"request context cannot own provider source or initiating frequency: {key}"
            )
    termination = context.get("release_termination")
    if not isinstance(termination, dict):
        raise CompressiblePlaneChainError("request context must declare release_termination")
    if termination.get("basis") != "provider_declared" or termination.get("time_s") != "provider_duration":
        raise CompressiblePlaneChainError(
            "compressible-plane chain requires release_termination basis=provider_declared and time_s=provider_duration"
        )
    context["source_operator"] = _source_operator(release, context)
    context["evaluation_times_s"] = sorted(
        {float(value) for value in context.get("evaluation_times_s", [])} | {float(release.duration_s)}
    )
    try:
        return build_consequence_request_from_provider_release(release, context)
    except (ProviderReleaseContractError, TypeError, ValueError) as error:
        raise CompressiblePlaneChainError(f"provider context failed strict request binding: {error}") from error


def load_backend(config_path: Path, *, refresh_pins: bool) -> tuple[BackendConfig, list[dict[str, str]]]:
    raw = _load(config_path)
    if not isinstance(raw, dict):
        raise CompressiblePlaneChainError("backend config must be a JSON object")
    refreshed: list[dict[str, str]] = []
    for pin in raw.get("packages", []):
        if not isinstance(pin, dict):
            raise CompressiblePlaneChainError("backend package pins must be objects")
        root = Path(str(pin.get("root", "")))
        if refresh_pins and root.exists():
            old = pin.get("sha256")
            new = tree_digest(root)
            pin["sha256"] = new
            if old != new:
                refreshed.append({"name": str(pin.get("name", "")), "old": str(old), "new": new})
    try:
        config = BackendConfig.model_validate_json(json.dumps(raw, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise CompressiblePlaneChainError(f"backend config failed strict validation: {error}") from error
    return config, refreshed


def _max_mach(release: Any) -> float | None:
    try:
        import CoolProp.CoolProp as cp
        _, history = resolve_gas_rows(release.model_dump(mode="json"), release.ambient_pressure_pa_abs, cp)
    except (ImportError, TypeError, ValueError, RuntimeError):
        return None
    checks = history.get("thermodynamic_checks", [])
    values = [float(row["mach_number"]) for row in checks if isinstance(row, Mapping) and row.get("mach_number") is not None]
    return max(values) if values else None


def run(
    packet_path: Path,
    handoff_path: Path,
    facility_path: Path,
    context_path: Path,
    backend_config_path: Path,
    output_dir: Path,
    *,
    refresh_pins: bool = False,
) -> dict[str, Any]:
    packet = _load(packet_path)
    handoff = _load(handoff_path)
    try:
        attached_packet, attach_audit = attach_compressible_plane_handoff(packet, handoff)
        release = load_provider_release(attached_packet)
    except (CompressibleHandoffExportError, ProviderReleaseContractError, TypeError, ValueError) as error:
        raise CompressiblePlaneChainError(f"compressible handoff binding failed: {error}") from error
    facility = bind_facility(facility_path, release)
    request = build_request(release, context_path)
    config, refreshed_pins = load_backend(backend_config_path, refresh_pins=refresh_pins)
    result = ResearchPipeline(facility, IsolatedBackend(config)).consequences(request)
    data = result.get("data", result) if isinstance(result, dict) else {}
    handoffs = data.get("handoffs", []) if isinstance(data, Mapping) else []
    if not isinstance(handoffs, list):
        handoffs = []
    consumed = bool(handoffs) and all(
        bool(item.get("provider_compressible_plane_adapter"))
        for item in handoffs
        if isinstance(item, Mapping)
    )
    status = data.get("status") if isinstance(data, Mapping) else None
    if status != "END_TO_END_DIAGNOSTIC_EXECUTED" or not data.get("full_chain_executed") or not consumed:
        raise CompressiblePlaneChainError(
            f"downstream chain did not consume the provider handoff: status={status!r}, "
            f"full_chain={data.get('full_chain_executed')!r}, handoffs={len(handoffs)}"
        )
    mass_residual = release.cumulative_mass_out_kg - release.integrated_mass_kg
    max_chain_residual = max(
        (abs(float(item.get("mass_residual_relative", 0.0))) for item in handoffs if isinstance(item, Mapping)),
        default=0.0,
    )
    verification = {
        "status": "SYNTHETIC_COMPRESSIBLE_PLANE_CHAIN_EXECUTED",
        "chain_status": status,
        "full_chain_executed": bool(data.get("full_chain_executed")),
        "provider_handoff_consumed": consumed,
        "handoff_count": len(handoffs),
        "handoff_state_count": attach_audit.get("handoff_state_count"),
        "event_id": release.event_id,
        "component_id": release.component_id,
        "port_id": release.port_id,
        "provider_result_digest": release.provider_result_digest,
        "provider_duration_s": release.duration_s,
        "provider_mass_residual_kg": mass_residual,
        "chain_max_mass_residual_relative": max_chain_residual,
        "max_mach_number": _max_mach(release),
        "source_operator": request.source_operator,
        "backend_pin_refresh": refreshed_pins,
        "operator_limited": bool(data.get("operator_limited")),
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference": False,
        "limitations": [
            "synthetic or diagnostic provider history; provider qualification is pending",
            "synthetic facility, receptors, weather and ignition context",
            "no initiating frequency was applied or inferred",
            "compressible-plane handoff is an adapter boundary, not an independently validated near-field solver",
        ],
    }
    _save(output_dir / "resolved_release_with_handoff.json", attached_packet)
    _save(output_dir / "attach_audit.json", attach_audit)
    _save(output_dir / "request.json", request.model_dump(mode="json"))
    _save(output_dir / "consequence_result.json", result)
    _save(output_dir / "backend_config_used.json", config.model_dump(mode="json"))
    _save(output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--facility", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--refresh-pins",
        action="store_true",
        help="refresh existing backend package digests explicitly before execution",
    )
    args = parser.parse_args()
    try:
        verification = run(
            args.packet,
            args.handoff,
            args.facility,
            args.context,
            args.backend_config,
            args.output_dir,
            refresh_pins=args.refresh_pins,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CompressiblePlaneChainError) as error:
        print(json.dumps({"status": "COMPRESSIBLE_PLANE_CHAIN_BLOCKED", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
