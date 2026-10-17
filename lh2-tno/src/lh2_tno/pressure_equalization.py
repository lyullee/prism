"""Audit a provider history for a pressure-equalization release candidate.

The audit is intentionally read-only.  It does not rewrite a provider packet,
replace a bounded horizon, or promote a provider result.  It identifies the
earliest interval at which a provider-exported source state no longer drives
outward flow and then checks that the provider kept recording zero flow for a
short observation tail.  A caller may use the result to request an explicit
``model_pressure_equalization`` packet from the equipment model.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


SCHEMA = "prism.provider_pressure_equalization_audit.v1"
MASS_TOLERANCE_KG = 1.0e-8
DEFAULT_FLOW_TOLERANCE_KG_S = 1.0e-12
DEFAULT_PRESSURE_TOLERANCE_PA = 1.0e-3


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _payload(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    data = packet.get("data")
    return data if isinstance(data, Mapping) else packet


def _steps(packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = _payload(packet).get("steps")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [row for row in raw if isinstance(row, Mapping)]


def _mass_balance(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = _payload(packet)
    value = payload.get("provider_mass_balance")
    if isinstance(value, Mapping):
        return value
    meta = payload.get("provider_meta")
    return meta if isinstance(meta, Mapping) else {}


def _dynamic_closure(balance: Mapping[str, Any]) -> Mapping[str, Any]:
    value = balance.get("dynamic_state_closure")
    return value if isinstance(value, Mapping) else {}


def audit_provider_pressure_equalization(
    packet: Mapping[str, Any],
    *,
    minimum_zero_flow_intervals: int = 2,
    flow_tolerance_kg_s: float = DEFAULT_FLOW_TOLERANCE_KG_S,
    pressure_tolerance_pa: float = DEFAULT_PRESSURE_TOLERANCE_PA,
) -> dict[str, Any]:
    """Return a diagnostic pressure-equalization candidate for one packet.

    The source state is taken from ``provider_source_state`` on each resolved
    interval.  A candidate requires a positive-flow interval before the first
    zero-flow interval, a source pressure at or below ambient at that point,
    and at least ``minimum_zero_flow_intervals`` consecutive zero-flow rows.
    Dynamic state and mass ledgers must also be explicitly closed.  These
    conditions are evidence checks only; the result never changes the packet's
    termination basis or enables provider/frequency/facility promotion.
    """
    if not isinstance(packet, Mapping):
        raise TypeError("packet must be a mapping")
    if (
        isinstance(minimum_zero_flow_intervals, bool)
        or not isinstance(minimum_zero_flow_intervals, int)
        or minimum_zero_flow_intervals < 1
    ):
        raise ValueError("minimum_zero_flow_intervals must be a positive integer")
    if (
        isinstance(flow_tolerance_kg_s, bool)
        or not isinstance(flow_tolerance_kg_s, (int, float))
        or not math.isfinite(float(flow_tolerance_kg_s))
        or float(flow_tolerance_kg_s) < 0.0
    ):
        raise ValueError("flow_tolerance_kg_s must be finite and non-negative")
    if (
        isinstance(pressure_tolerance_pa, bool)
        or not isinstance(pressure_tolerance_pa, (int, float))
        or not math.isfinite(float(pressure_tolerance_pa))
        or float(pressure_tolerance_pa) < 0.0
    ):
        raise ValueError("pressure_tolerance_pa must be finite and non-negative")

    payload = _payload(packet)
    rows = _steps(packet)
    ambient = _finite(packet.get("ambient_pressure_pa_abs", payload.get("ambient_pressure_pa_abs")))
    balance = _mass_balance(packet)
    closure = _dynamic_closure(balance)
    reasons: list[str] = []
    checks: dict[str, bool] = {
        "steps_present": bool(rows),
        "ambient_pressure_present": ambient is not None and ambient > 0.0,
        "provider_source_state_complete": False,
        "positive_flow_precedes_zero_flow": False,
        "source_pressure_non_outward_at_zero_flow": False,
        "zero_flow_observation_tail_complete": False,
        "dynamic_state_closure_present": bool(closure),
        "dynamic_state_closure_closed": False,
        "mass_ledger_present": False,
        "mass_ledger_closed": False,
    }

    if not rows:
        reasons.append("provider steps history is missing")
    if ambient is None or ambient <= 0.0:
        reasons.append("ambient pressure is missing or invalid")

    source_rows: list[tuple[float, float, float]] = []
    missing_source_state = False
    for index, row in enumerate(rows):
        time_s = _finite(row.get("time_s"))
        flow = _finite(row.get("mass_flow_kg_s"))
        source = row.get("provider_source_state")
        source_pressure = _finite(source.get("source_pressure_pa_abs")) if isinstance(source, Mapping) else None
        if time_s is None or flow is None or flow < 0.0 or source_pressure is None:
            missing_source_state = True
            continue
        source_rows.append((time_s, flow, source_pressure))
    checks["provider_source_state_complete"] = bool(rows) and not missing_source_state and len(source_rows) == len(rows)
    if not checks["provider_source_state_complete"]:
        reasons.append("provider source pressure/flow state is incomplete")

    candidate_index: int | None = None
    if checks["provider_source_state_complete"] and ambient is not None:
        for index, (time_s, flow, source_pressure) in enumerate(source_rows):
            if flow <= float(flow_tolerance_kg_s) and source_pressure <= ambient + float(pressure_tolerance_pa):
                if index > 0 and source_rows[index - 1][1] > float(flow_tolerance_kg_s):
                    candidate_index = index
                    break
        checks["positive_flow_precedes_zero_flow"] = candidate_index is not None
        if candidate_index is None:
            reasons.append("no provider interval shows positive flow followed by non-outward zero flow")
        else:
            checks["source_pressure_non_outward_at_zero_flow"] = True
            tail = source_rows[candidate_index:]
            checks["zero_flow_observation_tail_complete"] = len(tail) >= minimum_zero_flow_intervals and all(
                flow <= float(flow_tolerance_kg_s) for _, flow, _ in tail[:minimum_zero_flow_intervals]
            )
            if not checks["zero_flow_observation_tail_complete"]:
                reasons.append("provider zero-flow observation tail is shorter than required")

    initial = _finite(balance.get("initial_mass_kg"))
    final = _finite(balance.get("final_mass_kg"))
    released = _finite(balance.get("cumulative_mass_out_kg", payload.get("cumulative_mass_out_kg")))
    cumulative_in = _finite(balance.get("cumulative_mass_in_kg"))
    if cumulative_in is None:
        cumulative_in = 0.0
    checks["mass_ledger_present"] = all(value is not None and value >= 0.0 for value in (initial, final, released, cumulative_in))
    residual = _finite(balance.get("derived_accounting_residual_kg"))
    if checks["mass_ledger_present"]:
        expected = float(final) + float(released) - float(initial) - float(cumulative_in)
        checks["mass_ledger_closed"] = residual is not None and abs(expected) <= MASS_TOLERANCE_KG and abs(residual) <= MASS_TOLERANCE_KG
    if not checks["mass_ledger_present"] or not checks["mass_ledger_closed"]:
        reasons.append("provider mass ledger is missing or not closed")

    checks["dynamic_state_closure_closed"] = (
        checks["dynamic_state_closure_present"]
        and closure.get("inventory_feedback_closed") is True
        and closure.get("pressure_feedback_closed") is True
        and _finite(closure.get("max_abs_inventory_residual_kg")) is not None
        and _finite(closure.get("inventory_tolerance_kg")) is not None
        and float(closure["max_abs_inventory_residual_kg"]) <= float(closure["inventory_tolerance_kg"])
        and _finite(closure.get("max_abs_pressure_residual_pa")) is not None
        and _finite(closure.get("pressure_tolerance_pa")) is not None
        and float(closure["max_abs_pressure_residual_pa"]) <= float(closure["pressure_tolerance_pa"])
    )
    if not checks["dynamic_state_closure_closed"]:
        reasons.append("provider dynamic pressure/inventory closure is missing or not closed")

    candidate_time = None
    observation_s = None
    terminal_pressure = None
    if candidate_index is not None and checks["zero_flow_observation_tail_complete"]:
        candidate_time = source_rows[candidate_index][0]
        last_index = candidate_index + minimum_zero_flow_intervals - 1
        observation_s = max(0.0, source_rows[last_index][0] - candidate_time)
        terminal_pressure = source_rows[last_index][2]

    reasons = list(dict.fromkeys(reasons))
    ready = not reasons
    return {
        "schema_version": SCHEMA,
        "status": "PRESSURE_EQUALIZATION_CANDIDATE" if ready else "PRESSURE_EQUALIZATION_EVIDENCE_OPEN",
        "diagnostic_only": True,
        "event_id": payload.get("event_id", packet.get("event_id")),
        "component_id": payload.get("component_id", packet.get("component_id")),
        "port_id": payload.get("port_id", packet.get("port_id")),
        "current_termination_basis": payload.get("termination_basis", packet.get("termination_basis")),
        "checks": checks,
        "blocking_reasons": reasons,
        "candidate_termination": {
            "basis": "model_pressure_equalization" if ready else None,
            "time_s": candidate_time,
            "observation_s": observation_s,
            "terminal_source_pressure_pa_abs": terminal_pressure,
            "ambient_pressure_pa_abs": ambient,
            "flow_tolerance_kg_s": float(flow_tolerance_kg_s),
            "pressure_tolerance_pa": float(pressure_tolerance_pa),
            "provenance": (
                "derived from provider-exported source pressure and zero-flow history; "
                "requires provider re-export with this termination basis before packet mutation"
            ),
        },
        "promotion_gates": {
            "packet_mutation_allowed": False,
            "qualified_provider_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "physical_validation_claim": False,
        },
    }


__all__ = ["SCHEMA", "audit_provider_pressure_equalization"]
