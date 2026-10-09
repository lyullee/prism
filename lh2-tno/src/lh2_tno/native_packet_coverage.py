"""Build an evidence-only ledger for native LH2 model release packets.

The ledger answers a narrow audit question: which saved ``lh2dt`` accident
exports have an exact event identity, and which of those exports reached the
PRISM consequence-chain boundary?  It deliberately does not infer a rate,
promote a provider packet, or make a facility IR/F-N claim.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
import json
from pathlib import Path
from typing import Any


RELEASE_SCHEMAS = {"prism.resolved_release.v1", "prism.resolved_release_set.v1"}
RESPONSE_SCHEMA = "prism.external_accident_history.v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _event_ids(value: Any) -> set[str]:
    return {
        str(row["event_id"])
        for row in _walk(value)
        if isinstance(row.get("event_id"), str)
    }


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and value == value and abs(float(value)) != float("inf")


def _first_release(packet_dir: Path) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    response: Mapping[str, Any] | None = None
    for path in sorted(packet_dir.glob("provider_response*.json")):
        try:
            value = _load(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, Mapping) or value.get("provider_export_schema") != RESPONSE_SCHEMA:
            continue
        data = value.get("data")
        if isinstance(data, Mapping) and isinstance(data.get("event_id"), str):
            response = value
            break
    releases: list[Mapping[str, Any]] = []
    for path in sorted(packet_dir.glob("resolved_release*.json")):
        try:
            value = _load(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for row in _walk(value):
            if row.get("provider_export_schema") in RELEASE_SCHEMAS and isinstance(row.get("event_id"), str):
                releases.append(row)
    if not releases:
        return None, response
    event_id = response.get("data", {}).get("event_id") if response else None
    selected = next((row for row in releases if row.get("event_id") == event_id), releases[0])
    return selected, response


def _chain_index(results_root: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for path in results_root.rglob("verification.json"):
        try:
            verification = _load(path)
            if not isinstance(verification, Mapping) or not str(verification.get("status", "")).startswith("END_TO_END"):
                continue
            request_path = path.parent / "request.json"
            request = _load(request_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for event_id in _event_ids(request):
            index[event_id].append(str(path.relative_to(results_root.parent)).replace("\\", "/"))
    return dict(index)


def _worklist_ids(provider_worklist: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(provider_worklist, Mapping):
        return set()
    return {
        str(row.get("event_id"))
        for row in provider_worklist.get("work_items", [])
        if isinstance(row, Mapping) and isinstance(row.get("event_id"), str)
    }


def build_native_packet_coverage_ledger(
    results_root: str | Path,
    packet_dirs: Iterable[str | Path],
    provider_worklist: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, diagnostic-only coverage ledger.

    ``packet_dirs`` is explicit so old smoke outputs are not silently treated
    as current evidence.  Missing directories are reported as skipped rows.
    """
    root = Path(results_root).resolve()
    chain_index = _chain_index(root)
    worklist_ids = _worklist_ids(provider_worklist)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped: list[str] = []
    for raw_dir in packet_dirs:
        packet_dir = Path(raw_dir)
        if not packet_dir.is_absolute():
            packet_dir = root / packet_dir
        packet_dir = packet_dir.resolve()
        key = str(packet_dir)
        if key in seen:
            continue
        seen.add(key)
        if not packet_dir.is_dir():
            skipped.append(str(packet_dir.relative_to(root.parent)).replace("\\", "/"))
            continue
        release, response = _first_release(packet_dir)
        if release is None:
            skipped.append(str(packet_dir.relative_to(root.parent)).replace("\\", "/"))
            continue
        verification: Mapping[str, Any] = {}
        verification_path = packet_dir / "verification.json"
        try:
            value = _load(verification_path)
            if isinstance(value, Mapping):
                verification = value
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        event_id = str(release.get("event_id"))
        component_id = release.get("component_id")
        event_chain = chain_index.get(event_id, [])
        cumulative = release.get("cumulative_mass_out_kg")
        integrated = release.get("integrated_mass_kg")
        residual = None
        if _finite(cumulative) and _finite(integrated):
            residual = float(cumulative) - float(integrated)
        if residual is None and _finite(verification.get("provider_mass_residual_kg")):
            residual = float(verification["provider_mass_residual_kg"])
        packet_model = response.get("provider_model") if response else verification.get("provider_model")
        chain_executed = bool(event_chain) or (
            verification.get("consequence_chain_executed") is True
            or verification.get("facility_campaign_executed") is True
        )
        chain_paths = list(event_chain)
        if not event_chain and chain_executed:
            chain_paths = [str(verification_path.relative_to(root.parent)).replace("\\", "/")]
        frequency_bound = (
            verification.get("frequency_applied") is True
            or verification.get("literature_frequency_bound") is True
        )
        rows.append({
            "family_hint": event_id.split("/")[-2] if "/" in event_id else None,
            "packet_path": str(packet_dir.relative_to(root.parent)).replace("\\", "/"),
            "verification_path": str(verification_path.relative_to(root.parent)).replace("\\", "/") if verification_path.is_file() else None,
            "event_id": event_id,
            "component_id": component_id,
            "port_id": release.get("port_id"),
            "provider_model": packet_model,
            "provider_export_schema": release.get("provider_export_schema"),
            "phase_basis": release.get("phase_basis"),
            "failure_opening_diameter_m": release.get("failure_opening_diameter_m"),
            "duration_s": release.get("duration_s"),
            "termination_basis": release.get("termination_basis"),
            "termination_provenance": release.get("termination_provenance"),
            "available_mass_kg": release.get("available_mass_kg"),
            "cumulative_mass_out_kg": cumulative,
            "integrated_mass_kg": integrated,
            "mass_residual_kg": residual,
            "exact_worklist_event": event_id in worklist_ids if worklist_ids else None,
            "chain_executed": chain_executed,
            "chain_verification_paths": chain_paths,
            "frequency_bound": frequency_bound,
            "frequency_event_id": verification.get("frequency_event_id"),
            "provider_packet_promoted": verification.get("provider_packet_promoted") is True,
            "physical_validation_claim": verification.get("physical_validation_claim") is True,
            "facility_qra_claim": verification.get("facility_qra_claim") is True,
            "verification_status": verification.get("status"),
            "evidence_status": "NATIVE_PACKET_WITH_CONSEQUENCE_CHAIN" if chain_executed else "NATIVE_PACKET_ONLY",
            "diagnostic_only": True,
        })
    rows.sort(key=lambda row: (str(row.get("event_id")), str(row.get("packet_path"))))
    family_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"packet_count": 0, "chain_count": 0, "frequency_bound_count": 0})
    for row in rows:
        family = str(row.get("family_hint") or "unknown")
        family_summary[family]["packet_count"] += 1
        family_summary[family]["chain_count"] += int(row["chain_executed"])
        family_summary[family]["frequency_bound_count"] += int(row["frequency_bound"])
    return {
        "schema_version": "prism.native_lh2dt_packet_coverage_ledger.v1",
        "status": "PARTIAL_NATIVE_DIAGNOSTIC_EVIDENCE" if rows else "NO_NATIVE_PACKET_EVIDENCE",
        "results_root": str(root.relative_to(root.parent)).replace("\\", "/"),
        "packet_count": len(rows),
        "exact_worklist_event_count": sum(int(row["exact_worklist_event"]) for row in rows if row["exact_worklist_event"] is not None),
        "consequence_chain_event_count": sum(int(row["chain_executed"]) for row in rows),
        "frequency_bound_event_count": sum(int(row["frequency_bound"]) for row in rows),
        "provider_packet_promoted_count": sum(int(row["provider_packet_promoted"]) for row in rows),
        "physical_validation_claim_count": sum(int(row["physical_validation_claim"]) for row in rows),
        "facility_qra_claim_count": sum(int(row["facility_qra_claim"]) for row in rows),
        "family_summary": dict(sorted(family_summary.items())),
        "skipped_packet_directories": skipped,
        "rows": rows,
        "policy": {
            "diagnostic_only": True,
            "frequency_inference_performed": False,
            "provider_packet_promoted": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
        },
        "interpretation": (
            "Native lh2dt accident exports are indexed with their termination and mass ledgers. "
            "A consequence-chain row proves interface execution only; packet evidence remains "
            "synthetic/operator-limited until site calibration and independent validation are supplied."
        ),
    }


__all__ = ["build_native_packet_coverage_ledger"]
