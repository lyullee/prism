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

from .provider_release import ProviderReleaseContractError, load_provider_release


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

# A normal-process result may contain a mass-flow field while still being
# unsuitable as an accident source.  Keep the inventory deliberately narrow:
# it looks for an explicit resolved-release packet, rather than guessing one
# from P/T, a screening flow, or a command sequence.
_FLOW_KEYS = {
    "mass_flow_kg_s",
    "total_mass_flow_kg_s",
    "gas_mass_flow_kg_s",
    "ground_liquid_mass_flow_kg_s",
}
_GENERIC_RELEASE_KEYS = {
    "event_kind",
    "failure_opening_diameter_m",
    "steps",
    "duration_s",
    "available_mass_kg",
    "cumulative_mass_out_kg",
    "component_id",
    "port_id",
    "event_id",
    "provider_source_digest",
    "provider_result_digest",
    "provider_boundary_reference",
    "position_enu_m",
    "direction_enu",
    "termination_provenance",
    "property_basis",
    "upstream_service",
    "upstream_service_provenance",
    "input_origin",
    "ambient_pressure_pa_abs",
    "ambient_temperature_k",
}
_GAS_RELEASE_KEYS = {
    "cumulative_static_enthalpy_out_j",
    "boundary_kind",
    "enthalpy_convention",
}
_LIQUID_RELEASE_KEYS = {
    "cumulative_specific_enthalpy_out_j",
    "boundary_kind",
    "enthalpy_convention",
    "phase_basis",
    "reference_area_m2",
    "reference_area_provenance",
    "droplet_partition_provenance",
}


def _iter_json_objects(value: Any):
    """Yield every nested JSON object without interpreting provider values."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_json_objects(child)


def _json_inventory_paths(root: Path) -> list[Path]:
    """Return provider JSON files, excluding virtual environments and caches."""
    excluded = {"__pycache__", "build", "dist", "node_modules", ".git"}
    paths: list[Path] = []
    for path in root.rglob("*.json"):
        if any(part == name or part.startswith(".venv") for part in path.parts for name in excluded):
            continue
        paths.append(path)
    return sorted(paths)


def _release_packet_inventory(root: Path) -> dict[str, Any]:
    """Inventory explicit accident-release packets in a provider export.

    This is an evidence check only.  It never turns a JSON object into a
    ``ResolvedGasRelease``/``ResolvedLiquidRelease`` and therefore cannot
    accidentally promote a normal-flow or screening result.
    """
    files_scanned = 0
    invalid_json = 0
    flow_only_files = 0
    candidate_files: list[dict[str, Any]] = []
    qualified_files: list[dict[str, Any]] = []
    strict_validation_failures: list[dict[str, str]] = []
    missing_reasons: dict[str, int] = {}

    for path in _json_inventory_paths(root):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            invalid_json += 1
            continue
        files_scanned += 1
        objects = list(_iter_json_objects(value))
        flow_present = any(any(key in obj for key in _FLOW_KEYS) for obj in objects)
        accident_objects = [obj for obj in objects if obj.get("event_kind") == "accidental_leak"]
        if not accident_objects and flow_present:
            flow_only_files += 1
        for obj in accident_objects:
            # A candidate needs a declared random opening and a time history.
            candidate = all(key in obj for key in ("failure_opening_diameter_m", "steps", "duration_s"))
            if not candidate:
                for key in ("failure_opening_diameter_m", "steps", "duration_s"):
                    if key not in obj:
                        missing_reasons[f"missing:{key}"] = missing_reasons.get(f"missing:{key}", 0) + 1
                continue
            relative = str(path.relative_to(root))
            entry = {
                "file": relative,
                "event_id": obj.get("event_id"),
                "component_id": obj.get("component_id"),
                "port_id": obj.get("port_id"),
                "event_kind": obj.get("event_kind"),
                "schema": obj.get("provider_export_schema") or obj.get("schema_version"),
            }
            candidate_files.append(entry)
            required = set(_GENERIC_RELEASE_KEYS)
            if "phase_basis" in obj or "cumulative_specific_enthalpy_out_j" in obj:
                required.update(_LIQUID_RELEASE_KEYS)
            else:
                required.update(_GAS_RELEASE_KEYS)
            # An explicit contract marker prevents a coincidentally similar
            # provider result from being treated as a PRISM export.
            required.add("provider_export_schema")
            missing = sorted(key for key in required if key not in obj)
            if not isinstance(obj.get("steps"), list) or not obj.get("steps"):
                missing.append("steps_nonempty")
            else:
                for index, step in enumerate(obj["steps"]):
                    if not isinstance(step, dict):
                        missing.append(f"steps[{index}]_object")
                        continue
                    if "time_s" not in step:
                        missing.append(f"steps[{index}].time_s")
                    if "mass_flow_kg_s" not in step and "total_mass_flow_kg_s" not in step:
                        missing.append(f"steps[{index}].mass_flow")
                    if "phase_basis" in obj:
                        for key in ("gas_mass_flow_kg_s", "ground_liquid_mass_flow_kg_s", "airborne_liquid_mass_flow_kg_s"):
                            if key not in step:
                                missing.append(f"steps[{index}].{key}")
            if missing:
                for key in missing:
                    missing_reasons[f"missing:{key}"] = missing_reasons.get(f"missing:{key}", 0) + 1
                continue
            # Field presence is only the first gate. Re-run the exact PRISM
            # boundary validator so continuity, mass/enthalpy closure, clock
            # ordering, vertical handoff rules, and non-finite values cannot
            # hide behind a superficially complete provider packet.
            try:
                load_provider_release(obj)
            except (ProviderReleaseContractError, ValueError, TypeError) as error:
                strict_validation_failures.append(
                    {"file": relative, "error": str(error)}
                )
                continue
            qualified_files.append(entry)

    blockers: list[str] = []
    if not candidate_files:
        blockers.append("provider export contains no explicit accidental resolved-release packet")
    if candidate_files and not qualified_files:
        blockers.append("accident release candidates are missing the complete PRISM export contract")
    if strict_validation_failures:
        blockers.append("accident release candidates failed strict PRISM boundary validation")
    if flow_only_files:
        blockers.append("normal or screening flow JSON was found without an accident-release contract")
    return {
        "promotion_status": "QUALIFIED_ACCIDENT_RELEASE_EXPORT" if qualified_files else "NO_ACCIDENT_RELEASE_EXPORT",
        "files_scanned": files_scanned,
        "invalid_json_files": invalid_json,
        "normal_or_screening_flow_file_count": flow_only_files,
        "accident_release_candidate_file_count": len(candidate_files),
        "accident_release_qualified_file_count": len(qualified_files),
        "candidate_files": candidate_files[:50],
        "qualified_files": qualified_files[:50],
        "strict_validation_failures": strict_validation_failures[:50],
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "missing_field_counts": dict(sorted(missing_reasons.items())),
        "contract": {
            "required_event_kind": "accidental_leak",
            "required_provider_export_schema": "provider_export_schema",
            "screening_and_normal_flow_is_not_promotable": True,
        },
    }


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
    release_evidence = _release_packet_inventory(root_path)

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
    blockers.extend(release_evidence["blocking_reasons"])

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
            "accident_release_export": release_evidence["promotion_status"],
        },
        "release_evidence": release_evidence,
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
