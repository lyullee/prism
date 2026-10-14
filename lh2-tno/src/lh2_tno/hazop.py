"""Strict HAZOP-table and operating-mode scenario selection.

This module is the qualitative gate before a PRISM consequence calculation.
It consumes a state frame that contains an explicit operating mode together
with SI process values.  A matching deviation selects a declared accident
family, but it never creates a release, assigns a frequency, or promotes a
normal-state measurement to an accident packet.
"""
from __future__ import annotations

import math
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, model_validator

from .accident_scenario_catalog import (
    scenario_definition,
    scenario_families_for_release,
    scenario_families_for_request,
)
from .contracts import Contract, Name, Nonnegative
from .state_snapshot import StateMeasurement


HAZOP_SCHEMA = "prism.hazop_operating_mode_selection.v1"
HAZOP_STATE_SCHEMA = "prism.hazop_state_frame.v1"

_QUANTITIES = {
    "pressure", "temperature", "mass", "mass_flow", "level_fraction",
    "hydrogen_fraction", "differential_pressure",
}
_RELEASE_MODES = {
    "instantaneous_inventory", "inventory_over_600s", "hole",
    "two_sided_rupture", "maximum_relief_discharge",
}
_COMPONENT_KINDS = {
    "storage_tank", "pipe", "valve", "vent_stack", "vaporizer",
    "pump", "reliquefier",
}
_TRIGGERS = {"above", "at_or_above", "below", "at_or_below", "outside_range"}


class HazopSelectionError(ValueError):
    """Raised when a HAZOP table or state frame is structurally unsafe."""


class HazopRow(Contract):
    """One numeric HAZOP deviation row for one component and mode set."""

    id: Name
    component_id: Name
    component_kind: Literal[
        "storage_tank", "pipe", "valve", "vent_stack", "vaporizer",
        "pump", "reliquefier",
    ]
    operating_modes: tuple[Name, ...]
    variable_tag: Name
    quantity: Literal[
        "pressure", "temperature", "mass", "mass_flow", "level_fraction",
        "hydrogen_fraction", "differential_pressure",
    ]
    trigger: Literal["above", "at_or_above", "below", "at_or_below", "outside_range"]
    threshold_low_si: float | None = None
    threshold_high_si: float | None = None
    scenario_family: Name
    release_mode: Literal[
        "instantaneous_inventory", "inventory_over_600s", "hole",
        "two_sided_rupture", "maximum_relief_discharge",
    ]
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    deviation_label: Name
    cause_summary: Name
    consequence_summary: Name
    safeguards: tuple[Name, ...] = ()
    provenance: Name

    @model_validator(mode="after")
    def validate_row(self) -> "HazopRow":
        if not self.operating_modes or len(set(self.operating_modes)) != len(self.operating_modes):
            raise ValueError("HAZOP row requires unique operating_modes")
        if self.trigger not in _TRIGGERS or self.release_mode not in _RELEASE_MODES:
            raise ValueError("unsupported HAZOP trigger or release mode")
        for name, value in (("threshold_low_si", self.threshold_low_si), ("threshold_high_si", self.threshold_high_si)):
            if value is not None and (isinstance(value, bool) or not math.isfinite(float(value))):
                raise ValueError(f"{name} must be finite when supplied")
        if self.trigger in {"below", "at_or_below"} and self.threshold_low_si is None:
            raise ValueError("low trigger requires threshold_low_si")
        if self.trigger in {"above", "at_or_above"} and self.threshold_high_si is None:
            raise ValueError("high trigger requires threshold_high_si")
        if self.trigger == "outside_range":
            if self.threshold_low_si is None or self.threshold_high_si is None:
                raise ValueError("outside_range requires both thresholds")
            if not self.threshold_low_si < self.threshold_high_si:
                raise ValueError("outside_range requires threshold_low_si < threshold_high_si")
        try:
            definition = scenario_definition(self.scenario_family)
        except ValueError as error:
            raise ValueError(f"unknown HAZOP scenario family: {self.scenario_family}") from error
        if self.component_kind not in definition["equipment_kinds"]:
            raise ValueError(
                f"scenario family {self.scenario_family} does not apply to {self.component_kind}"
            )
        if self.release_mode not in definition["release_modes"]:
            raise ValueError(
                f"scenario family {self.scenario_family} does not support {self.release_mode}"
            )
        return self


