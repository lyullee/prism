"""Fail-closed consistency verification for the latest IJHE audit pointer.

This module verifies that the status ledger points to a real audit record, that
its summary counts agree with the stored checks, and that the inspection-center
facility handoff remains diagnostic-only. It never promotes a facility QRA.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "prism.latest_ijhe_audit_verification.v1"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _relative_or_absolute(path_value: str, *, root: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else root / path


def verify_latest_ijhe_audit(
    current_status: Mapping[str, Any] | Path,
    *,
    root: Path | None = None,
    audit: Mapping[str, Any] | Path | None = None,
    handoff: Mapping[str, Any] | Path | None = None,
    receptor_geometry: Mapping[str, Any] | Path | None = None,
    scope_matrix: Mapping[str, Any] | Path | None = None,
    release_boundary: Mapping[str, Any] | Path | None = None,
    facility_qra_gate_summary: Mapping[str, Any] | Path | None = None,
    release_closure_worklist: Mapping[str, Any] | Path | None = None,
    native_external_multi_equipment_recheck: Mapping[str, Any] | Path | None = None,
    native_external_clean_full_scope_replay: Mapping[str, Any] | Path | None = None,
    native_external_clean_full_scope_isolation_replay: Mapping[str, Any] | Path | None = None,
) -> dict[str, Any]:
    """Verify status/audit/handoff identity without changing qualification gates."""

    base = Path(root or Path.cwd()).resolve()
    status = _read_object(current_status) if isinstance(current_status, Path) else dict(current_status)
    record_value = status.get("latest_ijhe_completion_audit_record")
    reasons: list[str] = []
    if not isinstance(record_value, str) or not record_value.strip():
        reasons.append("current status has no latest_ijhe_completion_audit_record")
        record_path = base / "__missing_latest_audit__.json"
    else:
        record_path = _relative_or_absolute(record_value, root=base)

    if audit is None:
        if record_path.exists():
            audit_value = _read_object(record_path)
        else:
            audit_value = {}
    elif isinstance(audit, Path):
        audit_value = _read_object(audit)
    else:
        audit_value = dict(audit)

    checks = audit_value.get("checks")
    blockers = audit_value.get("blocking_reasons")
    if not isinstance(checks, list):
        reasons.append("latest audit checks must be a list")
        checks = []
    if not isinstance(blockers, list):
        reasons.append("latest audit blocking_reasons must be a list")
        blockers = []
    pass_count = sum(item.get("status") == "PASS" for item in checks if isinstance(item, Mapping))
    blocked_check_count = sum(item.get("status") == "BLOCKED" for item in checks if isinstance(item, Mapping))
    expected_count = status.get("latest_ijhe_completion_audit_check_count")
    expected_blocker_count = status.get("latest_ijhe_completion_audit_blocking_reason_count")
    if expected_count != len(checks):
        reasons.append(f"status check count {expected_count!r} does not match audit count {len(checks)}")
    if expected_blocker_count != len(blockers):
        reasons.append(f"status blocker count {expected_blocker_count!r} does not match audit count {len(blockers)}")
    if audit_value.get("status") != status.get("latest_ijhe_completion_audit_status", "").split(";", 1)[0]:
        reasons.append("status summary and audit status disagree")
    if audit_value.get("complete_facility_qra_claim") is not False:
        reasons.append("latest audit must keep complete_facility_qra_claim=false")
    if audit_value.get("physical_validation_claim") is not False:
        reasons.append("latest audit must keep physical_validation_claim=false")

    handoff_value: dict[str, Any]
    if handoff is None:
        handoff_path_value = status.get("inspection_center_facility_ijhe_handoff_audit_record")
        handoff_path = (
            _relative_or_absolute(handoff_path_value, root=base)
            if isinstance(handoff_path_value, str)
            else base / "__missing_handoff__.json"
        )
        handoff_value = _read_object(handoff_path) if handoff_path.exists() else {}
    elif isinstance(handoff, Path):
        handoff_path = handoff
        handoff_value = _read_object(handoff)
    else:
        handoff_path = None
        handoff_value = dict(handoff)
    handoff_checks = handoff_value.get("checks")
    if handoff_value.get("schema_version") != "prism.inspection_center_facility_ijhe_audit.v1":
        reasons.append("facility handoff schema is not the declared PRISM schema")
    if handoff_value.get("status") != "PASS_WITH_SCOPE_LIMITATIONS":
        reasons.append("facility handoff status is not PASS_WITH_SCOPE_LIMITATIONS")
    if not isinstance(handoff_checks, list) or not handoff_checks or any(
        not isinstance(item, Mapping) or item.get("status") != "PASS" for item in handoff_checks
    ):
        reasons.append("facility handoff checks are not all PASS")
    boundary = handoff_value.get("qualification_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("facility_ir_fn_available") is not False or boundary.get("physical_validation_claim") is not False:
        reasons.append("facility handoff qualification boundary is not fail-closed")

    geometry_value: dict[str, Any] = {}
    geometry_path: Path | None = None
    geometry_pointer = status.get("receptor_geometry_interpretation_record")
    if receptor_geometry is None and isinstance(geometry_pointer, str):
        geometry_path = _relative_or_absolute(geometry_pointer, root=base)
        geometry_value = _read_object(geometry_path) if geometry_path.exists() else {}
    elif isinstance(receptor_geometry, Path):
        geometry_path = receptor_geometry
        geometry_value = _read_object(receptor_geometry)
    elif isinstance(receptor_geometry, Mapping):
        geometry_value = dict(receptor_geometry)
    if geometry_pointer is not None or receptor_geometry is not None:
        if geometry_value.get("schema_version") != "prism.receptor_geometry_interpretation.v1":
            reasons.append("receptor geometry interpretation schema is not the declared PRISM schema")
        if geometry_value.get("status") != "PASS_DIAGNOSTIC_ONLY":
            reasons.append("receptor geometry interpretation is not PASS_DIAGNOSTIC_ONLY")
        geometry_checks = geometry_value.get("checks")
        if not isinstance(geometry_checks, list) or not geometry_checks or any(
            not isinstance(item, Mapping) or item.get("status") != "PASS" for item in geometry_checks
        ):
            reasons.append("receptor geometry interpretation checks are not all PASS")
        promotion = geometry_value.get("promotion_boundary")
        if not isinstance(promotion, Mapping) or any(
            promotion.get(key) is not False
            for key in ("facility_total_risk_claim", "facility_qra_claim", "physical_validation_claim")
        ):
            reasons.append("receptor geometry interpretation promotion boundary is not fail-closed")

    # Bind the latest facility-level scope and release-boundary ledgers when
    # the current status ledger exposes their pointers.  These are diagnostic
    # consistency checks only: a numerically executed row is never promoted to
    # qualified provider evidence or facility QRA here.
    def _load_optional(
        supplied: Mapping[str, Any] | Path | None,
        pointer_keys: tuple[str, ...],
    ) -> tuple[dict[str, Any], Path | None, bool]:
        if supplied is not None:
            if isinstance(supplied, Path):
                return _read_object(supplied), supplied, True
            return dict(supplied), None, True
        for key in pointer_keys:
            pointer = status.get(key)
            if isinstance(pointer, str) and pointer.strip():
                path = _relative_or_absolute(pointer, root=base)
                if not path.exists():
                    reasons.append(f"{key} does not exist")
                    return {}, path, True
                return _read_object(path), path, True
        return {}, None, False

    scope_value, scope_path, scope_present = _load_optional(
        scope_matrix,
        ("latest_union_scope_matrix_record", "scope_matrix_latest_record"),
    )
    release_value, release_path, release_present = _load_optional(
        release_boundary,
        ("latest_release_boundary_case_audit",),
    )
    gate_value, gate_path, gate_present = _load_optional(
        facility_qra_gate_summary,
        ("facility_qra_gate_summary_record",),
    )
    if scope_present:
        if scope_value.get("schema_version") != "prism.major_accident_scope.v1":
            reasons.append("latest facility scope matrix schema is not the declared PRISM schema")
        if not isinstance(scope_value.get("rows"), list) or not scope_value.get("rows"):
            reasons.append("latest facility scope matrix has no family rows")
        if not isinstance(scope_value.get("conditional_chain_complete"), bool):
            reasons.append("latest facility scope matrix conditional-chain flag is missing")
        if scope_value.get("facility_total_risk_available") is not False:
            reasons.append("latest facility scope matrix must keep facility_total_risk_available=false")
        if scope_value.get("physical_validation_claim") is not False:
            reasons.append("latest facility scope matrix must keep physical_validation_claim=false")
        expected_cases = status.get("latest_union_case_count")
        if expected_cases is not None and scope_value.get("case_count") != expected_cases:
            reasons.append("latest facility scope matrix case count disagrees with status ledger")
    if gate_present:
        if gate_value.get("schema_version") != "prism.facility_qra_gate_summary.v1":
            reasons.append("latest facility QRA gate summary schema is not the declared PRISM schema")
        embedded_gate = next(
            (
                item
                for item in checks
                if isinstance(item, Mapping)
                and item.get("name") == "facility_qra_gate_summary"
            ),
            None,
        )
        embedded_evidence = (
            embedded_gate.get("evidence")
            if isinstance(embedded_gate, Mapping)
            else None
        )
        if not isinstance(embedded_evidence, Mapping):
            reasons.append("latest audit has no embedded facility QRA gate summary evidence")
        else:
            source_gates = gate_value.get("gates")
            source_gate_names = (
                sorted(source_gates.keys())
                if isinstance(source_gates, Mapping)
                else None
            )
            expected_incomplete = (
                sum(not row.get("complete", False) for row in source_gates.values())
                if isinstance(source_gates, Mapping)
                else None
            )
            comparisons = {
                "status": gate_value.get("status"),
                "promotion_allowed": gate_value.get("promotion_allowed"),
                "facility_qra_claim": gate_value.get("facility_qra_claim"),
                "gate_names": source_gate_names,
                "incomplete_gate_count": expected_incomplete,
                "blocking_reason_count": (
                    len(gate_value.get("blocking_reasons", []))
                    if isinstance(gate_value.get("blocking_reasons"), list)
                    else None
                ),
            }
            for key, expected in comparisons.items():
                if embedded_evidence.get(key) != expected:
                    reasons.append(
                        f"latest audit embedded facility QRA gate {key} disagrees with source summary"
                    )
    if release_present:
        if release_value.get("schema_version") != "prism.release_boundary_case_audit.v1":
            reasons.append("latest release-boundary audit schema is not the declared PRISM schema")
        if release_value.get("facility_ir_fn_promotion") is not False:
            reasons.append("latest release-boundary audit must keep facility_ir_fn_promotion=false")
        if release_value.get("provider_qualification_claim") is not False:
            reasons.append("latest release-boundary audit must keep provider_qualification_claim=false")
        if release_value.get("independent_physical_validation_claim") is not False:
            reasons.append("latest release-boundary audit must keep independent_physical_validation_claim=false")
        expected_cases = status.get("latest_union_case_count")
        if expected_cases is not None and release_value.get("case_count") != expected_cases:
            reasons.append("latest release-boundary audit case count disagrees with status ledger")
        for status_key, audit_key in (
            ("latest_ijhe_completion_audit_release_boundary_eligible_case_count", "strict_release_boundary_eligible_case_count"),
            ("latest_ijhe_completion_audit_release_boundary_blocked_case_count", "strict_release_boundary_blocked_case_count"),
        ):
            expected = status.get(status_key)
            if expected is not None and release_value.get(audit_key) != expected:
                reasons.append(f"latest release-boundary audit {audit_key} disagrees with status ledger")
        # Newer release audits include a per-case evidence-request contract
        # check.  Consume it when present while keeping historical records
        # readable; a blocked contract must never be mistaken for aligned
        # evidence coverage.
        if "facility_evidence_request_contract_blocked_case_count" in release_value:
            if release_value.get("facility_evidence_request_contract_blocked_case_count") != 0:
                reasons.append("latest release-boundary audit has blocked evidence-request contracts")
            contract_counts = release_value.get(
                "facility_evidence_request_contract_status_counts"
            )
            if not isinstance(contract_counts, Mapping) or contract_counts.get("BLOCKED", 0) != 0:
                reasons.append("latest release-boundary audit evidence-request contract status is not aligned")
        if "asset_summary" in release_value:
            asset_summary = release_value.get("asset_summary")
            if not isinstance(asset_summary, Mapping) or not asset_summary:
                reasons.append("latest release-boundary audit asset summary is missing")
            else:
                asset_case_count = sum(
                    int(value.get("case_count", -1))
                    for value in asset_summary.values()
                    if isinstance(value, Mapping)
                )
                asset_eligible_count = sum(
                    int(value.get("strict_release_boundary_eligible_case_count", -1))
                    for value in asset_summary.values()
                    if isinstance(value, Mapping)
                )
                asset_blocked_count = sum(
                    int(value.get("strict_release_boundary_blocked_case_count", -1))
                    for value in asset_summary.values()
                    if isinstance(value, Mapping)
                )
                if asset_case_count != release_value.get("case_count"):
                    reasons.append("latest release-boundary asset summary case count disagrees")
                if asset_eligible_count != release_value.get("strict_release_boundary_eligible_case_count"):
                    reasons.append("latest release-boundary asset summary eligible count disagrees")
                if asset_blocked_count != release_value.get("strict_release_boundary_blocked_case_count"):
                    reasons.append("latest release-boundary asset summary blocked count disagrees")

        # The completion audit also embeds a case-level release-boundary
        # snapshot.  Check that snapshot against the pointed artifact instead
        # of trusting a stale copied summary.  This is metadata consistency
        # only; it never changes the qualification gate.
        embedded_boundary = next(
            (
                item
                for item in checks
                if isinstance(item, Mapping)
                and item.get("name") == "diagnostic_release_boundary_case_audit"
            ),
            None,
        )
        if isinstance(embedded_boundary, Mapping):
            embedded = embedded_boundary.get("evidence")
            if isinstance(embedded, Mapping):
                for key in (
                    "case_count",
                    "strict_release_boundary_eligible_case_count",
                    "strict_release_boundary_blocked_case_count",
                    "provider_termination_evidence_status_counts",
                    "provider_termination_evidence_used_case_count",
                ):
                    if key in embedded and embedded.get(key) != release_value.get(key):
                        reasons.append(
                            f"latest audit embedded release-boundary {key} disagrees with source ledger"
                        )

        embedded_trace = next(
            (
                item
                for item in checks
                if isinstance(item, Mapping)
                and item.get("name") == "diagnostic_conditional_facility_release_trace"
            ),
            None,
        )
        if isinstance(embedded_trace, Mapping):
            embedded = embedded_trace.get("evidence")
            trace_record = (
                embedded.get("record")
                if isinstance(embedded, Mapping)
                else None
            )
            trace_path = (
                _relative_or_absolute(trace_record, root=base)
                if isinstance(trace_record, str) and trace_record.strip()
                else None
            )
            trace_value = _read_object(trace_path) if trace_path and trace_path.exists() else None
            source_summary = (
                trace_value.get("release_trace", {}).get("summary")
                if isinstance(trace_value, Mapping)
                and isinstance(trace_value.get("release_trace"), Mapping)
                else None
            )
            embedded_summary = (
                embedded.get("summary")
                if isinstance(embedded, Mapping)
                else None
            )
            if isinstance(source_summary, Mapping) and isinstance(embedded_summary, Mapping):
                for key in (
                    "case_count",
                    "strict_release_boundary_eligible_case_count",
                    "strict_release_boundary_blocked_case_count",
                    "numerically_closed_case_count",
                    "numerically_open_case_count",
                    "operator_review_required_case_count",
                    "consequence_domain_truncated_case_count",
                    "numerical_closure_status_counts",
                    "consequence_domain_status_counts",
                    "facility_ir_fn_promotion",
                    "risk_atom_count",
                ):
                    if key in embedded_summary and embedded_summary.get(key) != source_summary.get(key):
                        reasons.append(
                            f"latest audit embedded release-trace {key} disagrees with source ledger"
                        )

    # Keep the release-closure worklist pointer synchronized with the current
    # facility assessment. This is a diagnostic consistency check only: an
    # open worklist remains open and never promotes a provider or facility QRA.
    closure_value, closure_path, closure_present = _load_optional(
        release_closure_worklist,
        ("v060_release_closure_worklist",),
    )
    closure_sha256 = None
    if closure_present:
        if closure_value.get("schema_version") != "prism.release_closure_worklist.v1":
            reasons.append("release-closure worklist schema is not the declared PRISM schema")
        cases = closure_value.get("cases")
        case_count = closure_value.get("case_count")
        open_case_count = closure_value.get("open_case_count")
        if not isinstance(cases, list) or not isinstance(case_count, int) or len(cases) != case_count:
            reasons.append("release-closure worklist case list/count is inconsistent")
        if not isinstance(open_case_count, int) or not isinstance(case_count, int) or not (
            0 <= open_case_count <= case_count
        ):
            reasons.append("release-closure worklist open_case_count is invalid")
        summary = closure_value.get("summary")
        if not isinstance(summary, Mapping):
            reasons.append("release-closure worklist summary is missing")
        else:
            for field in (
                "mass_closure_open_case_count",
                "isolation_open_case_count",
                "termination_open_case_count",
                "inventory_closure_open_case_count",
            ):
                if field in closure_value and summary.get(field) != closure_value.get(field):
                    reasons.append(f"release-closure worklist {field} disagrees with summary")
            # Newer worklists optionally join the case-level release-boundary
            # audit.  Validate the join accounting when present, while
            # retaining compatibility with older worklist snapshots.
            if "boundary_audit_join_case_count" in summary:
                join_count = summary.get("boundary_audit_join_case_count")
                unmatched_count = summary.get("boundary_audit_unmatched_case_count")
                duplicate_count = summary.get("boundary_audit_duplicate_key_count")
                numerical_counts = summary.get("numerical_closure_status_counts")
                evidence_counts = summary.get(
                    "provider_termination_evidence_status_counts"
                )
                numerical_closed = summary.get("numerically_closed_case_count")
                numerical_open = summary.get("numerically_open_case_count")
                operator_review = summary.get("operator_review_required_case_count")
                strict_eligible = summary.get(
                    "strict_release_boundary_eligible_case_count"
                )
                strict_blocked = summary.get(
                    "strict_release_boundary_blocked_case_count"
                )
                integer_fields = {
                    "boundary_audit_join_case_count": join_count,
                    "boundary_audit_unmatched_case_count": unmatched_count,
                    "boundary_audit_duplicate_key_count": duplicate_count,
                    "numerically_closed_case_count": numerical_closed,
                    "numerically_open_case_count": numerical_open,
                    "operator_review_required_case_count": operator_review,
                    "strict_release_boundary_eligible_case_count": strict_eligible,
                    "strict_release_boundary_blocked_case_count": strict_blocked,
                }
                if any(
                    not isinstance(value, int) or value < 0
                    for value in integer_fields.values()
                ):
                    reasons.append("release-closure boundary-join summary has invalid counts")
                if isinstance(join_count, int) and join_count != case_count:
                    reasons.append("release-closure boundary-join count disagrees with case_count")
                if isinstance(unmatched_count, int) and unmatched_count != 0:
                    reasons.append("release-closure boundary-join has unmatched cases")
                if isinstance(duplicate_count, int) and duplicate_count != 0:
                    reasons.append("release-closure boundary-join has duplicate keys")
                if not isinstance(numerical_counts, Mapping) or not isinstance(
                    evidence_counts, Mapping
                ):
                    reasons.append("release-closure boundary-join status counts are missing")
                else:
                    numerical_total = sum(
                        value for value in numerical_counts.values()
                        if isinstance(value, int) and value >= 0
                    )
                    evidence_total = sum(
                        value for value in evidence_counts.values()
                        if isinstance(value, int) and value >= 0
                    )
                    if numerical_total != join_count or evidence_total != join_count:
                        reasons.append(
                            "release-closure boundary-join status counts do not cover every case"
                        )
                    if all(
                        isinstance(value, int) and value >= 0
                        for value in (
                            join_count,
                            numerical_closed,
                            numerical_open,
                            operator_review,
                            strict_eligible,
                            strict_blocked,
                        )
                    ):
                        if numerical_closed + numerical_open != join_count:
                            reasons.append(
                                "release-closure numerical closed/open counts do not cover every case"
                            )
                        if operator_review > numerical_closed:
                            reasons.append(
                                "release-closure operator-review count exceeds numerical closure count"
                            )
                        if strict_eligible + strict_blocked != join_count:
                            reasons.append(
                                "release-closure strict eligible/blocked counts do not cover every case"
                            )
                joined_rows = [
                    row.get("boundary_audit_join")
                    for row in cases
                    if isinstance(row, Mapping)
                    and isinstance(row.get("boundary_audit_join"), Mapping)
                    and row["boundary_audit_join"].get("matched") is True
                ]
                if isinstance(join_count, int) and len(joined_rows) != join_count:
                    reasons.append(
                        "release-closure boundary-join row count disagrees with summary"
                    )
                if not isinstance(closure_value.get("boundary_audit_record"), str):
                    reasons.append("release-closure boundary-audit record pointer is missing")
        promotion = closure_value.get("promotion_gates")
        if not isinstance(promotion, Mapping) or any(
            promotion.get(key) is not False
            for key in (
                "release_boundary_promotion_allowed",
                "frequency_inference_allowed",
                "facility_qra_allowed",
                "physical_validation_claim",
            )
        ):
            reasons.append("release-closure worklist promotion gates are not fail-closed")
        if closure_path is not None and closure_path.exists():
            closure_sha256 = hashlib.sha256(closure_path.read_bytes()).hexdigest().upper()
            expected_sha = status.get("v060_release_closure_worklist_sha256")
            if isinstance(expected_sha, str) and expected_sha.strip() and expected_sha.upper() != closure_sha256:
                reasons.append("status release-closure worklist SHA-256 disagrees with the pointed file")

    # The clean-source native multi-equipment replay is a supplemental
    # diagnostic record.  Bind it to the current status ledger when present,
    # but keep every qualification boundary fail-closed: a replay is evidence
    # that the adapters execute, not a qualified provider packet, frequency,
    # physical-validation result, or facility QRA.
    native_recheck_value: dict[str, Any] = {}
    native_recheck_path: Path | None = None
    native_recheck_pointer = status.get(
        "external_lh2dt_native_multi_equipment_recheck_compact_record"
    )
    if native_external_multi_equipment_recheck is None and isinstance(
        native_recheck_pointer, str
    ):
        native_recheck_path = _relative_or_absolute(native_recheck_pointer, root=base)
        if not native_recheck_path.exists():
            reasons.append(
                "native external multi-equipment recheck record does not exist"
            )
        else:
            native_recheck_value = _read_object(native_recheck_path)
    elif isinstance(native_external_multi_equipment_recheck, Path):
        native_recheck_path = native_external_multi_equipment_recheck
        native_recheck_value = _read_object(native_recheck_path)
    elif isinstance(native_external_multi_equipment_recheck, Mapping):
        native_recheck_value = dict(native_external_multi_equipment_recheck)
    if native_recheck_pointer is not None or native_external_multi_equipment_recheck is not None:
        rows = native_recheck_value.get("equipment")
        row_valid = isinstance(rows, list) and all(
            isinstance(row, Mapping)
            and row.get("status") == "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC"
            and row.get("state_snapshot_digest_match") is True
            for row in rows
        )
        names = [row.get("equipment") for row in rows] if isinstance(rows, list) else []
        dynamic_rows = [
            row.get("dynamic_state_closure")
            for row in rows
            if isinstance(row, Mapping) and row.get("dynamic_state_closure") is not None
        ] if isinstance(rows, list) else []
        dynamic_valid = all(
            isinstance(row, Mapping)
            and row.get("declared_by_provider") is True
            and row.get("prism_source_dynamics_status") == "READY"
            and row.get("ready") is True
            and row.get("blocking_reasons") == []
            for row in dynamic_rows
        )
        expected_equipment_count = native_recheck_value.get("equipment_count")
        native_recheck_valid = (
            native_recheck_value.get("schema_version")
            == "prism.native_external_multi_equipment_recheck_compact.v1"
            and native_recheck_value.get("status")
            == "NATIVE_EXTERNAL_MULTI_EQUIPMENT_RECHECK_EXECUTED_DIAGNOSTIC"
            and isinstance(expected_equipment_count, int)
            and expected_equipment_count > 0
            and isinstance(rows, list)
            and len(rows) == expected_equipment_count
            and len(set(names)) == len(names)
            and row_valid
            and dynamic_valid
            and isinstance(native_recheck_value.get("source_repository"), str)
            and bool(native_recheck_value.get("source_repository"))
            and isinstance(native_recheck_value.get("source_commit"), str)
            and bool(native_recheck_value.get("source_commit"))
            and isinstance(native_recheck_value.get("external_source_digest"), str)
            and bool(native_recheck_value.get("external_source_digest"))
            and native_recheck_value.get("provider_packet_promoted_count") == 0
            and native_recheck_value.get("physical_validation_claim") is False
            and native_recheck_value.get("frequency_inference_performed") is False
            and native_recheck_value.get("facility_qra_claim") is False
        )
        if not native_recheck_valid:
            reasons.append(
                "native external multi-equipment recheck is malformed or permits unsafe promotion"
            )
        for status_key, record_key in (
            (
                "external_lh2dt_native_multi_equipment_recheck_compact_source_digest",
                "external_source_digest",
            ),
            (
                "external_lh2dt_native_multi_equipment_recheck_compact_dynamic_closure_ready_count",
                "dynamic_closure_ready_count",
            ),
            (
                "external_lh2dt_native_multi_equipment_recheck_compact_provider_packet_promoted_count",
                "provider_packet_promoted_count",
            ),
            (
                "external_lh2dt_native_multi_equipment_recheck_compact_facility_qra_claim",
                "facility_qra_claim",
            ),
        ):
            expected = status.get(status_key)
            if expected is None:
                continue
            if record_key == "dynamic_closure_ready_count":
                actual = sum(
                    isinstance(row, Mapping)
                    and isinstance(row.get("dynamic_state_closure"), Mapping)
                    and row["dynamic_state_closure"].get("ready") is True
                    for row in rows
                ) if isinstance(rows, list) else None
            else:
                actual = native_recheck_value.get(record_key)
            if actual != expected:
                reasons.append(
                    f"status ledger {status_key} disagrees with native external recheck"
                )

    # Bind the fresh exporter/chain comparison when the status ledger points
    # to one.  This is provenance evidence only: it proves reproducibility of
    # the diagnostic replay and never promotes a provider packet or facility
    # QRA result.
    native_comparison_value: dict[str, Any] = {}
    native_comparison_path: Path | None = None
    native_comparison_pointer = status.get(
        "external_lh2dt_native_multi_equipment_recheck_comparison_record"
    )
    if isinstance(native_comparison_pointer, str):
        native_comparison_path = _relative_or_absolute(native_comparison_pointer, root=base)
        if not native_comparison_path.exists():
            reasons.append(
                "native external multi-equipment comparison record does not exist"
            )
        else:
            native_comparison_value = _read_object(native_comparison_path)
        rows = native_comparison_value.get("rows")
        comparison_valid = (
            native_comparison_value.get("schema_version")
            == "prism.native_external_multi_equipment_recheck_comparison.v1"
            and native_comparison_value.get("status")
            == "MATCHED_CURRENT_EXTERNAL_SOURCE_AND_CHAIN"
            and isinstance(native_comparison_value.get("equipment_count"), int)
            and native_comparison_value.get("equipment_count") > 0
            and isinstance(rows, list)
            and len(rows) == native_comparison_value.get("equipment_count")
            and all(
                isinstance(row, Mapping)
                and row.get("provider_result_digest_match") is True
                and row.get("termination_basis_match") is True
                and row.get("duration_match") is True
                and row.get("state_snapshot_digest_match_old") is True
                and row.get("state_snapshot_digest_match_new") is True
                and row.get("chain_status_match") is True
                and row.get("chain_provider_duration_match") is True
                and row.get("chain_mass_residual_match") is True
                for row in rows
            )
            and native_comparison_value.get("all_provider_result_digests_match") is True
            and native_comparison_value.get("all_chain_statuses_match") is True
            and native_comparison_value.get("all_chain_durations_match") is True
            and native_comparison_value.get("all_mass_residuals_match") is True
            and native_comparison_value.get("provider_packet_promoted_count") == 0
            and native_comparison_value.get("physical_validation_claim") is False
            and native_comparison_value.get("frequency_inference_performed") is False
            and native_comparison_value.get("facility_qra_claim") is False
        )
        if native_recheck_value.get("external_source_digest") and native_comparison_value.get(
            "external_source_digest"
        ) != native_recheck_value.get("external_source_digest"):
            comparison_valid = False
            reasons.append(
                "native external recheck comparison source digest disagrees with compact recheck"
            )
        if not comparison_valid:
            reasons.append(
                "native external multi-equipment recheck comparison is malformed or permits unsafe promotion"
            )
        for status_key, record_key in (
            (
                "external_lh2dt_native_multi_equipment_recheck_comparison_status",
                "status",
            ),
            (
                "external_lh2dt_native_multi_equipment_recheck_comparison_all_provider_result_digests_match",
                "all_provider_result_digests_match",
            ),
            (
                "external_lh2dt_native_multi_equipment_recheck_comparison_all_chain_statuses_match",
                "all_chain_statuses_match",
            ),
        ):
            expected = status.get(status_key)
            if expected is not None and native_comparison_value.get(record_key) != expected:
                reasons.append(
                    f"status ledger {status_key} disagrees with native recheck comparison"
                )

    # The clean-source full-scope replay binds all 24 generic outdoor LH2
    # event identities to the facility consequence runner.  It is still a
    # diagnostic record: the verifier checks the complete handoff and all
    # fail-closed flags, but never treats it as qualified facility QRA.
    clean_scope_value: dict[str, Any] = {}
    clean_scope_path: Path | None = None
    clean_scope_pointer = status.get(
        "external_lh2dt_native_clean_full_scope_replay_record"
    )
    if native_external_clean_full_scope_replay is None and isinstance(
        clean_scope_pointer, str
    ):
        clean_scope_path = _relative_or_absolute(clean_scope_pointer, root=base)
        if not clean_scope_path.exists():
            reasons.append("native clean full-scope replay record does not exist")
        else:
            clean_scope_value = _read_object(clean_scope_path)
    elif isinstance(native_external_clean_full_scope_replay, Path):
        clean_scope_path = native_external_clean_full_scope_replay
        clean_scope_value = _read_object(clean_scope_path)
    elif isinstance(native_external_clean_full_scope_replay, Mapping):
        clean_scope_value = dict(native_external_clean_full_scope_replay)
    if clean_scope_pointer is not None or native_external_clean_full_scope_replay is not None:
        source = clean_scope_value.get("source")
        packet_catalog = clean_scope_value.get("packet_catalog")
        campaign = clean_scope_value.get("facility_campaign")
        clean_scope_valid = (
            clean_scope_value.get("schema_version")
            == "prism.native_external_facility_full_scope_clean_source_replay.v1"
            and clean_scope_value.get("status")
            == "EXECUTED_DIAGNOSTIC_CLEAN_EXTERNAL_SOURCE"
            and isinstance(source, Mapping)
            and isinstance(source.get("repository"), str)
            and bool(source.get("repository"))
            and isinstance(source.get("commit"), str)
            and bool(source.get("commit"))
            and isinstance(source.get("source_tree_sha256"), str)
            and len(source.get("source_tree_sha256")) == 64
            and isinstance(packet_catalog, Mapping)
            and packet_catalog.get("event_count") == 24
            and packet_catalog.get("exact_native_packet_count") == 24
            and packet_catalog.get("uncomputed_event_count") == 0
            and packet_catalog.get("isolation_requested") is False
            and isinstance(campaign, Mapping)
            and campaign.get("packet_count") == 24
            and campaign.get("event_count") == 24
            and campaign.get("matched_event_case_record_count") == 24
            and campaign.get("matched_event_executed_case_count") == 24
            and campaign.get("matched_event_uncomputed_case_count") == 0
            and campaign.get("matched_event_failed_case_count") == 0
            and campaign.get("risk_atom_count") == 96
            and campaign.get("hazop_event_mode_binding", {}).get("bound_event_count") == 24
            and campaign.get("hazop_event_mode_binding", {}).get("unbound_event_count") == 0
            and campaign.get("provider_packet_promoted") is False
            and campaign.get("physical_validation_claim") is False
            and campaign.get("facility_qra_claim") is False
        )
        if not clean_scope_valid:
            reasons.append(
                "native clean full-scope replay is malformed or permits unsafe promotion"
            )
        for status_key, actual in (
            (
                "external_lh2dt_native_clean_full_scope_replay_source_digest",
                source.get("source_tree_sha256") if isinstance(source, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_replay_packet_count",
                campaign.get("packet_count") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_replay_executed_case_count",
                campaign.get("matched_event_executed_case_count") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_replay_risk_atom_count",
                campaign.get("risk_atom_count") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_replay_facility_qra_claim",
                campaign.get("facility_qra_claim") if isinstance(campaign, Mapping) else None,
            ),
        ):
            expected = status.get(status_key)
            if expected is not None and actual != expected:
                reasons.append(
                    f"status ledger {status_key} disagrees with clean full-scope replay"
                )

    # The isolation replay is a separate diagnostic record because it proves a
    # stronger provider termination branch than the earlier no-isolation
    # replay.  It still cannot promote a provider packet, infer field
    # isolation reliability, or open the facility-QRA gate.
    isolation_scope_value: dict[str, Any] = {}
    isolation_scope_path: Path | None = None
    isolation_scope_valid = False
    isolation_scope_pointer = status.get(
        "external_lh2dt_native_clean_full_scope_isolation_replay_record"
    )
    if native_external_clean_full_scope_isolation_replay is None and isinstance(
        isolation_scope_pointer, str
    ):
        isolation_scope_path = _relative_or_absolute(isolation_scope_pointer, root=base)
        if not isolation_scope_path.exists():
            reasons.append("native clean full-scope isolation replay record does not exist")
        else:
            isolation_scope_value = _read_object(isolation_scope_path)
    elif isinstance(native_external_clean_full_scope_isolation_replay, Path):
        isolation_scope_path = native_external_clean_full_scope_isolation_replay
        isolation_scope_value = _read_object(isolation_scope_path)
    elif isinstance(native_external_clean_full_scope_isolation_replay, Mapping):
        isolation_scope_value = dict(native_external_clean_full_scope_isolation_replay)
    if isolation_scope_pointer is not None or native_external_clean_full_scope_isolation_replay is not None:
        source = isolation_scope_value.get("source")
        packet_catalog = isolation_scope_value.get("packet_catalog")
        campaign = isolation_scope_value.get("facility_campaign")
        adapter = isolation_scope_value.get("adapter")
        facility_risk_summary = isolation_scope_value.get("facility_risk_summary")
        facility_execution_boundary = (
            facility_risk_summary.get("execution_boundary")
            if isinstance(facility_risk_summary, Mapping)
            else None
        )
        isolation_scope_valid = (
            isolation_scope_value.get("schema_version")
            == "prism.native_external_facility_full_scope_clean_source_isolation_replay.v1"
            and isolation_scope_value.get("status")
            == "EXECUTED_DIAGNOSTIC_CLEAN_EXTERNAL_SOURCE_WITH_ISOLATION"
            and isinstance(source, Mapping)
            and isinstance(source.get("repository"), str)
            and bool(source.get("repository"))
            and isinstance(source.get("commit"), str)
            and bool(source.get("commit"))
            and isinstance(source.get("source_tree_sha256"), str)
            and len(source.get("source_tree_sha256")) == 64
            and isinstance(adapter, Mapping)
            and adapter.get("transfer_valve_isolation_success_event_count") == 5
            and isinstance(facility_risk_summary, Mapping)
            and isinstance(facility_risk_summary.get("sha256"), str)
            and len(facility_risk_summary.get("sha256")) == 64
            and facility_risk_summary.get("conditional_diagnostic_facility_risk_available") is True
            and facility_risk_summary.get("facility_total_risk_available") is False
            and facility_risk_summary.get("scenario_count") == 3
            and facility_risk_summary.get("receptor_count") == 1
            and facility_risk_summary.get("frequency_reallocation_performed") is False
            and isinstance(facility_execution_boundary, Mapping)
            and facility_execution_boundary.get("assessment_fresh_physics_executed") is False
            and facility_execution_boundary.get("source_campaign_physics_executed") is True
            and facility_execution_boundary.get("source_campaign_fresh_physics_cases") == 24
            and isinstance(packet_catalog, Mapping)
            and packet_catalog.get("event_count") == 24
            and packet_catalog.get("exact_native_packet_count") == 24
            and packet_catalog.get("uncomputed_event_count") == 0
            and packet_catalog.get("isolation_requested") is True
            and packet_catalog.get("isolation_time_s") == 0.05
            and packet_catalog.get("post_isolation_observation_s") == 0.1
            and isinstance(campaign, Mapping)
            and campaign.get("packet_count") == 24
            and campaign.get("event_count") == 24
            and campaign.get("matched_event_case_record_count") == 24
            and campaign.get("matched_event_executed_case_count") == 24
            and campaign.get("matched_event_uncomputed_case_count") == 0
            and campaign.get("matched_event_failed_case_count") == 0
            and campaign.get("risk_atom_count") == 96
            and campaign.get("hazop_event_mode_binding", {}).get("bound_event_count") == 24
            and campaign.get("hazop_event_mode_binding", {}).get("unbound_event_count") == 0
            and campaign.get("provider_packet_promoted") is False
            and campaign.get("physical_validation_claim") is False
            and campaign.get("facility_qra_claim") is False
        )
        if not isolation_scope_valid:
            reasons.append(
                "native clean full-scope isolation replay is malformed or permits unsafe promotion"
            )
        for status_key, actual in (
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_source_digest",
                source.get("source_tree_sha256") if isinstance(source, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_packet_count",
                campaign.get("packet_count") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_executed_case_count",
                campaign.get("matched_event_executed_case_count") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_uncomputed_case_count",
                campaign.get("matched_event_uncomputed_case_count") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_failed_case_count",
                campaign.get("matched_event_failed_case_count") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_risk_atom_count",
                campaign.get("risk_atom_count") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_transfer_valve_isolation_success_count",
                adapter.get("transfer_valve_isolation_success_event_count") if isinstance(adapter, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_facility_qra_claim",
                campaign.get("facility_qra_claim") if isinstance(campaign, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_summary_sha256",
                facility_risk_summary.get("sha256") if isinstance(facility_risk_summary, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_scenario_count",
                facility_risk_summary.get("scenario_count") if isinstance(facility_risk_summary, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_receptor_count",
                facility_risk_summary.get("receptor_count") if isinstance(facility_risk_summary, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_summary_source_campaign_physics_executed",
                facility_execution_boundary.get("source_campaign_physics_executed") if isinstance(facility_execution_boundary, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_summary_source_campaign_fresh_physics_cases",
                facility_execution_boundary.get("source_campaign_fresh_physics_cases") if isinstance(facility_execution_boundary, Mapping) else None,
            ),
            (
                "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_summary_assessment_fresh_physics_executed",
                facility_execution_boundary.get("assessment_fresh_physics_executed") if isinstance(facility_execution_boundary, Mapping) else None,
            ),
        ):
            expected = status.get(status_key)
            if expected is not None and actual != expected:
                reasons.append(
                    f"status ledger {status_key} disagrees with clean full-scope isolation replay"
                )

    # The actual FFI Test 6 convergence record is optional for historical
    # callers, but when the current status ledger points to it we verify the
    # identity and fail-closed claims here as well.  This keeps a stale or
    # hand-edited status file from silently presenting an unresolved numerical
    # source as accepted physical validation.
    gate_record_value = status.get("slabx_lh2_test6_actual_source_numerical_gate_record")
    gate_status_value = status.get("slabx_lh2_test6_actual_source_numerical_gate_status")
    gate_accepted_value = status.get("slabx_lh2_test6_actual_source_numerical_gate_accepted")
    gate_record: dict[str, Any] = {}
    ffi_gate_path: Path | None = None
    if gate_record_value is not None:
        if not isinstance(gate_record_value, str) or not gate_record_value.strip():
            reasons.append("actual FFI numerical gate record pointer is not a non-empty string")
        else:
            ffi_gate_path = _relative_or_absolute(gate_record_value, root=base)
            if not ffi_gate_path.exists():
                reasons.append("actual FFI numerical gate record does not exist")
            else:
                gate_record = _read_object(ffi_gate_path)
                if gate_record.get("schema_version") != (
                    "prism.slabx_lh2_ffi_test6_actual_source_numerical_gate.v1"
                ):
                    reasons.append("actual FFI numerical gate schema is not the declared schema")
                if gate_status_value != gate_record.get("status"):
                    reasons.append("status ledger and actual FFI numerical gate status disagree")
                if gate_accepted_value != gate_record.get("accepted"):
                    reasons.append("status ledger and actual FFI numerical gate acceptance disagree")
                if status.get("slabx_lh2_test6_actual_source_numerical_gate_physical_validation_claim") is not False:
                    reasons.append("status ledger actual FFI gate must keep physical_validation_claim=false")
                if status.get("slabx_lh2_test6_actual_source_numerical_gate_facility_qra_claim") is not False:
                    reasons.append("status ledger actual FFI gate must keep facility_qra_claim=false")
                refinement_path = ffi_gate_path.with_name("refinement.json")
                if not refinement_path.exists():
                    reasons.append("actual FFI numerical gate refinement record does not exist")

    # A separately declared pseudo-source convergence record may accompany the
    # actual FFI gate.  It is useful numerical evidence, but it must remain
    # explicitly non-promoting and must never be accepted as the actual source.
    pseudo_record_value = status.get("slabx_lh2_pseudosource_numerical_sensitivity_record")
    pseudo_record: dict[str, Any] = {}
    pseudo_path: Path | None = None
    if pseudo_record_value is not None:
        if not isinstance(pseudo_record_value, str) or not pseudo_record_value.strip():
            reasons.append("pseudo-source numerical sensitivity pointer is not a non-empty string")
        else:
            pseudo_path = _relative_or_absolute(pseudo_record_value, root=base)
            if not pseudo_path.exists():
                reasons.append("pseudo-source numerical sensitivity record does not exist")
            else:
                pseudo_record = _read_object(pseudo_path)
                if pseudo_record.get("schema_version") != (
                    "prism.slabx_lh2_pseudosource_numerical_sensitivity.v1"
                ):
                    reasons.append("pseudo-source numerical sensitivity schema is not the declared schema")
                if pseudo_record.get("status") != "DIAGNOSTIC_PSEUDOSOURCE_CONVERGENCE_ACCEPTED":
                    reasons.append("pseudo-source numerical sensitivity status is not accepted diagnostic evidence")
                if pseudo_record.get("accepted") is not True:
                    reasons.append("pseudo-source numerical sensitivity must have accepted=true")
                policy = pseudo_record.get("promotion_policy")
                if not isinstance(policy, Mapping) or policy.get("actual_ffi_test6_source_gate_closed") is not False:
                    reasons.append("pseudo-source evidence must keep the actual FFI source gate open")
                if not isinstance(policy, Mapping) or policy.get("independent_physical_validation_claim") is not False:
                    reasons.append("pseudo-source evidence must keep physical_validation_claim=false")
                if not isinstance(policy, Mapping) or policy.get("facility_qra_claim") is not False:
                    reasons.append("pseudo-source evidence must keep facility_qra_claim=false")

    status_value = "PASS" if not reasons else "BLOCKED_AUDIT_METADATA"
    scope_status = scope_value.get("status") if scope_value else None
    if scope_value and scope_status is None:
        scope_status = (
            "COMPLETE_DECLARED_SCOPE"
            if scope_value.get("matrix_complete") is True
            else "INCOMPLETE_DECLARED_SCOPE"
        )

    return {
        "schema_version": SCHEMA,
        "status": status_value,
        "audit_record": str(record_path),
        "audit_status": audit_value.get("status"),
        "check_count": len(checks),
        "pass_check_count": pass_count,
        "blocked_check_count": blocked_check_count,
        "blocking_reason_count": len(blockers),
        "facility_handoff_check_count": len(handoff_checks) if isinstance(handoff_checks, list) else 0,
        "facility_handoff_status": handoff_value.get("status"),
        "complete_facility_qra_claim": audit_value.get("complete_facility_qra_claim"),
        "physical_validation_claim": audit_value.get("physical_validation_claim"),
        "receptor_geometry_interpretation_record": str(geometry_path) if geometry_path else None,
        "receptor_geometry_interpretation_status": geometry_value.get("status") if geometry_value else None,
        "actual_ffi_numerical_gate_record": str(ffi_gate_path) if ffi_gate_path else None,
        "actual_ffi_numerical_gate_status": gate_record.get("status") if gate_record else gate_status_value,
        "actual_ffi_numerical_gate_accepted": gate_record.get("accepted") if gate_record else gate_accepted_value,
        "pseudo_source_numerical_sensitivity_record": str(pseudo_path) if pseudo_path else None,
        "pseudo_source_numerical_sensitivity_status": pseudo_record.get("status") if pseudo_record else status.get("slabx_lh2_pseudosource_numerical_sensitivity_status"),
        "pseudo_source_numerical_sensitivity_accepted": pseudo_record.get("accepted") if pseudo_record else status.get("slabx_lh2_pseudosource_numerical_sensitivity_accepted"),
        "facility_scope_matrix_record": str(scope_path) if scope_path else None,
        "facility_scope_matrix_status": scope_status,
        "facility_scope_matrix_case_count": scope_value.get("case_count") if scope_value else None,
        "facility_qra_gate_summary_record": str(gate_path) if gate_path else None,
        "facility_qra_gate_summary_status": gate_value.get("status") if gate_value else None,
        "facility_qra_gate_summary_incomplete_gate_count": (
            sum(
                not row.get("complete", False)
                for row in gate_value.get("gates", {}).values()
            )
            if gate_value and isinstance(gate_value.get("gates"), Mapping)
            else None
        ),
        "facility_qra_gate_summary_blocking_reason_count": (
            len(gate_value.get("blocking_reasons", []))
            if gate_value and isinstance(gate_value.get("blocking_reasons"), list)
            else None
        ),
        "release_boundary_audit_record": str(release_path) if release_path else None,
        "release_boundary_audit_status": release_value.get("status") if release_value else None,
        "release_boundary_case_count": release_value.get("case_count") if release_value else None,
        "release_boundary_request_contract_status_counts": (
            release_value.get("facility_evidence_request_contract_status_counts")
            if release_value else None
        ),
        "release_boundary_request_contract_blocked_case_count": (
            release_value.get("facility_evidence_request_contract_blocked_case_count")
            if release_value else None
        ),
        "release_boundary_asset_count": (
            len(release_value.get("asset_summary", {}))
            if release_value and isinstance(release_value.get("asset_summary"), Mapping)
            else None
        ),
        "release_closure_worklist_record": str(closure_path) if closure_path else None,
        "release_closure_worklist_status": closure_value.get("status") if closure_value else None,
        "release_closure_worklist_case_count": closure_value.get("case_count") if closure_value else None,
        "release_closure_worklist_open_case_count": closure_value.get("open_case_count") if closure_value else None,
        "release_closure_worklist_termination_open_case_count": (
            closure_value.get("summary", {}).get("termination_open_case_count")
            if closure_value and isinstance(closure_value.get("summary"), Mapping)
            else None
        ),
        "release_closure_worklist_isolation_open_case_count": (
            closure_value.get("summary", {}).get("isolation_open_case_count")
            if closure_value and isinstance(closure_value.get("summary"), Mapping)
            else None
        ),
        "release_closure_worklist_inventory_open_case_count": (
            closure_value.get("summary", {}).get("inventory_closure_open_case_count")
            if closure_value and isinstance(closure_value.get("summary"), Mapping)
            else None
        ),
        "release_closure_worklist_boundary_join_case_count": (
            closure_value.get("summary", {}).get("boundary_audit_join_case_count")
            if closure_value and isinstance(closure_value.get("summary"), Mapping)
            else None
        ),
        "release_closure_worklist_numerically_closed_case_count": (
            closure_value.get("summary", {}).get("numerically_closed_case_count")
            if closure_value and isinstance(closure_value.get("summary"), Mapping)
            else None
        ),
        "release_closure_worklist_numerically_open_case_count": (
            closure_value.get("summary", {}).get("numerically_open_case_count")
            if closure_value and isinstance(closure_value.get("summary"), Mapping)
            else None
        ),
        "release_closure_worklist_operator_review_required_case_count": (
            closure_value.get("summary", {}).get("operator_review_required_case_count")
            if closure_value and isinstance(closure_value.get("summary"), Mapping)
            else None
        ),
        "release_closure_worklist_strict_boundary_eligible_case_count": (
            closure_value.get("summary", {}).get(
                "strict_release_boundary_eligible_case_count"
            )
            if closure_value and isinstance(closure_value.get("summary"), Mapping)
            else None
        ),
        "release_closure_worklist_sha256": closure_sha256,
        "native_external_multi_equipment_recheck_record": (
            str(native_recheck_path) if native_recheck_path else None
        ),
        "native_external_multi_equipment_recheck_status": (
            native_recheck_value.get("status") if native_recheck_value else None
        ),
        "native_external_multi_equipment_recheck_equipment_count": (
            native_recheck_value.get("equipment_count") if native_recheck_value else None
        ),
        "native_external_multi_equipment_recheck_dynamic_closure_ready_count": (
            sum(
                isinstance(row, Mapping)
                and isinstance(row.get("dynamic_state_closure"), Mapping)
                and row["dynamic_state_closure"].get("ready") is True
                for row in native_recheck_value.get("equipment", [])
            )
            if isinstance(native_recheck_value.get("equipment"), list)
            else None
        ),
        "native_external_multi_equipment_recheck_valid": (
            native_recheck_valid if native_recheck_pointer is not None or native_external_multi_equipment_recheck is not None else None
        ),
        "native_external_multi_equipment_recheck_comparison_record": (
            str(native_comparison_path) if native_comparison_path else None
        ),
        "native_external_multi_equipment_recheck_comparison_status": (
            native_comparison_value.get("status") if native_comparison_value else None
        ),
        "native_external_multi_equipment_recheck_comparison_equipment_count": (
            native_comparison_value.get("equipment_count") if native_comparison_value else None
        ),
        "native_external_multi_equipment_recheck_comparison_valid": (
            comparison_valid if native_comparison_pointer is not None else None
        ),
        "native_external_clean_full_scope_replay_record": (
            str(clean_scope_path) if clean_scope_path else None
        ),
        "native_external_clean_full_scope_replay_status": (
            clean_scope_value.get("status") if clean_scope_value else None
        ),
        "native_external_clean_full_scope_replay_valid": (
            clean_scope_valid
            if clean_scope_pointer is not None or native_external_clean_full_scope_replay is not None
            else None
        ),
        "native_external_clean_full_scope_replay_packet_count": (
            clean_scope_value.get("facility_campaign", {}).get("packet_count")
            if isinstance(clean_scope_value.get("facility_campaign"), Mapping)
            else None
        ),
        "native_external_clean_full_scope_replay_executed_case_count": (
            clean_scope_value.get("facility_campaign", {}).get("matched_event_executed_case_count")
            if isinstance(clean_scope_value.get("facility_campaign"), Mapping)
            else None
        ),
        "native_external_clean_full_scope_replay_risk_atom_count": (
            clean_scope_value.get("facility_campaign", {}).get("risk_atom_count")
            if isinstance(clean_scope_value.get("facility_campaign"), Mapping)
            else None
        ),
        "native_external_clean_full_scope_isolation_replay_record": (
            str(isolation_scope_path) if isolation_scope_path else None
        ),
        "native_external_clean_full_scope_isolation_replay_status": (
            isolation_scope_value.get("status") if isolation_scope_value else None
        ),
        "native_external_clean_full_scope_isolation_replay_valid": (
            isolation_scope_valid
            if isolation_scope_pointer is not None or native_external_clean_full_scope_isolation_replay is not None
            else None
        ),
        "native_external_clean_full_scope_isolation_replay_packet_count": (
            isolation_scope_value.get("facility_campaign", {}).get("packet_count")
            if isinstance(isolation_scope_value.get("facility_campaign"), Mapping)
            else None
        ),
        "native_external_clean_full_scope_isolation_replay_executed_case_count": (
            isolation_scope_value.get("facility_campaign", {}).get("matched_event_executed_case_count")
            if isinstance(isolation_scope_value.get("facility_campaign"), Mapping)
            else None
        ),
        "native_external_clean_full_scope_isolation_replay_uncomputed_case_count": (
            isolation_scope_value.get("facility_campaign", {}).get("matched_event_uncomputed_case_count")
            if isinstance(isolation_scope_value.get("facility_campaign"), Mapping)
            else None
        ),
        "native_external_clean_full_scope_isolation_replay_failed_case_count": (
            isolation_scope_value.get("facility_campaign", {}).get("matched_event_failed_case_count")
            if isinstance(isolation_scope_value.get("facility_campaign"), Mapping)
            else None
        ),
        "native_external_clean_full_scope_isolation_replay_risk_atom_count": (
            isolation_scope_value.get("facility_campaign", {}).get("risk_atom_count")
            if isinstance(isolation_scope_value.get("facility_campaign"), Mapping)
            else None
        ),
        "native_external_clean_full_scope_isolation_replay_facility_risk_summary_valid": (
            isinstance(isolation_scope_value.get("facility_risk_summary"), Mapping)
            and isolation_scope_value.get("facility_risk_summary", {}).get("conditional_diagnostic_facility_risk_available") is True
            and isolation_scope_value.get("facility_risk_summary", {}).get("facility_total_risk_available") is False
            if isolation_scope_pointer is not None or native_external_clean_full_scope_isolation_replay is not None
            else None
        ),
        "blocking_reasons": reasons,
        "interpretation": (
            "The latest audit pointer, summary counts, diagnostic facility handoff, scope matrix, and "
            "release-boundary ledger are internally consistent; this verification does not promote provider "
            "qualification, physical validation, or facility IR/F-N."
            if not reasons
            else "The latest audit metadata is inconsistent or incomplete; no qualification claim is allowed."
        ),
    }
