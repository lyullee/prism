"""Audit the complete diagnostic path from a release packet to facility harm.

The facility ledger already validates each risk atom and the packet-binding
audit already checks provider aggregate values against a case.  This module
joins those checks in one event-level record and independently recomputes the
conditional facility IR/F-N contribution.  It is deliberately diagnostic:
qualified provider evidence, independent physical validation, and facility
QRA promotion remain separate gates.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
from typing import Any

from .facility_ledger import _fn_curve


CHAIN_CLOSURE_SCHEMA = "prism.facility_chain_closure_audit.v1"


class ChainClosureAuditError(ValueError):
    """Raised when a chain-closure input is malformed."""


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _same_number(left: Any, right: Any, *, rel_tol: float = 1.0e-8, abs_tol: float = 1.0e-12) -> bool:
    return _finite(left) and _finite(right) and math.isclose(
        float(left), float(right), rel_tol=rel_tol, abs_tol=abs_tol
    )


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ChainClosureAuditError(f"{label} must be an array")
    result = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ChainClosureAuditError(f"{label}[{index}] must be an object")
        result.append(row)
    return result


def _packet_rows(path: Path) -> list[Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ChainClosureAuditError(f"packet {path} must contain an object")
    if isinstance(payload.get("releases"), list):
        rows = payload["releases"]
    elif isinstance(payload.get("release_sets"), list):
        rows = [
            endpoint
            for release_set in payload["release_sets"]
            if isinstance(release_set, Mapping)
            for endpoint in release_set.get("releases", ())
        ]
    else:
        rows = [payload]
    return _rows(rows, f"packet {path} releases")


def _resolve_packet_path(packet_root: Path, raw: Any) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.replace("\\", "/")
    path = Path(text)
    if not path.is_absolute():
        path = packet_root / path
    return path.resolve()


def _identity_digests(value: Mapping[str, Any], key: str) -> tuple[str, ...]:
    raw = value.get(key, ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    return tuple(str(item) for item in raw if isinstance(item, str) and item)


def _packet_value_mismatches(
    packet_rows: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Compare provider aggregate values with every matching campaign case."""
    expected: dict[str, list[Mapping[str, Any]]] = {}
    for row in packet_rows:
        digest = row.get("provider_result_digest")
        if isinstance(digest, str) and digest:
            expected.setdefault(digest, []).append(row)
    mismatches: list[str] = []
    for case_index, case in enumerate(cases):
        identity = case.get("provider_packet_identity")
        if not isinstance(identity, Mapping):
            mismatches.append(f"case[{case_index}] missing provider_packet_identity")
            continue
        digests = _identity_digests(identity, "provider_result_digests")
        if not digests:
            mismatches.append(f"case[{case_index}] missing provider result digest")
            continue
        rows: list[Mapping[str, Any]] = []
        for digest in digests:
            rows.extend(expected.get(digest, ()))
        if len(rows) != len(digests):
            mismatches.append(f"case[{case_index}] provider result digest set does not match packet")
            continue
        for field in ("duration_s", "available_mass_kg", "cumulative_mass_out_kg"):
            packet_values = [row.get(field) for row in rows]
            case_values = identity.get(field)
            if not isinstance(case_values, Sequence) or isinstance(case_values, (str, bytes)):
                mismatches.append(f"case[{case_index}] missing identity {field}")
                continue
            if len(packet_values) != len(case_values) or any(
                not _same_number(left, right) for left, right in zip(packet_values, case_values)
            ):
                mismatches.append(f"case[{case_index}] {field} differs from packet")
        packet_bases = [row.get("termination_basis") for row in rows]
        case_bases = identity.get("termination_bases")
        if list(packet_bases) != list(case_bases or ()):
            mismatches.append(f"case[{case_index}] termination_bases differs from packet")
        packet_provenance = [row.get("termination_provenance") for row in rows]
        case_provenance = identity.get("termination_provenances")
        if list(packet_provenance) != list(case_provenance or ()):
            mismatches.append(f"case[{case_index}] termination_provenances differs from packet")
        termination = case.get("termination")
        if not isinstance(termination, Mapping) or not _same_number(
            termination.get("time_s"), max(float(row.get("duration_s")) for row in rows)
        ):
            mismatches.append(f"case[{case_index}] termination time differs from packet duration")
        mass_ledger = case.get("mass_ledger")
        if not isinstance(mass_ledger, Mapping) or not _same_number(
            mass_ledger.get("released_kg"),
            sum(float(row.get("cumulative_mass_out_kg")) for row in rows),
        ):
            mismatches.append(f"case[{case_index}] released mass differs from packet cumulative mass")
    return mismatches