class HazopTable(Contract):
    """A facility-neutral HAZOP table with explicit mode coverage."""

    schema_version: Literal[HAZOP_SCHEMA]
    id: Name
    facility_id: Name
    operating_modes: tuple[Name, ...]
    rows: tuple[HazopRow, ...]
    source_provenance: Name
    configuration_origin: Literal["synthetic", "reviewed_design", "field_confirmed"]
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_table(self) -> "HazopTable":
        if not self.operating_modes or len(set(self.operating_modes)) != len(self.operating_modes):
            raise ValueError("HAZOP table requires unique operating_modes")
        if not self.rows:
            raise ValueError("HAZOP table requires at least one row")
        if len({row.id for row in self.rows}) != len(self.rows):
            raise ValueError("HAZOP row IDs must be unique")
        allowed = set(self.operating_modes)
        for row in self.rows:
            if not set(row.operating_modes).issubset(allowed):
                raise ValueError(f"HAZOP row {row.id} uses a mode absent from table")
        return self


class HazopStateFrame(Contract):
    """Process measurements plus the operating mode used for HAZOP selection."""

    schema_version: Literal[HAZOP_STATE_SCHEMA]
    facility_id: Name
    component_id: Name
    operating_mode: Name
    captured_at_s: Nonnegative
    values: dict[Name, StateMeasurement]
    state_snapshot_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_provenance: Name

    @model_validator(mode="after")
    def validate_frame(self) -> "HazopStateFrame":
        if not self.values:
            raise ValueError("HAZOP state frame requires at least one measurement")
        if len(set(self.values)) != len(self.values):
            raise ValueError("HAZOP state value tags must be unique")
        for tag, value in self.values.items():
            if value.quantity not in _QUANTITIES:
                raise ValueError(f"unsupported HAZOP state quantity: {tag}")
        return self


def _state_frame(value: HazopStateFrame | Mapping[str, Any]) -> HazopStateFrame:
    if isinstance(value, HazopStateFrame):
        return value
    if not isinstance(value, Mapping):
        raise HazopSelectionError("HAZOP state must be a mapping or HazopStateFrame")
    try:
        return HazopStateFrame.model_validate_json(json.dumps(value, allow_nan=False))
    except Exception as error:
        raise HazopSelectionError(f"invalid HAZOP state frame: {error}") from error


def _active(row: HazopRow, value: float) -> bool:
    if row.trigger == "above":
        return value > float(row.threshold_high_si)
    if row.trigger == "at_or_above":
        return value >= float(row.threshold_high_si)
    if row.trigger == "below":
        return value < float(row.threshold_low_si)
    if row.trigger == "at_or_below":
        return value <= float(row.threshold_low_si)
    return value < float(row.threshold_low_si) or value > float(row.threshold_high_si)


