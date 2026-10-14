"""Audit the termination evidence available for vertical-handoff releases.

The vertical-handoff campaign can produce a valid numerical state history while
still ending at a diagnostic time horizon.  This module keeps that distinction
explicit: a packet is discoverable evidence, but it is not a release boundary
unless its provider-owned termination basis is reviewed and closed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


_SUPPORTED_BOUNDARIES = {
    "reviewed_isolation_success",
    "inventory_depletion",
    "inventory_depletion_positive_threshold",
    "inventory_depletion_releasable_mass",
    "model_pressure_equalization",
}


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _event_suffix(event_id: str) -> str:
    """Return the stable area-bin suffix used by the rebound campaign."""

    marker = "/terminal-valve/"
    return event_id.split(marker, 1)[1] if marker in event_id else event_id.rsplit("/", 1)[-1]


def build_vertical_termination_evidence_search(
    vertical_catalog_dir: str | Path,
    *,
    vertical_chain_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Scan persisted vertical packets and classify termination evidence.

    ``vertical_catalog_dir`` is expected to contain an ``events``-like set of
    area-bin directories.  The report is deliberately advisory: it never
    changes the release-boundary catalog or promotes a synthetic packet.
    """

    root = Path(vertical_catalog_dir)
    event_dirs = root / "events"
    if event_dirs.is_dir():
        candidates = sorted(path for path in event_dirs.iterdir() if path.is_dir())
    elif any(path.is_dir() for path in root.iterdir()) if root.is_dir() else False:
        candidates = sorted(path for path in root.iterdir() if path.is_dir())
    else:
        # The historic all-bin vertical export stores the five event files in
        # one directory.  Treat it as the same packet inventory.
        candidates = [root]

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for event_dir in candidates:
        # Historic all-bin exports keep a representative ``resolved_release``
        # beside the five-row catalog.  Prefer the catalog so every area bin is
        # audited instead of silently inspecting only the representative row.
        if event_dir == root and (root / "resolved_release_catalog.json").exists():
            try:
                catalog = _read_json(root / "resolved_release_catalog.json")
                campaign_verification = (
                    _read_json(root / "verification.json")
                    if (root / "verification.json").exists()
                    else {}
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{root}: {exc}")
                continue
            for event_id, release in catalog.items():
                if not isinstance(release, Mapping):
                    errors.append(f"{event_id}: release row is not an object")
                    continue
                rows.append(
                    _classify_row(
                        event_id,
                        release,
                        campaign_verification,
                        root / "resolved_release_catalog.json",
                        root / "verification.json",
                    )
                )
            continue
        packet_path = event_dir / "resolved_release.json"
        verification_path = event_dir / "verification.json"
        if not packet_path.exists() or not verification_path.exists():
            # A single-directory catalog is represented by a resolved-release
            # catalog; expand it below when present.
            errors.append(f"{event_dir.name}: resolved_release.json or verification.json is missing")
            continue
        try:
            packet = _read_json(packet_path)
            verification = _read_json(verification_path)
            event_id = packet.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                errors.append(f"{event_dir.name}: event_id is missing")
                continue
            rows.append(_classify_row(event_id, packet, verification, packet_path, verification_path))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{event_dir.name}: {exc}")

    rebound_rows = []
    if isinstance(vertical_chain_audit, Mapping):
        rebound_rows = [row for row in vertical_chain_audit.get("event_rows", []) if isinstance(row, Mapping)]
    rebound_by_suffix = {
        _event_suffix(str(row.get("event_id"))): row
        for row in rebound_rows
        if isinstance(row.get("event_id"), str)
    }
    for row in rows:
        rebound = rebound_by_suffix.get(_event_suffix(str(row.get("source_event_id") or row.get("event_id"))))
        if rebound is not None:
            row["facility_event_id"] = rebound.get("event_id")
            row["facility_case_count"] = rebound.get("case_count")
            row["facility_chain_status"] = rebound.get("status")
        else:
            row["facility_event_id"] = None
            row["facility_case_count"] = None
            row["facility_chain_status"] = "UNBOUND"

    not_supplied = [row for row in rows if row["status"] == "NOT_SUPPLIED"]
    valid = [row for row in rows if row["status"] == "VALID"]
    expected_case_count = sum(
        int(row.get("facility_case_count") or 0)
        for row in rows
        if isinstance(row.get("facility_case_count"), int)
    )
    if not expected_case_count and isinstance(vertical_chain_audit, Mapping):
        expected_case_count = int(vertical_chain_audit.get("vertical_case_count") or 0)
    return {
        "schema_version": "prism.vertical_termination_evidence_search.v1",
        "status": (
            "SEARCH_COMPLETE_EVIDENCE_OPEN"
            if rows and not errors and not valid
            else "SEARCH_COMPLETE_PARTIAL"
            if rows
            else "SEARCH_OPEN"
        ),
        "source_root": str(root),
        "source_catalog_event_count": len(rows),
        "source_catalog_case_count": expected_case_count,
        "valid_termination_event_count": len(valid),
        "not_supplied_event_count": len(not_supplied),
        "not_supplied_case_count": sum(
            int(row.get("facility_case_count") or 0) for row in not_supplied
        ),
        "errors": list(dict.fromkeys(errors)),
        "promotion": {
            "release_boundary_catalog_updated": False,
            "facility_qra_promoted": False,
            "frequency_inferred": False,
            "physical_validation_claim": False,
        },
        "interpretation": (
            "Vertical packets were found and their provider termination basis was read. "
            "A synthetic diagnostic horizon is retained as NOT_SUPPLIED; duration and "
            "mass integration are not converted into isolation success or inventory depletion."
        ),
        "rows": rows,
    }


def _classify_row(
    event_id: str,
    packet: Mapping[str, Any],
    verification: Mapping[str, Any],
    packet_path: Path,
    verification_path: Path,
) -> dict[str, Any]:
    basis = packet.get("termination_basis")
    available = _finite(packet.get("available_mass_kg"))
    released = _finite(packet.get("cumulative_mass_out_kg"))
    residual = _finite(verification.get("mass_residual_max_kg"))
    provider_run_meta = verification.get("provider_run_meta")
    if isinstance(provider_run_meta, Mapping):
        if available is None:
            available = _finite(provider_run_meta.get("available_mass_kg"))
        if released is None:
            released = _finite(provider_run_meta.get("cumulative_mass_out_kg"))
        if residual is None:
            residual = _finite(provider_run_meta.get("max_abs_mass_residual_kg"))
    if residual is None:
        provider_mass = packet.get("provider_mass_balance")
        if isinstance(provider_mass, Mapping):
            residual = _finite(provider_mass.get("max_abs_mass_residual_kg"))
    valid = (
        basis in _SUPPORTED_BOUNDARIES
        and isinstance(packet.get("provider_result_digest"), str)
        and isinstance(packet.get("termination_provenance"), str)
        and residual is not None
        and abs(residual) <= 1e-9
    )
    reasons: list[str] = []
    if basis == "synthetic_diagnostic_horizon":
        reasons.extend(
            [
                "termination_basis_synthetic_diagnostic_horizon",
                "provider_history_ended_at_diagnostic_horizon",
            ]
        )
    elif basis not in _SUPPORTED_BOUNDARIES:
        reasons.append("termination_basis_not_supported_for_release_boundary")
    if not isinstance(packet.get("provider_result_digest"), str):
        reasons.append("provider_result_digest_missing")
    if not isinstance(packet.get("termination_provenance"), str):
        reasons.append("termination_provenance_missing")
    if residual is None:
        reasons.append("provider_mass_residual_missing")
    elif abs(residual) > 1e-9:
        reasons.append("provider_mass_residual_not_closed")
    if isinstance(packet.get("vertical_handoff"), Mapping):
        handoff_provenance = packet["vertical_handoff"].get("provenance")
        if isinstance(handoff_provenance, str) and "not independently validated" in handoff_provenance.lower():
            reasons.append("vertical_handoff_not_independently_validated")
    return {
        "event_id": event_id,
        "source_event_id": event_id,
        "component_id": packet.get("component_id"),
        "provider_result_digest": packet.get("provider_result_digest"),
        "termination_basis": basis,
        "duration_s": packet.get("duration_s"),
        "available_mass_kg": available,
        "cumulative_mass_out_kg": released,
        "mass_residual_kg": residual,
        "status": "VALID" if valid else "NOT_SUPPLIED",
        "blocking_reasons": list(dict.fromkeys(reasons)),
        "source": {
            "packet": str(packet_path),
            "verification": str(verification_path),
        },
    }


__all__ = ["build_vertical_termination_evidence_search"]
