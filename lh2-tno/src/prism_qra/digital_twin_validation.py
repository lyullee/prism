"""Pre-commissioning verification harness for the safety digital twin.

The physical plant is not yet available.  This module therefore does not
pretend to validate physical--digital convergence.  It tests the part that is
available before commissioning: transactional telemetry ingestion, state
management, timing, fault detection, traceability and deterministic execution.

The five evidence groups follow ISO/IEC 30186:2025 (convergence, capability,
integrated view, time and trustworthiness).  Numerical acceptance limits are
project requirements, not limits prescribed by that standard.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable, Mapping, Sequence


Number = int | float
TelemetryScalar = Number | bool
Analyzer = Callable[[Mapping[str, TelemetryScalar]], Mapping[str, object]]
Constraint = Callable[[Mapping[str, TelemetryScalar]], str | None]


class PlantState(str, Enum):
    STANDBY = "STANDBY"
    UNLOADING = "UNLOADING"
    FILLING = "FILLING"
    RELIEF = "RELIEF"
    ESD = "ESD"


class RejectReason(str, Enum):
    DUPLICATE_SEQUENCE = "DUPLICATE_SEQUENCE"
    OUT_OF_ORDER_SEQUENCE = "OUT_OF_ORDER_SEQUENCE"
    CLOCK_REVERSED = "CLOCK_REVERSED"
    STALE_FRAME = "STALE_FRAME"
    MISSING_TAG = "MISSING_TAG"
    UNKNOWN_TAG = "UNKNOWN_TAG"
    BAD_QUALITY = "BAD_QUALITY"
    BAD_UNIT = "BAD_UNIT"
    BAD_TYPE = "BAD_TYPE"
    NONFINITE = "NONFINITE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    CROSS_FIELD_INCONSISTENCY = "CROSS_FIELD_INCONSISTENCY"
    FORBIDDEN_STATE_TRANSITION = "FORBIDDEN_STATE_TRANSITION"
    ANALYSIS_FAILURE = "ANALYSIS_FAILURE"


@dataclass(frozen=True)
class TagSpec:
    tag: str
    unit: str
    kind: str = "number"
    minimum: float | None = None
    maximum: float | None = None
    required: bool = True
    alignment_abs_tolerance: float = 0.0

    def __post_init__(self):
        if not self.tag.strip() or not self.unit.strip():
            raise ValueError("tag and unit must not be blank")
        if self.kind not in {"number", "boolean"}:
            raise ValueError("kind must be 'number' or 'boolean'")
        if (self.minimum is not None and self.maximum is not None
                and self.minimum > self.maximum):
            raise ValueError("minimum cannot exceed maximum")
        if self.alignment_abs_tolerance < 0.0:
            raise ValueError("alignment tolerance cannot be negative")
        for name, value in (("minimum", self.minimum),
                            ("maximum", self.maximum),
                            ("alignment tolerance",
                             self.alignment_abs_tolerance)):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class TelemetryValue:
    value: TelemetryScalar
    unit: str
    quality: str = "VALID"


@dataclass(frozen=True)
class TelemetryFrame:
    sequence: int
    source_time_s: float
    arrival_time_s: float
    values: Mapping[str, TelemetryValue]
    stream_id: str = "virtual-historian"


@dataclass(frozen=True)
class FrameExpectation:
    frame: TelemetryFrame
    expected_accept: bool
    expected_state: PlantState | None = None
    expected_values: Mapping[str, TelemetryScalar] | None = None
    injected_fault: str | None = None
    expected_reason_prefix: str | None = None


@dataclass(frozen=True)
class FrameResult:
    sequence: int
    trace_id: str
    accepted: bool
    reasons: tuple[str, ...]
    state: str | None
    transport_latency_ms: float
    processing_latency_ms: float
    end_to_end_latency_ms: float
    output_hash: str | None


@dataclass(frozen=True)
class ReplayMetrics:
    n_frames: int
    n_expected_valid: int
    n_injected_faults: int
    n_accepted: int
    n_rejected: int
    detected_faults: int
    false_accepts: int
    false_rejects: int
    fault_detection_rate: float
    false_accept_rate: float
    valid_frame_acceptance_rate: float
    state_accuracy: float
    state_alignment_ratio: float
    traceability_coverage: float
    p50_processing_latency_ms: float
    p95_processing_latency_ms: float
    p99_processing_latency_ms: float
    p95_end_to_end_latency_ms: float
    max_recovery_time_ms: float
    rejection_reasons: Mapping[str, int]


@dataclass(frozen=True)
class ReplayReport:
    metrics: ReplayMetrics
    results: tuple[FrameResult, ...]


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percentile / 100.0
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return ordered[low]
    weight = index - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SafetyStateResolver:
    """Resolve advisory plant state and reject impossible combinations."""

    _ALLOWED = {
        None: set(PlantState),
        PlantState.STANDBY: set(PlantState),
        PlantState.UNLOADING: {
            PlantState.UNLOADING, PlantState.STANDBY,
            PlantState.RELIEF, PlantState.ESD,
        },
        PlantState.FILLING: {
            PlantState.FILLING, PlantState.STANDBY,
            PlantState.RELIEF, PlantState.ESD,
        },
        PlantState.RELIEF: {
            PlantState.RELIEF, PlantState.STANDBY, PlantState.ESD,
        },
        PlantState.ESD: {PlantState.ESD, PlantState.STANDBY},
    }

    def __init__(self, active_flow_kg_s: float = 0.01,
                 relief_open_pct: float = 5.0):
        self.active_flow_kg_s = active_flow_kg_s
        self.relief_open_pct = relief_open_pct

    def resolve(self, values: Mapping[str, TelemetryScalar]) -> PlantState:
        unloading = float(values["UNLOADING_FLOW_KG_S"])
        filling = float(values["FILLING_FLOW_KG_S"])
        if unloading > self.active_flow_kg_s and filling > self.active_flow_kg_s:
            raise ValueError("filling and unloading flows are active together")
        if values["ESD_ACTIVE"] is True:
            return PlantState.ESD
        if float(values["RELIEF_POSITION_PCT"]) > self.relief_open_pct:
            return PlantState.RELIEF
        if unloading > self.active_flow_kg_s:
            return PlantState.UNLOADING
        if filling > self.active_flow_kg_s:
            return PlantState.FILLING
        return PlantState.STANDBY

    def transition_allowed(self, old: PlantState | None,
                           new: PlantState) -> bool:
        return new in self._ALLOWED[old]


class DigitalTwinMonitor:
    """Transactional boundary for ONE plant state with redundant streams.

    Independent assets require separate monitors. Sequence histories are
    stream-local, but no stream may rewind the shared accepted plant state.
    """

    def __init__(self, specs: Sequence[TagSpec], analyzer: Analyzer,
                 *, max_frame_age_ms: float = 1000.0,
                 constraints: Sequence[Constraint] = (),
                 model_version: str = "precommissioning-v1",
                 sequence_history_limit: int = 10_000):
        self.specs = {spec.tag: spec for spec in specs}
        if len(self.specs) != len(specs):
            raise ValueError("tag specifications must be unique")
        if not math.isfinite(max_frame_age_ms) or max_frame_age_ms <= 0.0:
            raise ValueError("max_frame_age_ms must be finite and positive")
        if (isinstance(sequence_history_limit, bool)
                or not isinstance(sequence_history_limit, int)
                or sequence_history_limit <= 0):
            raise ValueError("sequence_history_limit must be a positive integer")
        self.analyzer = analyzer
        self.max_frame_age_ms = max_frame_age_ms
        self.constraints = tuple(constraints)
        self.model_version = model_version
        self.resolver = SafetyStateResolver()
        self.state: dict[str, TelemetryScalar] = {}
        self.plant_state: PlantState | None = None
        self.sequence_history_limit = sequence_history_limit
        self._seen_sequences: dict[str, set[int]] = {}
        self._sequence_history: dict[str, deque[int]] = {}
        self._highest_sequence: dict[str, int] = {}
        self._last_source_time_s: dict[str, float] = {}
        self._last_arrival_time_s: dict[str, float] = {}
        self._plant_source_time_s: float | None = None
        self._plant_arrival_time_s: float | None = None

    def _remember_sequence(self, stream_id: str, sequence: int) -> None:
        seen = self._seen_sequences.setdefault(stream_id, set())
        history = self._sequence_history.setdefault(stream_id, deque())
        if len(history) >= self.sequence_history_limit:
            seen.discard(history.popleft())
        history.append(sequence)
        seen.add(sequence)
        self._highest_sequence[stream_id] = sequence

    def _validate_value(self, spec: TagSpec, sample: TelemetryValue,
                        reasons: list[str]) -> TelemetryScalar | None:
        if not isinstance(sample, TelemetryValue):
            reasons.append(f"{RejectReason.BAD_TYPE.value}:{spec.tag}")
            return None
        if sample.quality != "VALID":
            reasons.append(f"{RejectReason.BAD_QUALITY.value}:{spec.tag}")
        if sample.unit != spec.unit:
            reasons.append(f"{RejectReason.BAD_UNIT.value}:{spec.tag}")
        value = sample.value
        if spec.kind == "boolean":
            if type(value) is not bool:
                reasons.append(f"{RejectReason.BAD_TYPE.value}:{spec.tag}")
                return None
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            reasons.append(f"{RejectReason.BAD_TYPE.value}:{spec.tag}")
            return None
        numeric = float(value)
        if not math.isfinite(numeric):
            reasons.append(f"{RejectReason.NONFINITE.value}:{spec.tag}")
            return None
        if spec.minimum is not None and numeric < spec.minimum:
            reasons.append(f"{RejectReason.OUT_OF_RANGE.value}:{spec.tag}")
        if spec.maximum is not None and numeric > spec.maximum:
            reasons.append(f"{RejectReason.OUT_OF_RANGE.value}:{spec.tag}")
        return numeric

    def process(self, frame: TelemetryFrame) -> FrameResult:
        started = time.perf_counter()
        trace_id = f"{frame.stream_id}:{frame.sequence}"
        reasons: list[str] = []

        stream_valid = (
            isinstance(frame.stream_id, str) and bool(frame.stream_id.strip())
        )
        if not stream_valid:
            reasons.append(f"{RejectReason.BAD_TYPE.value}:stream_id")
        sequence_valid = type(frame.sequence) is int and frame.sequence >= 0
        if not sequence_valid:
            reasons.append(f"{RejectReason.BAD_TYPE.value}:sequence")

        if stream_valid and sequence_valid:
            seen = self._seen_sequences.get(frame.stream_id, set())
            highest = self._highest_sequence.get(frame.stream_id)
            if frame.sequence in seen:
                reasons.append(RejectReason.DUPLICATE_SEQUENCE.value)
            elif highest is not None and frame.sequence < highest:
                reasons.append(RejectReason.OUT_OF_ORDER_SEQUENCE.value)

        source_valid = (
            not isinstance(frame.source_time_s, bool)
            and isinstance(frame.source_time_s, (int, float))
            and math.isfinite(float(frame.source_time_s))
        )
        arrival_valid = (
            not isinstance(frame.arrival_time_s, bool)
            and isinstance(frame.arrival_time_s, (int, float))
            and math.isfinite(float(frame.arrival_time_s))
        )
        if not source_valid:
            reasons.append(f"{RejectReason.NONFINITE.value}:source_time_s")
        if not arrival_valid:
            reasons.append(f"{RejectReason.NONFINITE.value}:arrival_time_s")

        transport_ms = 0.0
        if source_valid and arrival_valid:
            source_time_s = float(frame.source_time_s)
            arrival_time_s = float(frame.arrival_time_s)
            transport_ms = (arrival_time_s - source_time_s) * 1000.0
            last_source = (
                self._last_source_time_s.get(frame.stream_id)
                if stream_valid else None
            )
            last_arrival = (
                self._last_arrival_time_s.get(frame.stream_id)
                if stream_valid else None
            )
            if (transport_ms < 0.0
                    or (last_source is not None
                        and source_time_s < last_source)
                    or (last_arrival is not None
                        and arrival_time_s < last_arrival)
                    or (self._plant_source_time_s is not None
                        and source_time_s < self._plant_source_time_s)
                    or (self._plant_arrival_time_s is not None
                        and arrival_time_s < self._plant_arrival_time_s)):
                reasons.append(RejectReason.CLOCK_REVERSED.value)
            elif transport_ms > self.max_frame_age_ms:
                reasons.append(RejectReason.STALE_FRAME.value)

        frame_values = frame.values
        if not isinstance(frame_values, Mapping):
            reasons.append(f"{RejectReason.BAD_TYPE.value}:values")
            frame_values = {}
        if any(not isinstance(tag, str) for tag in frame_values):
            reasons.append(f"{RejectReason.BAD_TYPE.value}:tag")
        supplied = {tag for tag in frame_values if isinstance(tag, str)}
        required = {tag for tag, spec in self.specs.items() if spec.required}
        for tag in sorted(required - supplied):
            reasons.append(f"{RejectReason.MISSING_TAG.value}:{tag}")
        for tag in sorted(supplied - set(self.specs)):
            reasons.append(f"{RejectReason.UNKNOWN_TAG.value}:{tag}")

        candidate: dict[str, TelemetryScalar] = {}
        for tag in sorted(supplied & set(self.specs)):
            value = self._validate_value(self.specs[tag], frame_values[tag], reasons)
            if value is not None:
                candidate[tag] = value

        if not reasons:
            for constraint in self.constraints:
                problem = constraint(candidate)
                if problem:
                    reasons.append(
                        f"{RejectReason.CROSS_FIELD_INCONSISTENCY.value}:"
                        f"{problem}"
                    )

        if (not reasons and self._plant_source_time_s == frame.source_time_s
                and candidate != self.state):
            reasons.append(f"{RejectReason.CROSS_FIELD_INCONSISTENCY.value}:"
                           "conflicting values at the accepted plant timestamp")

        next_state = None
        if not reasons:
            try:
                next_state = self.resolver.resolve(candidate)
            except (KeyError, TypeError, ValueError) as exc:
                reasons.append(
                    f"{RejectReason.CROSS_FIELD_INCONSISTENCY.value}:{exc}"
                )
            if (next_state is not None
                    and not self.resolver.transition_allowed(
                        self.plant_state, next_state)):
                reasons.append(
                    f"{RejectReason.FORBIDDEN_STATE_TRANSITION.value}:"
                    f"{self.plant_state}->{next_state}"
                )

        output_hash = None
        if not reasons:
            try:
                analysis = dict(self.analyzer(candidate))
                output_hash = _canonical_hash({
                    "trace_id": trace_id,
                    "source_time_s": frame.source_time_s,
                    "model_version": self.model_version,
                    "plant_state": next_state.value,
                    "input": candidate,
                    "analysis": analysis,
                })
            except Exception as exc:
                reasons.append(
                    f"{RejectReason.ANALYSIS_FAILURE.value}:"
                    f"{type(exc).__name__}"
                )

        accepted = not reasons
        if accepted:
            self.state = candidate
            self.plant_state = next_state
            self._remember_sequence(frame.stream_id, frame.sequence)
            self._last_source_time_s[frame.stream_id] = float(
                frame.source_time_s
            )
            self._last_arrival_time_s[frame.stream_id] = float(
                frame.arrival_time_s
            )
            self._plant_source_time_s = float(frame.source_time_s)
            self._plant_arrival_time_s = float(frame.arrival_time_s)
        processing_ms = (time.perf_counter() - started) * 1000.0
        return FrameResult(
            sequence=frame.sequence,
            trace_id=trace_id,
            accepted=accepted,
            reasons=tuple(reasons),
            state=next_state.value if accepted and next_state else None,
            transport_latency_ms=max(transport_ms, 0.0),
            processing_latency_ms=processing_ms,
            end_to_end_latency_ms=max(transport_ms, 0.0) + processing_ms,
            output_hash=output_hash,
        )


def _values_align(expected: Mapping[str, TelemetryScalar] | None,
                  actual: Mapping[str, TelemetryScalar],
                  specs: Mapping[str, TagSpec]) -> bool:
    if expected is None:
        return True
    for tag, expected_value in expected.items():
        if tag not in actual:
            return False
        actual_value = actual[tag]
        if type(expected_value) is bool or type(actual_value) is bool:
            if actual_value is not expected_value:
                return False
        elif not math.isclose(
            float(actual_value), float(expected_value), rel_tol=0.0,
            abs_tol=specs[tag].alignment_abs_tolerance,
        ):
            return False
    return True


def run_replay(monitor: DigitalTwinMonitor,
               cases: Sequence[FrameExpectation]) -> ReplayReport:
    results: list[FrameResult] = []
    detected = false_accepts = false_rejects = 0
    state_checks = state_correct = 0
    alignment_checks = alignment_correct = 0
    recovery_times: list[float] = []
    last_rejected_arrival: float | None = None

    for case in cases:
        result = monitor.process(case.frame)
        results.append(result)
        if case.expected_accept:
            if not result.accepted:
                false_rejects += 1
                last_rejected_arrival = case.frame.arrival_time_s
            else:
                if last_rejected_arrival is not None:
                    recovery_times.append(
                        (case.frame.arrival_time_s - last_rejected_arrival)
                        * 1000.0
                    )
                    last_rejected_arrival = None
                if case.expected_state is not None:
                    state_checks += 1
                    state_correct += result.state == case.expected_state.value
                alignment_checks += 1
                aligned = _values_align(
                    case.expected_values, monitor.state, monitor.specs
                )
                if case.expected_state is not None:
                    aligned = aligned and result.state == case.expected_state.value
                alignment_correct += aligned
        else:
            if result.accepted:
                false_accepts += 1
            else:
                reason_matched = (
                    case.expected_reason_prefix is None
                    or any(
                        reason.startswith(case.expected_reason_prefix)
                        for reason in result.reasons
                    )
                )
                detected += reason_matched
                last_rejected_arrival = case.frame.arrival_time_s

    expected_valid = sum(case.expected_accept for case in cases)
    injected = len(cases) - expected_valid
    accepted = sum(result.accepted for result in results)
    rejected = len(results) - accepted
    accepted_results = [result for result in results if result.accepted]
    processing = [result.processing_latency_ms for result in accepted_results]
    end_to_end = [result.end_to_end_latency_ms for result in accepted_results]
    traceable = sum(
        bool(result.trace_id and result.output_hash)
        for result in accepted_results
    )
    reason_counts = Counter(
        reason.split(":", 1)[0]
        for result in results for reason in result.reasons
    )
    metrics = ReplayMetrics(
        n_frames=len(cases),
        n_expected_valid=expected_valid,
        n_injected_faults=injected,
        n_accepted=accepted,
        n_rejected=rejected,
        detected_faults=detected,
        false_accepts=false_accepts,
        false_rejects=false_rejects,
        fault_detection_rate=detected / injected if injected else 0.0,
        false_accept_rate=false_accepts / injected if injected else 0.0,
        valid_frame_acceptance_rate=(
            (expected_valid - false_rejects) / expected_valid
            if expected_valid else 0.0
        ),
        state_accuracy=state_correct / state_checks if state_checks else 0.0,
        state_alignment_ratio=(
            alignment_correct / alignment_checks if alignment_checks else 0.0
        ),
        traceability_coverage=(
            traceable / accepted if accepted else 0.0
        ),
        p50_processing_latency_ms=_percentile(processing, 50),
        p95_processing_latency_ms=_percentile(processing, 95),
        p99_processing_latency_ms=_percentile(processing, 99),
        p95_end_to_end_latency_ms=_percentile(end_to_end, 95),
        max_recovery_time_ms=max(recovery_times, default=0.0),
        rejection_reasons=dict(sorted(reason_counts.items())),
    )
    return ReplayReport(metrics, tuple(results))


def default_tag_specs() -> tuple[TagSpec, ...]:
    return (
        TagSpec("TANK_PRESSURE_PA", "Pa", minimum=101325.0,
                maximum=80.0e6, alignment_abs_tolerance=1.0),
        TagSpec("TANK_PRESSURE_REDUNDANT_PA", "Pa", minimum=101325.0,
                maximum=80.0e6, alignment_abs_tolerance=1.0),
        TagSpec("TANK_TEMPERATURE_K", "K", minimum=14.0, maximum=400.0,
                alignment_abs_tolerance=0.01),
        TagSpec("UNLOADING_FLOW_KG_S", "kg/s", minimum=0.0, maximum=5.0,
                alignment_abs_tolerance=1e-6),
        TagSpec("FILLING_FLOW_KG_S", "kg/s", minimum=0.0, maximum=5.0,
                alignment_abs_tolerance=1e-6),
        TagSpec("RELIEF_POSITION_PCT", "%", minimum=0.0, maximum=100.0,
                alignment_abs_tolerance=1e-6),
        TagSpec("ESD_ACTIVE", "boolean", kind="boolean"),
        TagSpec("LEAK_DIAMETER_M", "m", minimum=0.0001, maximum=0.025,
                alignment_abs_tolerance=1e-9),
    )


def pressure_agreement(values: Mapping[str, TelemetryScalar]) -> str | None:
    first = float(values["TANK_PRESSURE_PA"])
    second = float(values["TANK_PRESSURE_REDUNDANT_PA"])
    tolerance = max(100_000.0, 0.005 * max(first, second))
    if abs(first - second) > tolerance:
        return "redundant pressure sensors disagree"
    return None


def make_values(*, pressure_pa: float = 45.0e6,
                temperature_k: float = 288.0,
                unloading_flow_kg_s: float = 0.0,
                filling_flow_kg_s: float = 0.0,
                relief_position_pct: float = 0.0,
                esd_active: bool = False,
                leak_diameter_m: float = 0.006) -> dict[str, TelemetryValue]:
    return {
        "TANK_PRESSURE_PA": TelemetryValue(pressure_pa, "Pa"),
        "TANK_PRESSURE_REDUNDANT_PA": TelemetryValue(
            pressure_pa * 1.001, "Pa"
        ),
        "TANK_TEMPERATURE_K": TelemetryValue(temperature_k, "K"),
        "UNLOADING_FLOW_KG_S": TelemetryValue(
            unloading_flow_kg_s, "kg/s"
        ),
        "FILLING_FLOW_KG_S": TelemetryValue(filling_flow_kg_s, "kg/s"),
        "RELIEF_POSITION_PCT": TelemetryValue(relief_position_pct, "%"),
        "ESD_ACTIVE": TelemetryValue(esd_active, "boolean"),
        "LEAK_DIAMETER_M": TelemetryValue(leak_diameter_m, "m"),
    }


def _frame(sequence: int, source: float, values: Mapping[str, TelemetryValue],
           *, latency_ms: float = 25.0) -> TelemetryFrame:
    return TelemetryFrame(
        sequence=sequence,
        source_time_s=source,
        arrival_time_s=source + latency_ms / 1000.0,
        values=values,
    )


def build_virtual_commissioning_suite() -> tuple[FrameExpectation, ...]:
    """Normal/state-transition cases followed by known injected faults."""
    cases: list[FrameExpectation] = []

    def valid(sequence: int, source: float, state: PlantState, **kwargs):
        values = make_values(**kwargs)
        cases.append(FrameExpectation(
            _frame(sequence, source, values), True, state,
            {tag: sample.value for tag, sample in values.items()}, None,
        ))

    valid(1, 0.0, PlantState.STANDBY)
    valid(2, 1.0, PlantState.FILLING, filling_flow_kg_s=0.4)
    valid(3, 2.0, PlantState.STANDBY)
    valid(4, 3.0, PlantState.UNLOADING, unloading_flow_kg_s=0.5)
    valid(5, 4.0, PlantState.RELIEF, relief_position_pct=100.0)
    valid(6, 5.0, PlantState.ESD, esd_active=True)
    valid(7, 6.0, PlantState.STANDBY)

    missing = make_values()
    del missing["TANK_TEMPERATURE_K"]
    cases.append(FrameExpectation(
        _frame(8, 7.0, missing), False, injected_fault="dropout",
        expected_reason_prefix=RejectReason.MISSING_TAG.value,
    ))

    bad_unit = make_values()
    bad_unit["TANK_PRESSURE_PA"] = TelemetryValue(450.0, "bar")
    cases.append(FrameExpectation(
        _frame(9, 8.0, bad_unit), False, injected_fault="unit_swap",
        expected_reason_prefix=RejectReason.BAD_UNIT.value,
    ))

    cases.append(FrameExpectation(
        _frame(10, 9.0, make_values(), latency_ms=5000.0), False,
        injected_fault="stale_frame",
        expected_reason_prefix=RejectReason.STALE_FRAME.value,
    ))
    cases.append(FrameExpectation(
        _frame(7, 10.0, make_values()), False,
        injected_fault="duplicate_sequence",
        expected_reason_prefix=RejectReason.DUPLICATE_SEQUENCE.value,
    ))
    cases.append(FrameExpectation(
        _frame(0, 11.0, make_values()), False,
        injected_fault="out_of_order_sequence",
        expected_reason_prefix=RejectReason.OUT_OF_ORDER_SEQUENCE.value,
    ))

    bad_quality = make_values()
    bad_quality["TANK_TEMPERATURE_K"] = TelemetryValue(
        288.0, "K", "UNCERTAIN"
    )
    cases.append(FrameExpectation(
        _frame(11, 12.0, bad_quality), False,
        injected_fault="bad_quality",
        expected_reason_prefix=RejectReason.BAD_QUALITY.value,
    ))

    nonfinite = make_values()
    nonfinite["UNLOADING_FLOW_KG_S"] = TelemetryValue(float("nan"), "kg/s")
    cases.append(FrameExpectation(
        _frame(12, 13.0, nonfinite), False,
        injected_fault="nonfinite",
        expected_reason_prefix=RejectReason.NONFINITE.value,
    ))

    biased = make_values()
    biased["TANK_PRESSURE_REDUNDANT_PA"] = TelemetryValue(40.0e6, "Pa")
    cases.append(FrameExpectation(
        _frame(13, 14.0, biased), False,
        injected_fault="redundant_sensor_bias",
        expected_reason_prefix=RejectReason.CROSS_FIELD_INCONSISTENCY.value,
    ))

    conflict = make_values(unloading_flow_kg_s=0.5, filling_flow_kg_s=0.5)
    cases.append(FrameExpectation(
        _frame(14, 15.0, conflict), False,
        injected_fault="impossible_state",
        expected_reason_prefix=RejectReason.CROSS_FIELD_INCONSISTENCY.value,
    ))

    unknown = make_values()
    unknown["UNREGISTERED_TAG"] = TelemetryValue(1.0, "-")
    cases.append(FrameExpectation(
        _frame(15, 16.0, unknown), False,
        injected_fault="unknown_tag",
        expected_reason_prefix=RejectReason.UNKNOWN_TAG.value,
    ))

    reversed_clock = TelemetryFrame(
        sequence=16, source_time_s=18.0, arrival_time_s=17.0,
        values=make_values(),
    )
    cases.append(FrameExpectation(
        reversed_clock, False, injected_fault="reversed_clock",
        expected_reason_prefix=RejectReason.CLOCK_REVERSED.value,
    ))

    recovery = make_values()
    cases.append(FrameExpectation(
        _frame(17, 19.0, recovery), True, PlantState.STANDBY,
        {tag: sample.value for tag, sample in recovery.items()}, None,
    ))
    return tuple(cases)


def replay_hashes(report: ReplayReport) -> tuple[str, ...]:
    return tuple(
        result.output_hash for result in report.results
        if result.accepted and result.output_hash is not None
    )


def report_as_dict(report: ReplayReport) -> dict:
    return {
        "metrics": asdict(report.metrics),
        "results": [asdict(result) for result in report.results],
    }