def evaluate_hazop(
    table: HazopTable | Mapping[str, Any],
    state: HazopStateFrame | Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate mode-specific deviations and emit downstream scenario work items.

    A row with an absent signal remains ``MISSING_SIGNAL``.  An active row with
    a declared family is selected even when the provider release is unavailable;
    the selection then carries ``provider_release_required`` and is not a QRA
    result.
    """
    if not isinstance(table, HazopTable):
        try:
            # The wire contract is JSON, where arrays become the tuple fields
            # used by strict Pydantic contracts.
            table = HazopTable.model_validate_json(json.dumps(table, allow_nan=False))
        except Exception as error:
            raise HazopSelectionError(f"invalid HAZOP table: {error}") from error
    frame = _state_frame(state)
    if frame.facility_id != table.facility_id:
        raise HazopSelectionError("HAZOP table and state facility_id do not match")
    table_digest = table.digest()
    state_digest = frame.digest()
    applicable = [row for row in table.rows
                  if row.component_id == frame.component_id
                  and frame.operating_mode in row.operating_modes]
    checks: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    blocking: list[str] = []
    for row in applicable:
        measured = frame.values.get(row.variable_tag)
        base = {
            "row_id": row.id,
            "component_id": row.component_id,
            "operating_mode": frame.operating_mode,
            "variable_tag": row.variable_tag,
            "deviation": row.deviation_label,
            "trigger": row.trigger,
            "scenario_family": row.scenario_family,
            "release_mode": row.release_mode,
        }
        if measured is None:
            checks.append({**base, "status": "MISSING_SIGNAL", "reason": "required HAZOP signal is absent"})
            blocking.append(f"{row.id}: missing signal {row.variable_tag}")
            continue
        if measured.quantity != row.quantity:
            checks.append({**base, "status": "QUANTITY_MISMATCH", "reason": f"expected {row.quantity}, got {measured.quantity}"})
            blocking.append(f"{row.id}: quantity mismatch")
            continue
        value = float(measured.value_si)
        active = _active(row, value)
        check = {**base, "status": "DEVIATION" if active else "NORMAL", "value_si": value,
                 "quantity": measured.quantity, "threshold_low_si": row.threshold_low_si,
                 "threshold_high_si": row.threshold_high_si}
        checks.append(check)
        if not active:
            continue
        supported = row.scenario_family in scenario_families_for_release(
            row.component_kind, row.release_mode
        )
        if not supported:
            check["status"] = "SCENARIO_MAPPING_BLOCKED"
            check["reason"] = "scenario family is not a valid release mapping for this component/mode"
            blocking.append(f"{row.id}: scenario mapping blocked")
            continue
        selected.append({
            "scenario_id": f"{row.id}:{frame.operating_mode}:{row.scenario_family}",
            "hazop_row_id": row.id,
            "component_id": row.component_id,
            "component_kind": row.component_kind,
            "operating_mode": frame.operating_mode,
            "scenario_family": row.scenario_family,
            "release_mode": row.release_mode,
            "priority": row.priority,
            "measured_value_si": value,
            "trigger": row.trigger,
            "threshold_low_si": row.threshold_low_si,
            "threshold_high_si": row.threshold_high_si,
            "provider_release_status": "REQUIRED_NOT_CREATED",
            "provider_release_required": True,
            "frequency_assignment": "not_performed; bind an explicit literature event downstream",
            "source": row.provenance,
        })
    if selected:
        status = "SCENARIOS_SELECTED" if not blocking else "SCENARIOS_SELECTED_WITH_OPEN_INPUTS"
    elif blocking:
        status = "BLOCKED_OPEN_INPUTS"
    elif not applicable:
        status = "NO_APPLICABLE_MODE_ROW"
    else:
        status = "NO_DEVIATION"
    return {
        "schema_version": HAZOP_SCHEMA,
        "status": status,
        "facility_id": frame.facility_id,
        "table_id": table.id,
        "table_digest": table_digest,
        "state_digest": state_digest,
        "component_id": frame.component_id,
        "operating_mode": frame.operating_mode,
        "captured_at_s": frame.captured_at_s,
        "applicable_row_count": len(applicable),
        "active_deviation_count": sum(row["status"] == "DEVIATION" for row in checks),
        "selected_scenario_count": len(selected),
        "checks": checks,
        "selected_scenarios": selected,
        "blocking_reasons": blocking,
        "policy": {
            "operating_mode_taken_from_input": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "release_packet_created": False,
            "consequence_calculated": False,
            "facility_qra_claim": False,
        },
        "interpretation": (
            "HAZOP and operating-mode selection only; selected scenarios require an explicit "
            "equipment provider release packet before consequence analysis."
        ),
    }


def hazop_state_from_runtime_frame(
    frame: Mapping[str, Any],
    *,
    facility_id: str,
    now_s: float,
    mapping_digest: str | None = None,
) -> HazopStateFrame:
    """Convert a verified observed-state runtime frame into a HAZOP frame.

    The runtime adapter verifies frame/state digests and rejects accident-owned
    fields first.  A frame without an explicit operating mode is rejected;
    HAZOP never guesses a mode from pressure, flow, or a tag name.
    """
    from .observed_state_runtime import service_state_from_runtime_frame

    normalized = service_state_from_runtime_frame(
        frame, now_s=now_s, mapping_digest=mapping_digest
    )
    mode = normalized.get("operating_mode")
    if not isinstance(mode, str) or not mode.strip():
        raise HazopSelectionError(
            "runtime frame has no operating_mode; HAZOP scenario selection is withheld"
        )
    values: dict[str, StateMeasurement] = {}
    for tag, raw in normalized["values"].items():
        try:
            values[tag] = StateMeasurement.model_validate_json(
                json.dumps({
                    "quantity": raw["quantity"],
                    "value_si": raw["value_si"],
                    "sensor_location": raw.get("sensor_location"),
                    "quality": raw.get("quality", "valid"),
                }, allow_nan=False)
            )
        except Exception as error:
            raise HazopSelectionError(
                f"runtime HAZOP value {tag} is invalid: {error}"
            ) from error
    return HazopStateFrame(
        schema_version=HAZOP_STATE_SCHEMA,
        facility_id=facility_id,
        component_id=str(frame["component_id"]),
        operating_mode=mode,
        captured_at_s=float(frame["captured_at_s"]),
        values=values,
        state_snapshot_digest=frame.get("state_snapshot_digest"),
        source_digest=frame.get("source_sha256"),
        source_provenance=str(frame.get("source_id") or "runtime-frame"),
    )


def evaluate_hazop_runtime_frame(
    table: HazopTable | Mapping[str, Any],
    frame: Mapping[str, Any],
    *,
    now_s: float,
    mapping_digest: str | None = None,
) -> dict[str, Any]:
    """Run HAZOP selection directly on one verified runtime frame."""
    if isinstance(table, HazopTable):
        facility_id = table.facility_id
    elif isinstance(table, Mapping):
        facility_id = str(table.get("facility_id") or "")
    else:
        raise HazopSelectionError("HAZOP table must provide facility_id")
    state = hazop_state_from_runtime_frame(
        frame, facility_id=facility_id, now_s=now_s, mapping_digest=mapping_digest
    )
    return evaluate_hazop(table, state)


def run_hazop_runtime_consequence(
    table: HazopTable | Mapping[str, Any],
    frame: Mapping[str, Any],
    *,
    now_s: float,
    template: Any,
    monitor: Any,
    release_resolver: Any,
    mapping_digest: str | None = None,
) -> dict[str, Any]:
    """Gate one runtime consequence update with the mode-specific HAZOP result.

    The existing runtime monitor still owns normalization, provider packet
    validation, termination, SLABx-LH2 execution, and consequence output.  This
    adapter only decides whether that monitor may be called.  A single selected
    HAZOP row is required because a provider resolver returns one release
    request; multiple active rows must be dispatched as separate branches by
    the calling application.  The provider request is checked against the
    selected component kind, release mode, and accident family before any
    consequence calculation is accepted.
    """
    selection = evaluate_hazop_runtime_frame(
        table,
        frame,
        now_s=now_s,
        mapping_digest=mapping_digest,
    )
    base: dict[str, Any] = {
        "schema_version": "prism.hazop_runtime_consequence_gate.v1",
        "selection": selection,
        "consequence": None,
        "policy": {
            "operating_mode_taken_from_input": True,
            "provider_release_created_by_prism": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_claim": False,
        },
    }
    if selection["status"] != "SCENARIOS_SELECTED":
        base.update({
            "status": f"WITHHELD_HAZOP_{selection['status']}",
            "reason": (
                "HAZOP did not produce one clean active scenario; provider release "
                "and consequence calculation were not called"
            ),
        })
        return base
    selected = selection["selected_scenarios"]
    if len(selected) != 1:
        base.update({
            "status": "WITHHELD_SCENARIO_BRANCH_DISPATCH_REQUIRED",
            "reason": (
                "one runtime frame selected multiple accident branches; each branch "
                "requires an explicit provider request and separate consequence call"
            ),
        })
        return base
    if not callable(release_resolver):
        base.update({
            "status": "WITHHELD_PROVIDER_RELEASE_REQUIRED",
            "reason": "selected HAZOP scenario has no equipment provider release resolver",
        })
        return base
    update = getattr(monitor, "update_from_runtime_frame", None)
    if not callable(update):
        raise HazopSelectionError(
            "monitor must provide update_from_runtime_frame for the HAZOP runtime gate"
        )

    scenario = selected[0]

    def guarded_resolver(template_arg: Any, normalized: Mapping[str, Any]) -> Any:
        request = release_resolver(template_arg, normalized)
        if getattr(request, "component_id", None) != scenario["component_id"]:
            raise HazopSelectionError(
                "provider release component does not match the selected HAZOP component"
            )
        families = scenario_families_for_request(
            scenario["component_kind"],
            scenario["release_mode"],
            request,
        )
        if scenario["scenario_family"] not in families:
            raise HazopSelectionError(
                "provider release does not support the selected HAZOP scenario family"
            )
        definition = scenario_definition(scenario["scenario_family"])
        source_operator = getattr(request, "source_operator", None)
        if source_operator not in definition["required_source_operators"]:
            raise HazopSelectionError(
                "provider source operator does not satisfy the selected HAZOP scenario family"
            )
        termination = getattr(request, "release_termination", None)
        if termination is None or termination.basis not in definition["termination_bases"]:
            raise HazopSelectionError(
                "provider termination basis does not satisfy the selected HAZOP scenario family"
            )
        owners = []
        for attribute in ("resolved_release", "resolved_liquid_release"):
            owner = getattr(request, attribute, None)
            if owner is not None:
                owners.append(owner)
        release_set = getattr(request, "resolved_release_set", None)
        if release_set is not None:
            owners.extend(release_set.releases)
        expected_event_kind = (
            "emergency_relief"
            if scenario["release_mode"] == "maximum_relief_discharge"
            else "accidental_leak"
        )
        if not owners or any(
            getattr(owner, "event_kind", None) != expected_event_kind for owner in owners
        ):
            raise HazopSelectionError(
                "provider event kind does not satisfy the selected HAZOP release mode"
            )
        return request

    try:
        consequence = update(
            template,
            frame,
            now_s=float(now_s),
            release_resolver=guarded_resolver,
            mapping_digest=mapping_digest,
        )
    except Exception as error:
        base.update({
            "status": "CONSEQUENCE_REJECTED",
            "error_type": type(error).__name__,
            "reason": str(error),
        })
        return base
    base.update({
        "status": "CONSEQUENCE_EVALUATED",
        "consequence": consequence,
        "policy": {
            **base["policy"],
            "consequence_calculated": True,
            "provider_release_required": True,
            "provider_release_validated_by_scenario": True,
        },
    })
    return base


def run_hazop_runtime_consequence_branches(
    table: HazopTable | Mapping[str, Any],
    frame: Mapping[str, Any],
    *,
    now_s: float,
    template: Any,
    monitor: Any,
    release_resolvers: Mapping[str, Any],
    mapping_digest: str | None = None,
) -> dict[str, Any]:
    """Dispatch several active HAZOP rows as separate consequence branches.

    The resolver map is keyed by each selected ``scenario_id``.  Each branch
    is evaluated through :func:`run_hazop_runtime_consequence` with a one-row
    HAZOP table, so no provider history, termination basis, or frequency is
    silently shared between simultaneous accident hypotheses.  Missing branch
    resolvers remain explicitly withheld while other valid branches may run.
    """
    if not isinstance(release_resolvers, Mapping):
        raise HazopSelectionError("release_resolvers must map scenario_id to a provider resolver")
    selection = evaluate_hazop_runtime_frame(
        table,
        frame,
        now_s=now_s,
        mapping_digest=mapping_digest,
    )
    result: dict[str, Any] = {
        "schema_version": "prism.hazop_runtime_consequence_branches.v1",
        "status": None,
        "selection": selection,
        "branches": [],
        "policy": {
            "operating_mode_taken_from_input": True,
            "provider_release_created_by_prism": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_claim": False,
            "branches_auto_merged": False,
        },
    }
    if selection["status"] != "SCENARIOS_SELECTED":
        result["status"] = f"WITHHELD_HAZOP_{selection['status']}"
        result["reason"] = (
            "HAZOP did not produce clean active scenarios; no provider branch was called"
        )
        return result
    if isinstance(table, HazopTable):
        table_model = table
    else:
        try:
            table_model = HazopTable.model_validate_json(json.dumps(table, allow_nan=False))
        except Exception as error:
            raise HazopSelectionError(f"invalid HAZOP table: {error}") from error
    for scenario in selection["selected_scenarios"]:
        row = next(
            (candidate for candidate in table_model.rows if candidate.id == scenario["hazop_row_id"]),
            None,
        )
        if row is None:
            raise HazopSelectionError("selected HAZOP row disappeared during branch dispatch")
        branch_table = table_model.model_copy(update={"rows": (row,)})
        resolver = release_resolvers.get(scenario["scenario_id"])
        branch = run_hazop_runtime_consequence(
            branch_table,
            frame,
            now_s=now_s,
            template=template,
            monitor=monitor,
            release_resolver=resolver,
            mapping_digest=mapping_digest,
        )
        result["branches"].append({
            "scenario_id": scenario["scenario_id"],
            "scenario_family": scenario["scenario_family"],
            "release_mode": scenario["release_mode"],
            "result": branch,
        })
    branch_statuses = [row["result"]["status"] for row in result["branches"]]
    result["status"] = (
        "CONSEQUENCE_BRANCHES_EVALUATED"
        if branch_statuses and all(status == "CONSEQUENCE_EVALUATED" for status in branch_statuses)
        else "CONSEQUENCE_BRANCHES_PARTIAL"
    )
    result["policy"]["consequence_calculated"] = any(
        status == "CONSEQUENCE_EVALUATED" for status in branch_statuses
    )
    result["policy"]["provider_release_validated_by_scenario"] = all(
        status == "CONSEQUENCE_EVALUATED" for status in branch_statuses
    )
    return result


def run_hazop_facility_runtime(
    table: HazopTable | Mapping[str, Any],
    frames: Mapping[str, Mapping[str, Any]],
    *,
    now_s: float,
    component_bindings: Mapping[str, Any],
    release_resolvers: Mapping[str, Any],
    mapping_digest: str | None = None,
) -> dict[str, Any]:
    """Coordinate HAZOP-gated consequence branches for several components.

    ``component_bindings`` contains the existing runtime monitor and template
    for each component.  ``release_resolvers`` is keyed by HAZOP
    ``scenario_id`` so one provider history cannot be reused for another
    accident branch.  The returned facility ledger exposes conditional
    current-weather IR contributions when a single branch per component has a
    reviewed frequency binding.  It deliberately withholds annual facility
    IR/F-N: HAZOP deviations are an operator-triggered view, not a replacement
    for the full literature event catalogue and all-weather facility campaign.
    """
    if not isinstance(frames, Mapping) or not isinstance(component_bindings, Mapping):
        raise HazopSelectionError("frames and component_bindings must be mappings")
    if not isinstance(release_resolvers, Mapping):
        raise HazopSelectionError("release_resolvers must map scenario_id to a resolver")
    if not component_bindings:
        raise HazopSelectionError("component_bindings must not be empty")
    components: dict[str, Any] = {}
    risk_atoms: list[dict[str, Any]] = []
    for component_id in sorted(component_bindings):
        binding = component_bindings[component_id]
        frame = frames.get(component_id)
        if frame is None:
            components[component_id] = {
                "status": "WITHHELD_MISSING_RUNTIME_FRAME",
                "component_id": component_id,
                "selection": None,
                "branches": [],
                "reason": "facility runtime snapshot has no frame for this component",
            }
            continue
        try:
            selection = evaluate_hazop_runtime_frame(
                table,
                frame,
                now_s=now_s,
                mapping_digest=mapping_digest,
            )
            if selection["status"] != "SCENARIOS_SELECTED":
                components[component_id] = {
                    "status": f"WITHHELD_HAZOP_{selection['status']}",
                    "component_id": component_id,
                    "selection": selection,
                    "branches": [],
                    "reason": "no clean active HAZOP branch was available for consequence evaluation",
                }
                continue
            template = getattr(binding, "template", None)
            monitor = getattr(binding, "monitor", None)
            if template is None or monitor is None:
                raise HazopSelectionError(
                    "component binding must expose template and monitor"
                )
            branch_resolvers = {
                row["scenario_id"]: release_resolvers.get(row["scenario_id"])
                for row in selection["selected_scenarios"]
            }
            branch_result = run_hazop_runtime_consequence_branches(
                table,
                frame,
                now_s=now_s,
                template=template,
                monitor=monitor,
                release_resolvers=branch_resolvers,
                mapping_digest=mapping_digest,
            )
            frequency = getattr(binding, "frequency_binding", None)
            branch_rows: list[dict[str, Any]] = []
            for branch in branch_result["branches"]:
                branch_copy = dict(branch)
                branch_result_row = branch_copy.get("result")
                consequence = (
                    branch_result_row.get("consequence")
                    if isinstance(branch_result_row, Mapping)
                    else None
                )
                risk = None
                if (
                    isinstance(branch_result_row, Mapping)
                    and branch_result_row.get("status") == "CONSEQUENCE_EVALUATED"
                    and isinstance(consequence, Mapping)
                ):
                    from .service import _realtime_current_weather_risk

                    risk = _realtime_current_weather_risk(consequence, frequency)
                    if risk.get("status") == "AVAILABLE_CURRENT_WEATHER_IR":
                        risk_atoms.append({
                            "component_id": component_id,
                            "scenario_id": branch_copy["scenario_id"],
                            "scenario_family": branch_copy["scenario_family"],
                            "risk": risk,
                        })
                branch_copy["risk"] = risk
                branch_rows.append(branch_copy)
            components[component_id] = {
                "status": branch_result["status"],
                "component_id": component_id,
                "selection": selection,
                "branches": branch_rows,
                "policy": branch_result["policy"],
            }
        except Exception as error:
            components[component_id] = {
                "status": "REJECTED",
                "component_id": component_id,
                "selection": None,
                "branches": [],
                "error_type": type(error).__name__,
                "reason": str(error),
            }

    branch_counts = [
        len(row.get("branches", ()))
        for row in components.values()
        if isinstance(row, Mapping) and row.get("branches")
    ]
    multiple_branch = any(count > 1 for count in branch_counts)
    if risk_atoms and not multiple_branch:
        receptor_totals: dict[str, list[float]] = {}
        for atom in risk_atoms:
            risk = atom["risk"]
            annual_ir = risk.get("annual_ir_low_high")
            if not isinstance(annual_ir, Mapping):
                continue
            for receptor_id, values in annual_ir.items():
                if not isinstance(values, (list, tuple)) or len(values) != 2:
                    continue
                total = receptor_totals.setdefault(str(receptor_id), [0.0, 0.0])
                total[0] += float(values[0])
                total[1] += float(values[1])
        conditional_risk = {
            "status": "AVAILABLE_CONDITIONAL_CURRENT_WEATHER_IR",
            "annual_ir_low_high_by_receptor": receptor_totals,
            "risk_atom_count": len(risk_atoms),
            "frequency_learning": False,
            "interpretation": (
                "sum of explicitly bound HAZOP-selected component contributions for the "
                "current weather only; this is not a full facility annual IR/F-N result"
            ),
        }
    elif multiple_branch:
        conditional_risk = {
            "status": "WITHHELD_BRANCH_WEIGHT_REQUIRED",
            "annual_ir_low_high_by_receptor": None,
            "risk_atom_count": len(risk_atoms),
            "reason": "multiple active branches require explicit branch probabilities before aggregation",
        }
    else:
        conditional_risk = {
            "status": "WITHHELD_NO_ACCEPTED_HAZOP_RISK_ATOM",
            "annual_ir_low_high_by_receptor": None,
            "risk_atom_count": 0,
            "reason": "no selected branch produced a current-weather IR contribution",
        }
    rejected = [
        component_id
        for component_id, row in components.items()
        if row.get("status") not in {"WITHHELD_HAZOP_NO_DEVIATION", "WITHHELD_HAZOP_NO_APPLICABLE_MODE_ROW"}
        and not str(row.get("status", "")).startswith("CONSEQUENCE_BRANCHES_EVALUATED")
    ]
    status = "FACILITY_HAZOP_RUNTIME_EVALUATED" if not rejected else "FACILITY_HAZOP_RUNTIME_PARTIAL"
    return {
        "schema_version": "prism.hazop_facility_runtime.v1",
        "status": status,
        "component_count": len(component_bindings),
        "components": components,
        "risk_atoms": risk_atoms,
        "conditional_current_weather_risk": conditional_risk,
        "facility_annual_ir_available": False,
        "facility_fn_available": False,
        "policy": {
            "operating_mode_taken_from_input": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_annual_qra_promotion": False,
            "branch_results_auto_merged": False,
        },
    }


__all__ = [
    "HAZOP_SCHEMA", "HAZOP_STATE_SCHEMA", "HazopSelectionError",
    "HazopRow", "HazopTable", "HazopStateFrame", "evaluate_hazop",
    "hazop_state_from_runtime_frame", "evaluate_hazop_runtime_frame",
    "run_hazop_runtime_consequence", "run_hazop_runtime_consequence_branches",
    "run_hazop_facility_runtime",
]
