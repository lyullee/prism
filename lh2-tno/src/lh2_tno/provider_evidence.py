"""Read-only audit of an external LH2 digital-twin provider export.

This module is deliberately a boundary adapter.  It reads machine-readable
provider evidence (and the provider's validation note), counts what is
confirmed or still missing, and returns a promotion report.  It never imports
the provider's solver and never copies screening defaults into a PRISM
``Facility``.  That makes the same audit useful for a generic outdoor LH2
plant even when the current provider happens to be the inspection-centre
project.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


CONFIG_FILES = (
    "center_assets.json",
    "center_component_bindings.json",
    "center_operation_command_bindings.json",
    "center_operation_sequences.json",
    "center_parameter_input_template.json",
    "center_port_mappings.json",
    "center_port_netlist.json",
    "center_screening_closure.json",
    "center_observation_bindings.json",
    "scenarios.json",
)


def _count_status(rows: Any, field: str = "status") -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(rows, list):
        return counts
    for row in rows:
        value = row.get(field) if isinstance(row, dict) else None
        key = str(value) if value is not None else "<missing>"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing file"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"invalid JSON: {error}"
    if not isinstance(value, dict):
        return None, "top-level JSON value is not an object"
    return value, None


def _digest_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _regression_evidence(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"file": str(path), "test_count": None, "all_passed": None}
    text = path.read_text(encoding="utf-8")
    # Keep this parser intentionally narrow: only the provider's explicit
    # sentence is accepted as regression evidence.
    match = re.search(r"전체\s*회귀\s*\*\*(\d+)개가\s*모두\s*통과", text)
    return {
        "file": str(path),
        "test_count": int(match.group(1)) if match else None,
        "all_passed": bool(match),
    }


def audit_provider_root(root: str | Path) -> dict[str, Any]:
    """Audit provider evidence without promoting any provider values.

    The returned status is ``EXECUTABLE_PROVIDER`` only when the provider
    explicitly declares center binding and forward comparison readiness and
    has no unconfirmed parameter/control/port evidence.  The expected current
    result is ``PARTIAL_PROVIDER_EVIDENCE``.
    """
    root_path = Path(root)
    configs = root_path / "configs"
    loaded: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for name in CONFIG_FILES:
        data, error = _read_json(configs / name)
        if data is not None:
            loaded[name] = data
        if error:
            errors[name] = error

    assets = loaded.get("center_assets.json", {}).get("assets", [])
    components = loaded.get("center_component_bindings.json", {})
    params = loaded.get("center_parameter_input_template.json", {})
    commands = loaded.get("center_operation_command_bindings.json", {})
    mappings = loaded.get("center_port_mappings.json", {})
    netlist = loaded.get("center_port_netlist.json", {})
    closure = loaded.get("center_screening_closure.json", {})
    sequences = loaded.get("center_operation_sequences.json", {})
    observations = loaded.get("center_observation_bindings.json", {})
    scenarios = loaded.get("scenarios.json", {})

    parameter_rows = params.get("rows", [])
    parameter_status = _count_status(parameter_rows, "value_status")
    parameter_review = _count_status(parameter_rows, "review_status")
    priorities: dict[str, int] = {}
    for row in parameter_rows if isinstance(parameter_rows, list) else []:
        priority = str(row.get("priority", "<missing>")) if isinstance(row, dict) else "<missing>"
        priorities[priority] = priorities.get(priority, 0) + 1

    sequence_rows = [
        row
        for scenario in sequences.get("scenarios", [])
        if isinstance(scenario, dict)
        for row in scenario.get("rows", [])
        if isinstance(row, dict)
    ]
    physical_time_missing = sum(row.get("physical_time_s") is None for row in sequence_rows)

    confirmed_tag_map = commands.get("confirmed_tag_map", {})
    procedure_tag_map = commands.get("procedure_to_pid_tag_map", {})
    center_binding_ready = closure.get("parameter_policy", {}).get("bind_center_asset")
    forward_comparison_allowed = closure.get("promotion_rule", {}).get("forward_comparison_allowed")

    blockers: list[str] = []
    if center_binding_ready is not True:
        blockers.append("provider does not declare center asset binding ready")
    if forward_comparison_allowed is not True:
        blockers.append("provider does not allow forward comparison")
    if errors:
        blockers.extend(f"{name}: {reason}" for name, reason in sorted(errors.items()))
    if parameter_status.get("unconfirmed", 0) or parameter_status.get("<missing>", 0):
        blockers.append("parameter values remain unconfirmed or missing")
    if parameter_review.get("unconfirmed", 0):
        blockers.append("parameter review status remains unconfirmed")
    if not confirmed_tag_map:
        blockers.append("no reviewed confirmed operation command tag map")
    if not procedure_tag_map:
        blockers.append("no procedure-to-P&ID/PLC command map")
    if physical_time_missing:
        blockers.append("physical command times are missing from operation sequences")

    selected_paths = [
        configs / name for name in CONFIG_FILES if (configs / name).exists()
    ]
    validation_note = root_path / "검증결과.md"
    if validation_note.exists():
        selected_paths.append(validation_note)

    component_edges = components.get("edge_bindings", [])
    node_bindings = components.get("node_bindings", [])
    report = {
        "status": "EXECUTABLE_PROVIDER" if not blockers else "PARTIAL_PROVIDER_EVIDENCE",
        "provider_root": str(root_path),
        "facility": closure.get("facility") or params.get("facility"),
        "source_digest": _digest_files(selected_paths) if selected_paths else None,
        "provider_validation": _regression_evidence(validation_note),
        "readiness": {
            "center_binding_ready": center_binding_ready,
            "forward_comparison_allowed": forward_comparison_allowed,
            "screening_status": closure.get("status"),
            "plant_data_optimization": commands.get("plant_data_optimization"),
        },
        "coverage": {
            "assets": {"total": len(assets), "validation_status": _count_status(assets, "validation_status")},
            "component_nodes": {"total": len(node_bindings), "binding_status": _count_status(node_bindings, "binding_status")},
            "component_edges": {"total": len(component_edges), "binding_status": _count_status(component_edges, "binding_status")},
            "port_mappings": {"total": len(mappings.get("mappings", [])), "status": _count_status(mappings.get("mappings", []))},
            "port_netlist": {"total": len(netlist.get("connections", [])), "status": _count_status(netlist.get("connections", []))},
            "parameter_requests": {
                "declared_total": params.get("row_count", len(parameter_rows)),
                "observed_rows": len(parameter_rows),
                "priority": dict(sorted(priorities.items())),
                "value_status": parameter_status,
                "review_status": parameter_review,
            },
            "operation_commands": {
                "confirmed_tag_map": len(confirmed_tag_map) if isinstance(confirmed_tag_map, dict) else 0,
                "procedure_to_pid_tag_map": len(procedure_tag_map) if isinstance(procedure_tag_map, dict) else 0,
            },
            "operation_sequences": {
                "scenario_count": len(sequences.get("scenarios", [])),
                "row_count": len(sequence_rows),
                "physical_time_missing": physical_time_missing,
            },
            "observations": {"total": len(observations.get("bindings", [])), "status": _count_status(observations.get("bindings", []))},
            "scenarios": len(scenarios.get("scenarios", [])),
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "promotion_policy": {
            "screening_values_are_not_promoted": True,
            "missing_parameter_values_are_not_inferred": True,
            "missing_command_tags_are_not_inferred": True,
            "provider_solver_is_not_imported": True,
            "prism_facility_promotion_requires": "EXECUTABLE_PROVIDER",
        },
    }
    return report