def _atom_identity_matches_case(atom: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    for field in ("event_id", "annual_condition_id", "release_branch_id"):
        if atom.get(field) != case.get(field):
            return False
    atom_identity = atom.get("provider_packet_identity")
    case_identity = case.get("provider_packet_identity")
    return isinstance(atom_identity, Mapping) and isinstance(case_identity, Mapping) and (
        _identity_digests(atom_identity, "provider_result_digests")
        == _identity_digests(case_identity, "provider_result_digests")
    )


def _aggregate_ir(atoms: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    total: dict[str, list[float]] = {}
    for atom in atoms:
        frequency = float(atom["initiating_frequency_per_year"])
        weight = float(atom["conditional_weight"])
        harm = atom.get("receptor_harm_low_high")
        if not isinstance(harm, Mapping):
            continue
        for receptor_id, endpoints in harm.items():
            if not isinstance(endpoints, Sequence) or isinstance(endpoints, (str, bytes)) or len(endpoints) != 2:
                continue
            values = total.setdefault(str(receptor_id), [0.0, 0.0])
            values[0] += frequency * weight * float(endpoints[0])
            values[1] += frequency * weight * float(endpoints[1])
    return total


def _same_ir(left: Any, right: Mapping[str, Sequence[float]]) -> bool:
    if not isinstance(left, Mapping) or set(left) != set(right):
        return False
    return all(
        isinstance(left[key], Sequence)
        and not isinstance(left[key], (str, bytes))
        and len(left[key]) == 2
        and all(_same_number(left[key][index], right[key][index]) for index in range(2))
        for key in right
    )


def build_chain_closure_audit(
    campaign_result: Mapping[str, Any],
    *,
    packet_evidence: Mapping[str, Any] | None = None,
    packet_root: str | Path = ".",
) -> dict[str, Any]:
    """Return event-level release-to-facility closure evidence."""
    if not isinstance(campaign_result, Mapping):
        raise ChainClosureAuditError("campaign_result must be an object")
    events = _rows(campaign_result.get("events"), "campaign_result.events")
    cases = _rows(campaign_result.get("cases"), "campaign_result.cases")
    atoms = _rows(campaign_result.get("risk_atoms"), "campaign_result.risk_atoms")
    event_by_id = {str(row.get("id")): row for row in events if row.get("id")}
    cases_by_event: dict[str, list[Mapping[str, Any]]] = {}
    atoms_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in cases:
        if row.get("event_id"):
            cases_by_event.setdefault(str(row["event_id"]), []).append(row)
    for row in atoms:
        if row.get("event_id"):
            atoms_by_event.setdefault(str(row["event_id"]), []).append(row)

    packet_rows_by_event: dict[str, list[Mapping[str, Any]]] = {}
    packet_load_errors: dict[str, str] = {}
    packet_evidence_rows = []
    if packet_evidence is not None:
        if not isinstance(packet_evidence, Mapping):
            raise ChainClosureAuditError("packet_evidence must be an object")
        packet_evidence_rows = _rows(packet_evidence.get("rows"), "packet_evidence.rows")
        root = Path(packet_root).resolve()
        for row in packet_evidence_rows:
            event_id = str(row.get("event_id", ""))
            evidence = row.get("evidence")
            paths = evidence.get("resolved_packet_paths", ()) if isinstance(evidence, Mapping) else ()
            if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)):
                packet_load_errors[event_id] = "resolved_packet_paths missing"
                continue
            loaded: list[Mapping[str, Any]] = []
            for raw_path in paths:
                path = _resolve_packet_path(root, raw_path)
                if path is None or not path.is_file():
                    packet_load_errors[event_id] = f"packet file missing: {raw_path}"
                    continue
                try:
                    loaded.extend(_packet_rows(path))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ChainClosureAuditError) as error:
                    packet_load_errors[event_id] = str(error)
            if loaded:
                packet_rows_by_event[event_id] = loaded

    packet_expected_event_ids = {
        str(row.get("event_id"))
        for row in packet_evidence_rows
        if row.get("event_id")
    }
    event_rows: list[dict[str, Any]] = []
    packet_chain_closed = 0
    mismatch_event_ids: list[str] = []
    for event_id in sorted(event_by_id):
        event_cases = cases_by_event.get(event_id, [])
        event_atoms = atoms_by_event.get(event_id, [])
        packet_rows = packet_rows_by_event.get(event_id, [])
        packet_required = event_id in packet_expected_event_ids
        reasons: list[str] = []
        if packet_required:
            if not event_cases:
                reasons.append("no executed case")
            if not event_atoms:
                reasons.append("no risk atom")
            for case in event_cases:
                if not isinstance(case.get("termination"), Mapping):
                    reasons.append("case termination missing")
                if not isinstance(case.get("mass_ledger"), Mapping):
                    reasons.append("case mass ledger missing")
        if packet_required and not packet_rows:
            reasons.append(packet_load_errors.get(event_id, "no packet evidence"))
        if packet_rows and packet_required:
            reasons.extend(_packet_value_mismatches(packet_rows, event_cases))
        if event_cases and packet_required:
            for atom in event_atoms:
                if not any(_atom_identity_matches_case(atom, case) for case in event_cases):
                    reasons.append("risk atom provider/case identity mismatch")
                harm = atom.get("receptor_harm_low_high")
                deaths = atom.get("expected_deaths_low_high")
                if not isinstance(harm, Mapping) or not isinstance(deaths, Sequence) or len(deaths) != 2:
                    reasons.append("final damage fields missing")
        closed = not reasons
        if closed and packet_rows:
            packet_chain_closed += 1
        if reasons:
            mismatch_event_ids.append(event_id)
        if not packet_rows and not packet_required:
            status = "HANDOFF_OR_PACKET_MISSING"
        elif closed and packet_rows:
            status = "CLOSED_DIAGNOSTIC"
        else:
            status = "CHAIN_MISMATCH"
        event_rows.append({
            "event_id": event_id,
            "component_id": event_by_id[event_id].get("model_component_id"),
            "packet_row_count": len(packet_rows),
            "case_count": len(event_cases),
            "risk_atom_count": len(event_atoms),
            "status": status,
            "blocking_reasons": list(dict.fromkeys(reasons)),
            "qualified_provider_packet": False,
            "frequency_from_provider_packet": False,
        })

    aggregate_ir = _aggregate_ir(atoms)
    expected_ir = campaign_result.get("conditional_diagnostic_facility_annual_ir_low_high")
    if expected_ir is None:
        expected_ir = campaign_result.get("known_contribution_annual_ir_low_high")
    ir_closed = _same_ir(expected_ir, aggregate_ir)
    expected_fn = campaign_result.get("conditional_diagnostic_facility_expected_death_fn_low_high")
    fn_closed = (
        isinstance(expected_fn, list)
        and len(expected_fn) == 2
        and all(expected_fn[index] == _fn_curve(atoms, index) for index in range(2))
    )
    if not ir_closed:
        mismatch_event_ids.append("__facility_ir_aggregate__")
    if not fn_closed:
        mismatch_event_ids.append("__facility_fn_aggregate__")

    unique_mismatches = list(dict.fromkeys(mismatch_event_ids))
    packet_event_ids = set(packet_rows_by_event)
    status = (
        "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED"
        if packet_event_ids
        and packet_chain_closed == len(packet_event_ids)
        and not unique_mismatches
        else "BLOCKED_CHAIN_CLOSURE"
    )
    return {
        "schema_version": CHAIN_CLOSURE_SCHEMA,
        "status": status,
        "facility_id": campaign_result.get("facility_id"),
        "campaign_event_count": len(events),
        "campaign_case_count": len(cases),
        "campaign_risk_atom_count": len(atoms),
        "packet_event_count": len(packet_event_ids),
        "packet_chain_closed_event_count": packet_chain_closed,
        "packet_chain_mismatch_event_count": len(unique_mismatches),
        "packet_chain_mismatch_event_ids": unique_mismatches,
        "campaign_events_without_packet_count": len(set(event_by_id) - packet_event_ids),
        "event_rows": event_rows,
        "facility_ir_aggregate_closed": ir_closed,
        "facility_fn_aggregate_closed": fn_closed,
        "facility_total_risk_available": campaign_result.get("facility_total_risk_available") is True,
        "complete_facility_qra_claim": campaign_result.get("complete_facility_qra_claim") is True,
        "qualified_provider_packet_count": (
            packet_evidence.get("qualified_provider_packet_count")
            if isinstance(packet_evidence, Mapping)
            else None
        ),
        "frequency_from_provider_packet": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "The event rows prove that packet release aggregates reached termination/inventory "
            "cases, risk atoms carried final harm fields, and the conditional facility IR/F-N "
            "sum was independently recomputed. Missing handoff packets, provider qualification, "
            "scope completeness, and physical validation remain promotion gates."
        ),
    }


__all__ = ["CHAIN_CLOSURE_SCHEMA", "ChainClosureAuditError", "build_chain_closure_audit"]
