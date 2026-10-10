"""Digital-twin entry point for known leak scenarios and normalized sensors."""
from __future__ import annotations
from collections import OrderedDict
import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
import re
import time
from .backend import BackendError, tree_digest
from .consequences import ConsequenceRequest
from .contracts import canonical_digest
from .state_snapshot import EquipmentStateSnapshot, build_state_snapshot_from_normalized


# A process-state snapshot is deliberately smaller than a consequence request.
# The external equipment model owns the accident interpretation (hole, event
# frequency, duration, inventory ledger, and termination).  Rejecting these
# fields here prevents a normal operating snapshot from being promoted to an
# accident packet by an adapter that happens to carry extra metadata.
_FORBIDDEN_PROCESS_STATE_KEYS = frozenset({
    "annual_frequency_per_year",
    "frequency_event",
    "initiation_intensity_per_s",
    "failure_opening_diameter_m",
    "failure_area_m2",
    "hole_diameter_m",
    "leak_diameter_m",
    "resolved_release",
    "resolved_release_set",
    "resolved_liquid_release",
    "provider_release",
    "provider_release_packet",
    "release_termination",
    "termination_provenance",
    "event_id",
    "event_kind",
    "duration_s",
    "steps",
    "cumulative_mass_out_kg",
    "provider_export_schema",
})


def _scan_forbidden_process_state_keys(value, *, path: str = "state"):
    """Raise if a nested state payload contains an accident-owned field."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text.lower() in _FORBIDDEN_PROCESS_STATE_KEYS:
                raise ValueError(
                    f"process state contains accident-owned field: {path}.{key_text}"
                )
            _scan_forbidden_process_state_keys(child, path=f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_forbidden_process_state_keys(child, path=f"{path}[{index}]")


def validate_equipment_process_state(normalized: Mapping) -> dict:
    """Validate and copy a state-only digital-twin snapshot.

    ``normalized`` may contain pressure, temperature, level, flow, phase, and
    control measurements.  It must contain a ``values`` mapping whose rows
    provide finite ``value_si`` values.  It may not contain a release packet,
    leak geometry, duration, frequency, or accident termination field.  This
    function does not infer any missing accident information; the resolver
    must return a provider-owned :class:`ConsequenceRequest` separately.
    """
    if not isinstance(normalized, Mapping):
        raise TypeError("equipment process state must be a mapping")
    _scan_forbidden_process_state_keys(normalized)
    values = normalized.get("values")
    if not isinstance(values, Mapping):
        raise ValueError("equipment process state requires a values mapping")
    for tag, row in values.items():
        if not isinstance(tag, str) or not tag:
            raise ValueError("equipment process state tags must be nonempty strings")
        if not isinstance(row, Mapping):
            raise ValueError(f"equipment process state row is not a mapping: {tag}")
        if "value_si" not in row:
            raise ValueError(f"equipment process state row lacks value_si: {tag}")
        value_si = row["value_si"]
        if isinstance(value_si, bool) or not isinstance(value_si, (int, float)):
            raise ValueError(f"equipment process state value_si is not numeric: {tag}")
        if not math.isfinite(float(value_si)):
            raise ValueError(f"equipment process state value_si is not finite: {tag}")
    return copy.deepcopy(dict(normalized))


def _bind_normalized_state_snapshot(
    request: ConsequenceRequest,
    normalized: Mapping,
    *,
    pressure_tag: str | None = None,
    temperature_tag: str | None = None,
    captured_at_s: float | None = None,
) -> ConsequenceRequest:
    """Bind a valid live state frame to the provider request by digest.

    Older direct resolver calls may contain only ``values`` and therefore do
    not have enough provenance to form a canonical snapshot.  Such calls keep
    their historical behavior.  A realtime frame, however, carries origin,
    capture time and a verified frame digest; that path must preserve the
    state snapshot in the consequence request so the provider release can be
    audited against the exact observed state.
    """
    capture = captured_at_s if captured_at_s is not None else normalized.get("captured_at_s")
    origin = normalized.get("origin")
    frame_digest = normalized.get("frame_digest")
    if capture is None or origin not in {
        "historian_measured", "model_prediction", "reconstructed",
        "figure_digitized", "video_recovered", "synthetic",
    }:
        return request
    if not isinstance(frame_digest, str) or len(frame_digest) != 64:
        # A hand-authored diagnostic mapping is not a verified runtime frame.
        # Do not claim a state binding from an invalid provenance token.
        return request
    raw_snapshot = normalized.get("state_snapshot")
    raw_snapshot_digest = normalized.get("state_snapshot_digest")
    try:
        if raw_snapshot is not None or raw_snapshot_digest is not None:
            if not isinstance(raw_snapshot, Mapping) or not isinstance(raw_snapshot_digest, str):
                raise ValueError("state_snapshot and state_snapshot_digest must be supplied together")
            snapshot = EquipmentStateSnapshot.from_mapping(raw_snapshot)
            if snapshot.digest() != raw_snapshot_digest:
                raise ValueError("state_snapshot_digest does not match the runtime snapshot")
        else:
            snapshot = build_state_snapshot_from_normalized(
                normalized,
                component_id=request.component_id,
                captured_at_s=float(capture),
                pressure_tag=pressure_tag,
                temperature_tag=temperature_tag,
            )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"verified realtime state could not be converted to a canonical snapshot: {error}"
        ) from error
    if snapshot.component_id != request.component_id:
        raise ValueError("runtime state snapshot component does not match provider request")
    digest = snapshot.digest()
    if request.state_snapshot is not None and request.state_snapshot.digest() != digest:
        raise ValueError(
            "provider request state_snapshot does not match the normalized realtime state"
        )
    payload = request.model_dump(mode="json")
    payload.update(
        state_snapshot=snapshot.model_dump(mode="json"),
        state_snapshot_digest=digest,
        provider_state_snapshot_digest=digest,
        provider_state_snapshot_digests=(
            [digest] * len(request.provider_state_snapshot_digests)
            if request.provider_state_snapshot_digests is not None
            else None
        ),
    )
    try:
        return ConsequenceRequest.model_validate_json(
            __import__('json').dumps(payload, allow_nan=False)
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"provider request state snapshot binding failed: {error}") from error


def request_from_telemetry(template, normalized, *, pressure_tag, temperature_tag):
    """Use confirmed SI tank state. This is not inverse leak identification."""
    normalized = validate_equipment_process_state(normalized)
    if template.resolved_release is not None or template.resolved_release_set is not None or template.resolved_liquid_release is not None:
        raise ValueError('resolved provider flow must be updated by the equipment model; cannot overwrite its PH boundary from raw P/T tags')
    if pressure_tag==temperature_tag:raise ValueError('distinct pressure and temperature tags required')
    data=template.model_dump(mode='json')
    for tag,quantity,key in ((pressure_tag,'pressure','pressure_pa'),(temperature_tag,'temperature','temperature_k')):
        value=normalized['values'].get(tag)
        if value is None or value['quantity']!=quantity or value['component_id']!=template.component_id:
            raise ValueError('sensor quantity/component does not match the declared source boundary')
        data['source_input']['tank'][key]=value['value_si']
    return ConsequenceRequest.model_validate_json(__import__('json').dumps(data,allow_nan=False))


def request_from_equipment_resolver(
    template,
    normalized,
    resolver: Callable,
    *,
    pressure_tag: str | None = None,
    temperature_tag: str | None = None,
    captured_at_s: float | None = None,
):
    """Accept one provider-owned release request for a normalized state.

    The resolver is the explicit seam to an equipment digital twin.  It may
    use the normalized pressure/temperature state, but it must return a
    :class:`ConsequenceRequest` that already contains a validated
    ``ResolvedGasRelease``, ``ResolvedGasReleaseSet`` or
    ``ResolvedLiquidRelease``.  PRISM does not estimate a hole, duration,
    frequency, or release profile from the sensor frame.
    """
    if not callable(resolver):
        raise TypeError("release_resolver must be callable")
    normalized = validate_equipment_process_state(normalized)
    request = resolver(template, normalized)
    if not isinstance(request, ConsequenceRequest):
        raise ValueError("release_resolver must return a ConsequenceRequest")
    if request.component_id != template.component_id:
        raise ValueError("provider release component does not match telemetry template")
    owners = (
        request.resolved_release,
        request.resolved_release_set,
        request.resolved_liquid_release,
    )
    if sum(value is not None for value in owners) != 1:
        raise ValueError("release_resolver must return exactly one provider release boundary")
    if request.source_input is not None:
        raise ValueError("provider release request must not mix source_input with a resolved boundary")
    if any(
        value is not None
        for value in (
            request.annual_frequency_per_year,
            request.annual_frequency_provenance,
            request.frequency_event,
            request.initiation_intensity_per_s,
        )
    ):
        raise ValueError("release_resolver must not assign initiating frequency")
    if request.release_termination is None:
        raise ValueError("provider release request requires explicit release termination")
    return _bind_normalized_state_snapshot(
        request,
        normalized,
        pressure_tag=pressure_tag,
        temperature_tag=temperature_tag,
        captured_at_s=captured_at_s,
    )


def _provider_port_state_ledger(boundary) -> dict[str, object]:
    """Expose port-state coverage without copying every thermodynamic value."""
    steps = tuple(getattr(boundary, "steps", ()))
    states = tuple(
        state for state in (getattr(step, "provider_port_state", None) for step in steps)
        if state is not None
    )
    missing_times = [
        float(step.time_s)
        for step in steps
        if getattr(step, "provider_port_state", None) is None
    ]
    phase_counts: dict[str, int] = {}
    for state in states:
        phase = str(state.phase)
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
    return {
        "schema": "prism.provider_port_state.v1" if states else None,
        "interval_count": len(steps),
        "bound_interval_count": len(states),
        "coverage_fraction": (len(states) / len(steps)) if steps else 0.0,
        "all_intervals_bound": bool(steps) and len(states) == len(steps),
        "component_ids": sorted({str(state.component_id) for state in states}),
        "port_ids": sorted({str(state.port_id) for state in states}),
        "phase_counts": phase_counts,
        "state_digests": sorted({str(state.source_digest) for state in states}),
        "missing_time_s": missing_times,
        "interpretation": (
            "provider P/h/phase port state covers every resolved interval"
            if steps and len(states) == len(steps)
            else "port-state evidence is partial or absent; release boundary remains the only accepted consequence input"
        ),
    }


def _provider_port_state_component_ledger(path: Mapping[str, object]) -> dict[str, object]:
    """Summarize port-state coverage across every provider endpoint."""
    raw_boundaries = path.get("boundaries")
    boundaries = (
        tuple(item for item in raw_boundaries if isinstance(item, Mapping))
        if isinstance(raw_boundaries, Sequence) and not isinstance(raw_boundaries, (str, bytes))
        else ()
    )
    summaries = tuple(
        item.get("provider_port_state")
        for item in boundaries
        if isinstance(item.get("provider_port_state"), Mapping)
    )
    interval_count = sum(
        int(summary.get("interval_count", 0))
        for summary in summaries
        if isinstance(summary.get("interval_count"), int)
    )
    bound_interval_count = sum(
        int(summary.get("bound_interval_count", 0))
        for summary in summaries
        if isinstance(summary.get("bound_interval_count"), int)
    )
    all_boundaries_bound = bool(boundaries) and len(summaries) == len(boundaries)
    all_intervals_bound = (
        all_boundaries_bound
        and interval_count > 0
        and bound_interval_count == interval_count
        and all(summary.get("all_intervals_bound") is True for summary in summaries)
    )
    missing_times = [
        float(time_s)
        for summary in summaries
        for time_s in summary.get("missing_time_s", ())
        if isinstance(time_s, (int, float)) and not isinstance(time_s, bool)
    ]
    return {
        "status": (
            "ALL_BOUNDARIES_ALL_INTERVALS_BOUND"
            if all_intervals_bound
            else "PARTIAL_OR_MISSING_PORT_STATE"
        ),
        "boundary_count": len(boundaries),
        "port_state_boundary_count": len(summaries),
        "interval_count": interval_count,
        "bound_interval_count": bound_interval_count,
        "all_boundaries_bound": all_boundaries_bound,
        "all_intervals_bound": all_intervals_bound,
        "missing_time_s": missing_times,
        "frequency_inference_performed": False,
        "physical_validation_claim": False,
    }


def _realtime_release_path_ledger(request: ConsequenceRequest) -> dict[str, object]:
    """Summarize the provider-owned release path attached to one live request.

    The telemetry adapter is allowed to pass a resolved gas, liquid, or two-sided
    release into the consequence chain, but the monitor should expose the closure
    evidence without copying the full time history into every facility snapshot.
    This helper reports duration, termination/isolation basis, and mass inventory
    closure.  It never estimates a missing value from pressure or temperature.
    """
    resolved_release = request.resolved_release
    resolved_set = request.resolved_release_set
    resolved_liquid = request.resolved_liquid_release
    if resolved_release is None and resolved_set is None and resolved_liquid is None:
        return {
            "status": "WITHHELD_PROVIDER_RELEASE_NOT_RESOLVED",
            "provider_release_resolved": False,
            "boundary_count": 0,
            "boundaries": [],
            "termination": None,
            "inventory": None,
            "isolation": None,
            "frequency_inference_performed": False,
            "reason": "telemetry state did not supply a provider-owned accident release boundary",
        }

    if resolved_set is not None:
        boundaries = list(resolved_set.releases)
        available_mass = float(resolved_set.available_mass_kg)
        cumulative_mass = float(resolved_set.cumulative_mass_out_kg)
        inventory_provenance = str(resolved_set.inventory_provenance)
        shared_inventory = True
    else:
        boundary = resolved_release or resolved_liquid
        boundaries = [boundary]
        available_mass = float(boundary.available_mass_kg)
        cumulative_mass = float(boundary.cumulative_mass_out_kg)
        inventory_provenance = str(getattr(boundary, "termination_provenance", ""))
        shared_inventory = False

    termination = request.release_termination
    termination_payload = (
        termination.model_dump(mode="json") if termination is not None else None
    )
    basis = termination.basis if termination is not None else None
    isolation_status = {
        "reviewed_isolation_success": "ISOLATION_SUCCESS_DECLARED",
        "synthetic_diagnostic_horizon": "WITHHELD_SYNTHETIC_HORIZON",
        "inventory_depletion": "INVENTORY_TERMINATION",
        "inventory_over_600s": "HORIZON_BOUNDED_INVENTORY",
        "model_pressure_equalization": "MODEL_NATURAL_TERMINATION",
        "two_sided_rupture": "SHARED_TWO_SIDED_TERMINATION",
        "emergency_relief_discharge": "EMERGENCY_RELIEF_TERMINATION",
    }.get(str(basis), "WITHHELD_MISSING_TERMINATION")
    residual = available_mass - cumulative_mass
    if residual < -1.0e-9:
        inventory_status = "INVALID_NEGATIVE_REMAINING_INVENTORY"
    elif basis == "inventory_depletion":
        inventory_status = (
            "INVENTORY_DEPLETED" if residual <= 1.0e-9 else "INVENTORY_NOT_CLOSED"
        )
    elif basis == "inventory_over_600s":
        inventory_status = "HORIZON_BOUNDED_INVENTORY"
    else:
        inventory_status = "MASS_BALANCE_CLOSED"

    boundary_rows: list[dict[str, object]] = []
    for boundary in boundaries:
        row: dict[str, object] = {
            "component_id": str(boundary.component_id),
            "event_id": str(boundary.event_id),
            "event_kind": str(boundary.event_kind),
            "port_id": str(boundary.port_id),
            "boundary_kind": str(boundary.boundary_kind),
            "input_origin": str(boundary.input_origin),
            "duration_s": float(boundary.duration_s),
            "available_mass_kg": float(boundary.available_mass_kg),
            "cumulative_mass_out_kg": float(boundary.cumulative_mass_out_kg),
            "termination_provenance": str(boundary.termination_provenance),
            "termination_basis": boundary.termination_basis,
            "provider_source_digest": boundary.provider_source_digest,
            "provider_result_digest": boundary.provider_result_digest,
            "provider_mass_balance": (
                boundary.provider_mass_balance.model_dump(mode="json")
                if getattr(boundary, "provider_mass_balance", None) is not None
                else None
            ),
            "failure_opening_diameter_m": (
                float(boundary.failure_opening_diameter_m)
                if boundary.failure_opening_diameter_m is not None
                else None
            ),
            "provider_port_state": _provider_port_state_ledger(boundary),
        }
        if resolved_liquid is not None and boundary is resolved_liquid:
            row["phase_basis"] = str(boundary.phase_basis)
            row["reference_area_m2"] = float(boundary.reference_area_m2)
        boundary_rows.append(row)

    return {
        "status": "AVAILABLE_PROVIDER_RELEASE_PATH",
        "provider_release_resolved": True,
        "boundary_count": len(boundary_rows),
        "boundaries": boundary_rows,
        "duration_s": (
            float(termination.time_s) if termination is not None else None
        ),
        "termination": termination_payload,
        "isolation": {
            "status": isolation_status,
            "basis": basis,
            "provenance": termination.provenance if termination is not None else None,
        },
        "inventory": {
            "status": inventory_status,
            "shared_inventory": shared_inventory,
            "available_mass_kg": available_mass,
            "cumulative_mass_out_kg": cumulative_mass,
            "remaining_mass_kg": max(0.0, residual),
            "mass_residual_kg": residual,
            "provenance": inventory_provenance,
        },
        "source_operator": request.source_operator,
        "source_duration_mode": request.source_duration_mode,
        "frequency_inference_performed": False,
        "reason": (
            "provider-owned release duration, termination basis, and inventory ledger "
            "were carried into the realtime consequence snapshot"
        ),
    }


def _realtime_mode_contract(
    service_metadata: Mapping[str, object],
    *,
    deadline_met: bool | None = None,
    runtime_frame: bool = False,
) -> dict[str, object]:
    """Return an explicit mode ledger for one realtime consequence update.

    The enum is intentionally operational rather than optimistic: an exact
    cache hit is a fast diagnostic lookup, while a changed request is a fresh
    physics evaluation that belongs on a background/async path until its
    measured timing proves otherwise.  A missed deadline is exposed as a
    separate reported mode and never converted to a stale result.
    """
    cache_hit = service_metadata.get("exact_cache_hit") is True
    fresh_physics = service_metadata.get("fresh_physics_this_update") is True
    if cache_hit and fresh_physics:
        raise ValueError("realtime mode contract cannot mark a cache hit as fresh physics")
    if not cache_hit and not fresh_physics:
        raise ValueError("realtime mode contract requires cache hit or fresh physics")
    evaluation_mode = "cached_diagnostic_1hz" if cache_hit else "fresh_physics_background"
    reported_mode = (
        "deadline_missed"
        if deadline_met is False
        else evaluation_mode
    )
    return {
        "schema": "prism.realtime_mode_contract.v1",
        "evaluation_mode": evaluation_mode,
        "reported_mode": reported_mode,
        "runtime_frame": bool(runtime_frame),
        "deadline_met": deadline_met,
        "exact_cache_hit": cache_hit,
        "fresh_physics_this_update": fresh_physics,
        "fresh_physics_1hz_claim": False,
        "stale_fallback_used": False,
        "frequency_learning": False,
        "release_inference": False,
        "interpretation": (
            "exact cache lookup is eligible for a 1 Hz diagnostic polling path; "
            "changed-input fresh physics remains a separately measured background path"
            if cache_hit
            else "fresh SLABx-LH2 physics was executed for this changed input; "
            "do not interpret this result as a fresh-physics 1 Hz guarantee"
        ),
    }


class ConsequenceService:
    """Bounded exact-result cache; changed states invoke fresh physics.

    No interpolation, tolerance matching, or stale fallback is hidden here.
    A cached lookup is explicitly distinguished from a new model execution.
    """
    def __init__(self,pipeline,capacity=16):
        if isinstance(capacity,bool) or not isinstance(capacity,int) or not 1<=capacity<=1000:
            raise ValueError('positive bounded cache capacity required')
        self.pipeline=pipeline;self.capacity=capacity;self._cache=OrderedDict()

    def evaluate(self,request):
        start=time.perf_counter()
        for pin in self.pipeline.backend.config.packages:
            if tree_digest(Path(pin.root))!=pin.sha256:
                raise BackendError(f'source revision mismatch: {pin.name}')
        adapter=tree_digest(Path(__file__).parent)
        key=canonical_digest([request.digest(),self.pipeline.facility.digest(),self.pipeline.backend.config.digest(),adapter])
        hit=key in self._cache
        if hit:
            result=copy.deepcopy(self._cache[key]);self._cache.move_to_end(key)
        else:
            result=self.pipeline.consequences(request)
            if result['adapter_source_digest']!=adapter:raise BackendError('adapter changed before cache insertion')
            self._cache[key]=copy.deepcopy(result)
            while len(self._cache)>self.capacity:self._cache.popitem(last=False)
        result['service']={'exact_cache_hit':hit,'fresh_physics_this_update':not hit,
            'service_elapsed_ms':(time.perf_counter()-start)*1000,'physics_run_elapsed_ms':result['elapsed_ms'],
            'cache_key':key,
            'backend_mode':(
                'persistent_worker'
                if result.get('persistent_worker') is True
                else 'isolated_process'
            ),
            'realtime_fresh_physics_claim':False}
        result['service']['mode_contract'] = _realtime_mode_contract(
            result['service']
        )
        return result

    def _update_from_request(self, request, normalized, *, equipment_release_resolved):
        result=self.evaluate(request)
        result['equipment_release_path'] = _realtime_release_path_ledger(request)
        result['telemetry_boundary']={k:normalized[k] for k in
            ('origin','independent_measurement_claim','data_age_s','frame_digest','mapping_digest')}
        result['telemetry_boundary']['data_age_at_output_s']=normalized['data_age_s']+result['service']['service_elapsed_ms']/1000
        result['telemetry_boundary']['equipment_release_resolved'] = equipment_release_resolved
        result['telemetry_boundary']['state_snapshot_binding_status'] = (
            'BOUND_CANONICAL_RUNTIME_STATE'
            if request.state_snapshot is not None
            else 'NOT_AVAILABLE_OR_LEGACY_INPUT'
        )
        result['telemetry_boundary']['state_snapshot_digest'] = request.state_snapshot_digest
        result['telemetry_boundary']['provider_state_snapshot_digest'] = request.provider_state_snapshot_digest
        result['telemetry_boundary']['interpretation'] = (
            'equipment resolver supplied provider release; no inferred leak size or learned frequency'
            if equipment_release_resolved
            else 'known leak geometry; sensor pressure/temperature update, no inferred leak size or learned frequency'
        )
        return result

    def update_from_equipment_state(
        self,
        template,
        normalized,
        *,
        release_resolver,
        pressure_tag: str | None = None,
        temperature_tag: str | None = None,
        captured_at_s: float | None = None,
    ):
        """Evaluate a state-only input after an explicit provider resolution.

        This is the runtime-frame entry point. The resolver remains the owner of
        accident release geometry, duration, isolation, inventory depletion and
        termination; the service only evaluates the returned request.
        """
        request = request_from_equipment_resolver(
            template,
            normalized,
            release_resolver,
            pressure_tag=pressure_tag,
            temperature_tag=temperature_tag,
            captured_at_s=captured_at_s,
        )
        return self._update_from_request(
            request,
            normalized,
            equipment_release_resolved=True,
        )

    def update_from_telemetry(self,template,normalized,*,pressure_tag,temperature_tag,release_resolver=None):
        if release_resolver is None:
            request = request_from_telemetry(
                template, normalized, pressure_tag=pressure_tag, temperature_tag=temperature_tag
            )
            return self._update_from_request(
                request,
                normalized,
                equipment_release_resolved=False,
            )
        return self.update_from_equipment_state(
            template,
            normalized,
            release_resolver=release_resolver,
            pressure_tag=pressure_tag,
            temperature_tag=temperature_tag,
            captured_at_s=normalized.get("captured_at_s"),
        )


class RealtimeConsequenceMonitor:
    """Bounded synchronous monitor for sensor-conditioned consequence updates.

    The monitor provides an explicit deadline record around
    :class:`ConsequenceService`; it does not create a scheduler, estimate an
    unknown leak, or learn a frequency from telemetry.  A deadline miss is
    returned as data so an application can reject or alarm on that update
    rather than silently presenting an old result as fresh physics.
    """

    def __init__(self, service: ConsequenceService, *, period_s: float = 1.0,
                 deadline_s: float | None = None):
        if not isinstance(service, ConsequenceService):
            raise TypeError("service must be a ConsequenceService")
        if not isinstance(period_s, (int, float)) or isinstance(period_s, bool):
            raise ValueError("period_s must be a finite positive number")
        if not math.isfinite(float(period_s)) or period_s <= 0:
            raise ValueError("period_s must be a finite positive number")
        if deadline_s is None:
            deadline_s = float(period_s)
        if not isinstance(deadline_s, (int, float)) or isinstance(deadline_s, bool):
            raise ValueError("deadline_s must be a finite positive number")
        if not math.isfinite(float(deadline_s)) or deadline_s <= 0:
            raise ValueError("deadline_s must be a finite positive number")
        self.service = service
        self.period_s = float(period_s)
        self.deadline_s = float(deadline_s)
        self._last_source_time_by_stream: dict[str, float] = {}

    def update_from_frame(self, template, normalizer, frame, *, now_s: float,
                          pressure_tag: str, temperature_tag: str,
                          release_resolver=None, ambient_pressure_pa: float | None = None):
        """Normalize one frame, evaluate it, and attach a deadline ledger.

        ``normalizer`` remains the authority for timestamp, unit, quality,
        sensor-location, and pressure-basis checks.  The returned record always
        identifies whether this update used fresh physics or an exact cache
        hit.  No frequency or release geometry is inferred in this method.
        """
        normalized = normalizer.normalize(
            frame, now_s=now_s, ambient_pressure_pa=ambient_pressure_pa
        )
        source_time = float(frame.source_time_s)
        normalized["captured_at_s"] = source_time
        result = self.service.update_from_telemetry(
            template,
            normalized,
            pressure_tag=pressure_tag,
            temperature_tag=temperature_tag,
            release_resolver=release_resolver,
        )
        previous = self._last_source_time_by_stream.get(frame.stream_id)
        source_interval = None if previous is None else source_time - previous
        self._last_source_time_by_stream[frame.stream_id] = source_time
        elapsed_s = result["service"]["service_elapsed_ms"] / 1000.0
        result["realtime"] = {
            "period_s": self.period_s,
            "deadline_s": self.deadline_s,
            "deadline_status": "MET" if elapsed_s <= self.deadline_s else "MISSED",
            "deadline_met": elapsed_s <= self.deadline_s,
            "service_elapsed_s": elapsed_s,
            "source_interval_s": source_interval,
            "fresh_physics_this_update": result["service"]["fresh_physics_this_update"],
            "exact_cache_hit": result["service"]["exact_cache_hit"],
            "frequency_learning": False,
            "release_inference": False,
            "interpretation": (
                "deadline ledger only; a missed deadline is not replaced with a stale result"
            ),
        }
        result["realtime"]["mode_contract"] = _realtime_mode_contract(
            result["service"],
            deadline_met=result["realtime"]["deadline_met"],
        )
        return result

    def update_from_runtime_frame(
        self,
        template,
        runtime_frame: Mapping[str, object],
        *,
        now_s: float,
        release_resolver,
        mapping_digest: str | None = None,
    ):
        """Consume a state-only runtime frame through the provider seam.

        The frame adapter verifies its digest and state-only policy, then this
        monitor evaluates only the provider-owned resolved release. A missing
        resolver or missing provider termination is rejected by the service
        contract; no fallback leak or learned frequency is created.
        """
        from .observed_state_runtime import service_state_from_runtime_frame

        normalized = service_state_from_runtime_frame(
            runtime_frame,
            now_s=now_s,
            mapping_digest=mapping_digest,
        )
        result = self.service.update_from_equipment_state(
            template,
            normalized,
            release_resolver=release_resolver,
            captured_at_s=float(runtime_frame["captured_at_s"]),
        )
        source_time = float(runtime_frame["captured_at_s"])
        stream_id = str(
            runtime_frame.get("source_id")
            or runtime_frame.get("component_id")
            or "runtime-frame"
        )
        previous = self._last_source_time_by_stream.get(stream_id)
        source_interval = None if previous is None else source_time - previous
        self._last_source_time_by_stream[stream_id] = source_time
        elapsed_s = result["service"]["service_elapsed_ms"] / 1000.0
        result["realtime"] = {
            "period_s": self.period_s,
            "deadline_s": self.deadline_s,
            "deadline_status": "MET" if elapsed_s <= self.deadline_s else "MISSED",
            "deadline_met": elapsed_s <= self.deadline_s,
            "service_elapsed_s": elapsed_s,
            "source_interval_s": source_interval,
            "fresh_physics_this_update": result["service"]["fresh_physics_this_update"],
            "exact_cache_hit": result["service"]["exact_cache_hit"],
            "frequency_learning": False,
            "release_inference": False,
            "runtime_frame": True,
            "interpretation": (
                "provider release resolved from a state-only runtime frame; "
                "a missed deadline is not replaced with a stale result"
            ),
        }
        result["realtime"]["mode_contract"] = _realtime_mode_contract(
            result["service"],
            deadline_met=result["realtime"]["deadline_met"],
            runtime_frame=True,
        )
        return result

    def update_from_row(
        self,
        template,
        normalizer,
        row: Mapping[str, object],
        *,
        stream_id: str,
        sequence: int,
        source_time_s: float,
        arrival_time_s: float,
        origin: str,
        bindings: Mapping[str, Mapping[str, object]],
        now_s: float,
        pressure_tag: str,
        temperature_tag: str,
        release_resolver=None,
        ambient_pressure_pa: float | None = None,
    ):
        """Run one explicit tabular row through the realtime monitor.

        This is a convenience boundary for a digital-twin historian or CSV
        adapter.  ``frame_from_row`` still requires explicit tag, unit, and
        quality metadata before the existing normalizer and deadline ledger
        run.  The row is never interpreted as an accident release or a
        frequency observation.
        """
        from .inspection_timeseries import frame_from_row

        frame = frame_from_row(
            row,
            stream_id=stream_id,
            sequence=sequence,
            source_time_s=source_time_s,
            arrival_time_s=arrival_time_s,
            origin=origin,
            bindings=bindings,
        )
        return self.update_from_frame(
            template,
            normalizer,
            frame,
            now_s=now_s,
            pressure_tag=pressure_tag,
            temperature_tag=temperature_tag,
            release_resolver=release_resolver,
            ambient_pressure_pa=ambient_pressure_pa,
        )


@dataclass(frozen=True)
class RealtimeFrequencyBinding:
    """A reviewed literature frequency attached to one live component event.

    This is deliberately separate from the telemetry state and from the
    provider release resolver.  The monitor may use this binding to calculate
    the current-weather annual IR contribution, but it never estimates or
    learns the frequency from a sensor frame.  Full facility annual IR/F-N
    still requires the declared weather, population, accident-family and
    evidence gates outside this monitor.
    """

    event_id: str
    asset_id: str
    initiating_frequency_per_year: float
    annual_condition_probability: float
    release_branch_probability: float
    occupancy_probability: float
    provenance: str
    source_digest: str
    frequency_p05_per_year: float | None = None
    frequency_p95_per_year: float | None = None

    @classmethod
    def from_frequency_event(
        cls,
        event,
        *,
        annual_condition_probability: float,
        release_branch_probability: float,
        occupancy_probability: float,
        provenance: str | None = None,
    ) -> "RealtimeFrequencyBinding":
        """Create a realtime binding directly from the reviewed catalogue.

        ``FrequencyEvent`` is generated by :func:`lh2_tno.frequency.generate_events`
        from the packaged Purple/LH2 literature catalogue.  The three
        conditional weights remain required at this boundary because they are
        scenario assumptions, not properties inferred from a live process
        signal.  This helper prevents callers from copying the catalogue rate
        and source digest by hand while preserving the fail-closed binding
        contract used by the facility monitor.
        """
        from .frequency import FrequencyEvent

        if not isinstance(event, FrequencyEvent):
            raise TypeError("event must be a FrequencyEvent")
        if provenance is None:
            provenance = (
                f"catalogue_event={event.id}; source={event.source}; "
                f"catalogue_digest={event.catalogue_digest}"
            )
        return cls(
            event_id=event.id,
            asset_id=event.asset_id,
            initiating_frequency_per_year=float(event.annual_frequency_per_year),
            annual_condition_probability=annual_condition_probability,
            release_branch_probability=release_branch_probability,
            occupancy_probability=occupancy_probability,
            provenance=provenance,
            source_digest=event.source_sha256,
            frequency_p05_per_year=event.marginal_p05_per_year,
            frequency_p95_per_year=event.marginal_p95_per_year,
        )

    def __post_init__(self):
        for field in ("event_id", "asset_id", "provenance"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a nonempty string")
        frequency = self.initiating_frequency_per_year
        if isinstance(frequency, bool) or not isinstance(frequency, (int, float)):
            raise ValueError("initiating_frequency_per_year must be numeric")
        if not math.isfinite(float(frequency)) or frequency < 0.0:
            raise ValueError("initiating_frequency_per_year must be finite and nonnegative")
        for field in (
            "annual_condition_probability",
            "release_branch_probability",
            "occupancy_probability",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field} must be numeric")
            if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{field} must be finite and within [0, 1]")
        if not isinstance(self.source_digest, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", self.source_digest
        ):
            raise ValueError("source_digest must be a 64-character SHA-256 digest")
        bounds = (self.frequency_p05_per_year, self.frequency_p95_per_year)
        if (bounds[0] is None) != (bounds[1] is None):
            raise ValueError(
                "frequency_p05_per_year and frequency_p95_per_year must be supplied together"
            )
        if bounds[0] is not None:
            for field, value in zip(
                ("frequency_p05_per_year", "frequency_p95_per_year"), bounds
            ):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{field} must be numeric")
                if not math.isfinite(float(value)) or float(value) < 0.0:
                    raise ValueError(
                        f"{field} must be finite and nonnegative"
                    )
            if not (
                float(bounds[0])
                <= float(self.initiating_frequency_per_year)
                <= float(bounds[1])
            ):
                raise ValueError(
                    "frequency bounds must satisfy p05 <= published <= p95"
                )

    @property
    def conditional_weight(self) -> float:
        """Probability weight outside the provider consequence calculation."""
        return (
            float(self.annual_condition_probability)
            * float(self.release_branch_probability)
            * float(self.occupancy_probability)
        )

    def weighted_frequency(self, frequency_per_year: float | None = None) -> float:
        """Return one literature frequency after declared condition weights."""
        value = (
            self.initiating_frequency_per_year
            if frequency_per_year is None
            else frequency_per_year
        )
        return float(value) * self.conditional_weight


@dataclass(frozen=True)
class RealtimePopulationBinding:
    """Explicit receptor population used for a conditional realtime F/N view.

    The population is an input ledger, never a value inferred from telemetry.
    It is intentionally separate from :class:`RealtimeFrequencyBinding`: the
    latter carries annual condition, release-branch, and occupancy weights,
    while this class carries the number of people represented at each receptor
    for the current declared outdoor condition.  The resulting F/N contribution
    remains conditional on the accepted component set and current weather; it
    does not open the complete-facility QRA gate.
    """

    persons_by_receptor: Mapping[str, float]
    provenance: str
    source_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.persons_by_receptor, Mapping) or not self.persons_by_receptor:
            raise ValueError("persons_by_receptor must be a nonempty mapping")
        for receptor_id, persons in self.persons_by_receptor.items():
            if not isinstance(receptor_id, str) or not receptor_id.strip():
                raise ValueError("population receptor ids must be nonempty strings")
            if (
                isinstance(persons, bool)
                or not isinstance(persons, (int, float))
                or not math.isfinite(float(persons))
                or float(persons) < 0.0
            ):
                raise ValueError("population persons must be finite and nonnegative")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("population provenance must be a nonempty string")
        if not isinstance(self.source_digest, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", self.source_digest
        ):
            raise ValueError("population source_digest must be a 64-character SHA-256 digest")


@dataclass(frozen=True)
class FacilityRealtimeBinding:
    """The declared digital-twin boundary for one facility component.

    A binding is intentionally explicit.  The facility monitor does not look
    up a request, sensor tags, or a release model by component name, because
    such lookups could silently connect a normal-state signal to the wrong
    accident boundary.
    """

    component_id: str
    template: ConsequenceRequest
    monitor: RealtimeConsequenceMonitor
    normalizer: object
    pressure_tag: str
    temperature_tag: str
    release_resolver: Callable | None = None
    ambient_pressure_pa: float | None = None
    frequency_binding: RealtimeFrequencyBinding | None = None


_REALTIME_ROW_BINDING_KEYS = frozenset({
    "stream_id",
    "sequence",
    "source_time_s",
    "arrival_time_s",
    "origin",
    "bindings",
})


def _realtime_current_weather_risk(
    result: Mapping[str, object], frequency: RealtimeFrequencyBinding | None
) -> dict[str, object]:
    """Extract current-weather IR from provider consequence harm endpoints.

    The chain worker exposes ``harm_given_observed_release_low_high`` for each
    receptor.  No population or multi-weather information is available at the
    monitor boundary, so this helper intentionally returns IR only and keeps
    F/N and full-facility annual risk closed.
    """
    if frequency is None:
        return {
            "status": "WITHHELD_MISSING_LITERATURE_FREQUENCY",
            "annual_ir_low_high": None,
            "risk_atom": None,
            "reason": "no reviewed literature frequency binding was supplied",
        }
    data = result.get("data")
    if not isinstance(data, Mapping):
        return {
            "status": "WITHHELD_MISSING_CONSEQUENCE_DATA",
            "annual_ir_low_high": None,
            "risk_atom": None,
            "reason": "consequence result has no data object",
        }
    receptors = data.get("receptors")
    if not isinstance(receptors, list) or not receptors:
        return {
            "status": "WITHHELD_MISSING_RECEPTOR_HARM",
            "annual_ir_low_high": None,
            "risk_atom": None,
            "reason": "consequence result has no receptor harm endpoints",
        }
    receptor_harm: dict[str, list[float]] = {}
    for index, receptor in enumerate(receptors):
        if not isinstance(receptor, Mapping):
            return {
                "status": "WITHHELD_INVALID_RECEPTOR_HARM",
                "annual_ir_low_high": None,
                "risk_atom": None,
                "reason": f"receptor row {index} is not an object",
            }
        receptor_id = receptor.get("id")
        harm = receptor.get("harm_given_observed_release_low_high")
        if not isinstance(receptor_id, str) or not receptor_id.strip():
            return {
                "status": "WITHHELD_INVALID_RECEPTOR_HARM",
                "annual_ir_low_high": None,
                "risk_atom": None,
                "reason": f"receptor row {index} has no nonempty id",
            }
        if (
            not isinstance(harm, (list, tuple))
            or len(harm) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
                for value in harm
            )
        ):
            return {
                "status": "WITHHELD_INVALID_RECEPTOR_HARM",
                "annual_ir_low_high": None,
                "risk_atom": None,
                "reason": f"receptor {receptor_id} harm endpoints must be finite values in [0, 1]",
            }
        if receptor_id in receptor_harm:
            return {
                "status": "WITHHELD_DUPLICATE_RECEPTOR",
                "annual_ir_low_high": None,
                "risk_atom": None,
                "reason": f"duplicate receptor id: {receptor_id}",
            }
        receptor_harm[receptor_id] = [float(harm[0]), float(harm[1])]

    def annual_ir_for_frequency(value: float) -> dict[str, list[float]]:
        weighted_frequency = frequency.weighted_frequency(value)
        return {
            receptor_id: [
                weighted_frequency * harm[0],
                weighted_frequency * harm[1],
            ]
            for receptor_id, harm in sorted(receptor_harm.items())
        }

    annual_ir = annual_ir_for_frequency(
        float(frequency.initiating_frequency_per_year)
    )
    frequency_sensitivity = None
    if frequency.frequency_p05_per_year is not None:
        frequency_sensitivity = {
            "p05": annual_ir_for_frequency(float(frequency.frequency_p05_per_year)),
            "published": annual_ir,
            "p95": annual_ir_for_frequency(float(frequency.frequency_p95_per_year)),
            "source": frequency.provenance,
            "source_digest": frequency.source_digest,
            "physics_reexecuted": False,
        }
    return {
        "status": "AVAILABLE_CURRENT_WEATHER_IR",
        "annual_ir_low_high": annual_ir,
        "frequency_sensitivity_current_weather_ir_low_high": frequency_sensitivity,
        "risk_atom": {
            "event_id": frequency.event_id,
            "asset_id": frequency.asset_id,
            "initiating_frequency_per_year": frequency.initiating_frequency_per_year,
            "conditional_weight": frequency.conditional_weight,
            "annual_condition_probability": frequency.annual_condition_probability,
            "release_branch_probability": frequency.release_branch_probability,
            "occupancy_probability": frequency.occupancy_probability,
            "receptor_harm_low_high": receptor_harm,
            "frequency_provenance": frequency.provenance,
            "frequency_source_digest": frequency.source_digest,
            "frequency_is_not_inferred": True,
            "frequency_p05_per_year": frequency.frequency_p05_per_year,
            "frequency_p95_per_year": frequency.frequency_p95_per_year,
            "expected_deaths_low_high": None,
        },
        "reason": "reviewed literature frequency was multiplied by provider consequence harm for the current weather frame",
    }


def _realtime_ignition_accounting(
    result: Mapping[str, object], frequency: RealtimeFrequencyBinding | None
) -> dict[str, object]:
    """Preserve provider ignition branches for one current consequence result.

    The provider consequence output owns the branch probabilities.  This helper
    only validates that the four declared outdoor branches are present and, when
    a reviewed literature frequency is supplied, applies the same explicit
    condition/release/occupancy weight used by the realtime IR helper.  It never
    learns ignition or frequency from telemetry and never fills a missing branch.
    """
    branches = ("direct_fire", "delayed_flash_fire", "delayed_explosion", "no_ignition")
    data = result.get("data")
    reported = data.get("ignition_branch_probabilities") if isinstance(data, Mapping) else None
    if not isinstance(reported, Mapping) or set(reported) != set(branches):
        return {
            "status": "WITHHELD_MISSING_IGNITION_BRANCHES",
            "branch_probabilities": None,
            "weighted_branch_frequency_per_year": None,
            "frequency_inference_performed": False,
            "reason": "provider consequence result did not expose the complete outdoor ignition branch set",
        }
    probabilities: dict[str, float] = {}
    for branch in branches:
        value = reported.get(branch)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            return {
                "status": "WITHHELD_INVALID_IGNITION_BRANCHES",
                "branch_probabilities": None,
                "weighted_branch_frequency_per_year": None,
                "frequency_inference_performed": False,
                "reason": f"ignition branch {branch} is not a finite probability in [0, 1]",
            }
        probabilities[branch] = float(value)
    if not math.isclose(sum(probabilities.values()), 1.0, rel_tol=0.0, abs_tol=1.0e-10):
        return {
            "status": "WITHHELD_INVALID_IGNITION_BRANCHES",
            "branch_probabilities": None,
            "weighted_branch_frequency_per_year": None,
            "frequency_inference_performed": False,
            "reason": "ignition branch probabilities do not close to one",
        }
    weighted_rates = None
    frequency_metadata = None
    if frequency is not None:
        weighted_frequency = frequency.weighted_frequency()
        weighted_rates = {
            branch: weighted_frequency * probabilities[branch] for branch in branches
        }
        frequency_metadata = {
            "event_id": frequency.event_id,
            "source_digest": frequency.source_digest,
            "provenance": frequency.provenance,
            "weighted_frequency_per_year": weighted_frequency,
        }
    return {
        "status": "AVAILABLE_IGNITION_BRANCHES",
        "branch_probabilities": probabilities,
        "weighted_branch_frequency_per_year": weighted_rates,
        "frequency": frequency_metadata,
        "frequency_inference_performed": False,
        "reason": "provider ignition branch probabilities were retained without branch substitution",
    }


def _realtime_component_risk_ranking(
    component_ids: Sequence[str], components: Mapping[str, Mapping[str, object]]
) -> dict[str, object]:
    """Expose a conservative diagnostic priority view for one realtime batch.

    Only components with an explicit literature frequency and valid current-weather
    receptor IR can receive a numeric rank.  Missing, rejected, or malformed
    component results stay visible with ``None`` peaks; they are never converted to
    zero-risk rows.  This view is for operator triage and does not reallocate event
    frequencies or promote the snapshot to a facility annual IR/F-N result.
    """
    rows: list[dict[str, object]] = []
    available_rows: list[dict[str, object]] = []
    sensitivity_scenarios = ("p05", "published", "p95")

    def peak_from_receptor_ir(
        receptor_ir: Mapping[str, object],
    ) -> tuple[list[float] | None, list[str | None] | None]:
        """Return the two endpoint peaks without accepting a partial map."""
        peaks: list[float] = []
        receptors: list[str] = []
        for endpoint in range(2):
            candidates: list[tuple[float, str]] = []
            for receptor_id, values in receptor_ir.items():
                if (
                    not isinstance(values, (list, tuple))
                    or len(values) != 2
                    or isinstance(values[endpoint], bool)
                    or not isinstance(values[endpoint], (int, float))
                    or not math.isfinite(float(values[endpoint]))
                    or float(values[endpoint]) < 0.0
                ):
                    return None, None
                candidates.append((float(values[endpoint]), str(receptor_id)))
            if not candidates:
                return None, None
            peak_value, receptor_id = max(
                candidates, key=lambda row: (row[0], row[1])
            )
            peaks.append(peak_value)
            receptors.append(receptor_id)
        return peaks, receptors

    for component_id in sorted(component_ids):
        entry = components.get(component_id)
        entry_status = entry.get("status") if isinstance(entry, Mapping) else None
        risk = entry.get("risk") if isinstance(entry, Mapping) else None
        risk_status = risk.get("status") if isinstance(risk, Mapping) else None
        peaks: list[float | None] = [None, None]
        peak_receptors: list[str | None] = [None, None]
        sensitivity_peaks: dict[str, list[float] | None] = {
            scenario: None for scenario in sensitivity_scenarios
        }
        sensitivity_receptors: dict[str, list[str | None] | None] = {
            scenario: None for scenario in sensitivity_scenarios
        }
        row_status = "WITHHELD_COMPONENT_RESULT"
        reason = "component has no accepted realtime risk result"
        if entry_status == "ACCEPTED" and isinstance(risk, Mapping):
            if risk_status == "AVAILABLE_CURRENT_WEATHER_IR":
                annual_ir = risk.get("annual_ir_low_high")
                if isinstance(annual_ir, Mapping) and annual_ir:
                    peak_values, peak_ids = peak_from_receptor_ir(annual_ir)
                    valid = peak_values is not None and peak_ids is not None
                    if valid:
                        peaks = list(peak_values)
                        peak_receptors = list(peak_ids)
                    if valid:
                        row_status = "AVAILABLE_CURRENT_WEATHER_IR"
                        reason = "ranked from accepted current-weather receptor IR"
                        sensitivity = risk.get(
                            "frequency_sensitivity_current_weather_ir_low_high"
                        )
                        if isinstance(sensitivity, Mapping):
                            for scenario in sensitivity_scenarios:
                                scenario_ir = sensitivity.get(scenario)
                                if isinstance(scenario_ir, Mapping):
                                    scenario_peaks, scenario_ids = peak_from_receptor_ir(
                                        scenario_ir
                                    )
                                    if scenario_peaks is not None and scenario_ids is not None:
                                        sensitivity_peaks[scenario] = scenario_peaks
                                        sensitivity_receptors[scenario] = scenario_ids
                        available_rows.append({
                            "component_id": component_id,
                            "peak_annual_ir_low_high": peaks,
                            "peak_receptor_id_low_high": peak_receptors,
                            "frequency_sensitivity_peak_annual_ir_low_high": sensitivity_peaks,
                        })
                    else:
                        row_status = "WITHHELD_INVALID_CURRENT_WEATHER_IR"
                        reason = "current-weather IR endpoints are incomplete or invalid"
                else:
                    row_status = "WITHHELD_MISSING_CURRENT_WEATHER_IR"
                    reason = "current-weather IR has no receptor values"
            else:
                row_status = str(risk_status or "WITHHELD_COMPONENT_RISK")
                reason = str(risk.get("reason") or "component risk was withheld")
        elif entry_status is not None:
            row_status = f"WITHHELD_{entry_status}_COMPONENT_RESULT"
            reason = str(entry.get("error") or "component frame was rejected")
        rows.append({
            "rank": None,
            "component_id": component_id,
            "component_status": entry_status,
            "risk_status": row_status,
            "peak_annual_ir_low_high": peaks,
            "peak_receptor_id_low_high": peak_receptors,
            "frequency_sensitivity_peak_annual_ir_low_high": sensitivity_peaks,
            "frequency_sensitivity_peak_receptor_id": sensitivity_receptors,
            "frequency_sensitivity_rank": {
                scenario: None for scenario in sensitivity_scenarios
            },
            "frequency_sensitivity_rank_stable": None,
            "frequency_is_not_reallocated": True,
            "reason": reason,
        })

    available_rows.sort(
        key=lambda row: (
            -float(row["peak_annual_ir_low_high"][1]),
            -float(row["peak_annual_ir_low_high"][0]),
            str(row["component_id"]),
        )
    )
    ranks = {row["component_id"]: index for index, row in enumerate(available_rows, 1)}
    for row in rows:
        if row["component_id"] in ranks:
            row["rank"] = ranks[row["component_id"]]

    # Rank only the components that carry a complete p05/published/p95 map for
    # the same provider consequence.  A missing scenario remains ``None`` and
    # never becomes a zero-risk or worst-case placeholder.
    sensitivity_complete_rows = []
    for row in rows:
        peaks_by_scenario = row.get("frequency_sensitivity_peak_annual_ir_low_high")
        if not isinstance(peaks_by_scenario, Mapping):
            continue
        if all(
            isinstance(peaks_by_scenario.get(scenario), (list, tuple))
            and len(peaks_by_scenario[scenario]) == 2
            for scenario in sensitivity_scenarios
        ):
            sensitivity_complete_rows.append(row)
    for scenario in sensitivity_scenarios:
        scenario_rows = [
            row
            for row in sensitivity_complete_rows
            if isinstance(
                row["frequency_sensitivity_peak_annual_ir_low_high"].get(scenario),
                (list, tuple),
            )
        ]
        scenario_rows.sort(
            key=lambda row: (
                -float(
                    row["frequency_sensitivity_peak_annual_ir_low_high"][scenario][1]
                ),
                -float(
                    row["frequency_sensitivity_peak_annual_ir_low_high"][scenario][0]
                ),
                str(row["component_id"]),
            )
        )
        scenario_ranks = {
            row["component_id"]: index for index, row in enumerate(scenario_rows, 1)
        }
        for row in rows:
            row["frequency_sensitivity_rank"][scenario] = scenario_ranks.get(
                row["component_id"]
            )
    for row in rows:
        rank_map = row["frequency_sensitivity_rank"]
        values = [rank_map[scenario] for scenario in sensitivity_scenarios]
        row["frequency_sensitivity_rank_stable"] = (
            len(sensitivity_complete_rows) > 0
            and all(value is not None for value in values)
            and len(set(values)) == 1
        ) if any(value is not None for value in values) else None
    if not rows:
        status = "NO_COMPONENTS"
    elif len(available_rows) == len(rows):
        status = "AVAILABLE_CURRENT_WEATHER_COMPONENT_RANKING"
    elif available_rows:
        status = "PARTIAL_CURRENT_WEATHER_COMPONENT_RANKING"
    else:
        status = "WITHHELD_CURRENT_WEATHER_COMPONENT_RANKING"
    return {
        "status": status,
        "component_count": len(rows),
        "available_component_count": len(available_rows),
        "withheld_component_count": len(rows) - len(available_rows),
        "ranking_basis": (
            "descending peak receptor current-weather annual IR at the high uncertainty endpoint; "
            "diagnostic triage only"
        ),
        "frequency_sensitivity_scenarios": list(sensitivity_scenarios),
        "frequency_sensitivity_complete_component_count": len(sensitivity_complete_rows),
        "frequency_sensitivity_status": (
            "AVAILABLE_CURRENT_WEATHER_FREQUENCY_RANKING"
            if sensitivity_complete_rows and len(sensitivity_complete_rows) == len(available_rows)
            else "PARTIAL_CURRENT_WEATHER_FREQUENCY_RANKING"
            if sensitivity_complete_rows
            else "WITHHELD_CURRENT_WEATHER_FREQUENCY_RANKING"
        ),
        "frequency_reallocation_performed": False,
        "facility_ir_fn_promotion": False,
        "stale_or_zero_fallback_used": False,
        "rows": sorted(
            rows,
            key=lambda row: (
                row["rank"] is None,
                row["rank"] if row["rank"] is not None else len(rows) + 1,
                str(row["component_id"]),
            ),
        ),
    }


def _strict_realtime_release_boundary_gate(
    *,
    batch_status: str,
    component_ids: Sequence[str],
    release_path_component_rows: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Classify whether one realtime batch has a closed release boundary.

    The gate is intentionally narrower than facility-QRA qualification.  It
    checks only the evidence available in the live provider path: complete
    component coverage, a non-synthetic termination basis, an explicit
    isolation/depletion outcome, and a closed non-negative mass residual.  It
    never treats a missing path as zero risk and never evaluates provider
    qualification or independent physical validation.
    """

    blockers: list[str] = []
    component_set = set(component_ids)
    row_set = set(release_path_component_rows)
    if batch_status != "ACCEPTED":
        blockers.append("realtime component batch is not accepted")
    missing = sorted(component_set - row_set)
    if missing:
        blockers.append(
            "release path missing for component(s): " + ", ".join(missing)
        )
    extra = sorted(row_set - component_set)
    if extra:
        blockers.append(
            "release path contains undeclared component(s): " + ", ".join(extra)
        )

    allowed_termination = {"reviewed_isolation_success", "inventory_depletion"}
    allowed_isolation = {"ISOLATION_SUCCESS_DECLARED", "INVENTORY_TERMINATION"}
    allowed_inventory = {"MASS_BALANCE_CLOSED", "INVENTORY_DEPLETED"}
    for component_id in sorted(component_set):
        row = release_path_component_rows.get(component_id)
        if not isinstance(row, Mapping):
            continue
        if row.get("status") != "AVAILABLE_PROVIDER_RELEASE_PATH":
            blockers.append(f"{component_id}: provider release path is not available")
        basis = row.get("termination_basis")
        if basis not in allowed_termination:
            if basis == "synthetic_diagnostic_horizon":
                blockers.append(f"{component_id}: synthetic diagnostic horizon remains")
            elif basis is None:
                blockers.append(f"{component_id}: termination basis is missing")
            else:
                blockers.append(f"{component_id}: termination basis={basis} is not closed")
        isolation = row.get("isolation_status")
        if isolation not in allowed_isolation:
            blockers.append(f"{component_id}: isolation outcome is not reviewed/closed")
        inventory = row.get("inventory_status")
        if inventory not in allowed_inventory:
            blockers.append(f"{component_id}: inventory status={inventory} is not closed")
        residual = row.get("mass_residual_kg")
        if (
            isinstance(residual, bool)
            or not isinstance(residual, (int, float))
            or not math.isfinite(float(residual))
            or float(residual) < -1.0e-8
        ):
            blockers.append(f"{component_id}: mass residual is missing or negative")
        elif basis == "inventory_depletion" and abs(float(residual)) > 1.0e-8:
            blockers.append(
                f"{component_id}: inventory-depletion residual exceeds 1e-8 kg"
            )

    return {
        "strict_release_boundary_ready": not blockers,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "component_count": len(component_ids),
        "component_path_count": len(release_path_component_rows),
        "provider_qualification_evaluated": False,
        "independent_physical_validation_claim": False,
        "facility_ir_fn_promotion": False,
        "frequency_inference_performed": False,
        "policy": (
            "release-boundary completeness only; passing this gate does not qualify "
            "the provider packet, validate SLABx/physics, or promote facility IR/F-N"
        ),
    }


def _realtime_conditional_expected_death_fn(
    risk_rows: list[Mapping[str, object]],
    population: RealtimePopulationBinding | None,
) -> dict[str, object]:
    """Calculate a conditional current-weather expected-death contribution.

    This is deliberately narrower than a facility F/N curve.  It requires one
    explicit population ledger and one valid literature frequency binding for
    every accepted component.  Missing receptors, malformed risk atoms, or an
    incomplete batch return a withheld result rather than a zero contribution.
    """

    if population is None:
        return {
            "status": "WITHHELD_MISSING_POPULATION_LEDGER",
            "expected_death_fn_low_high": None,
            "frequency_sensitivity_expected_death_fn_low_high": None,
            "reason": "explicit receptor population ledger was not supplied",
        }
    receptor_ids = set(population.persons_by_receptor)
    scenario_totals: dict[str, list[float]] = {}
    bounded_row_count = 0
    for row_index, row in enumerate(risk_rows):
        atom = row.get("risk_atom")
        if not isinstance(atom, Mapping):
            return {
                "status": "WITHHELD_MISSING_FREQUENCY_ATOM",
                "expected_death_fn_low_high": None,
                "frequency_sensitivity_expected_death_fn_low_high": None,
                "reason": f"risk row {row_index} has no frequency risk atom",
            }
        harms = atom.get("receptor_harm_low_high")
        if not isinstance(harms, Mapping):
            return {
                "status": "WITHHELD_MISSING_RECEPTOR_HARM",
                "expected_death_fn_low_high": None,
                "frequency_sensitivity_expected_death_fn_low_high": None,
                "reason": f"risk row {row_index} has no receptor harm ledger",
            }
        harm_ids = set(harms)
        if harm_ids != receptor_ids:
            return {
                "status": "WITHHELD_POPULATION_RECEPTOR_MISMATCH",
                "expected_death_fn_low_high": None,
                "frequency_sensitivity_expected_death_fn_low_high": None,
                "reason": (
                    f"risk row {row_index} receptors do not exactly match population ledger: "
                    f"population={sorted(receptor_ids)}, harm={sorted(harm_ids)}"
                ),
            }
        frequency = atom.get("initiating_frequency_per_year")
        conditional_weight = atom.get("conditional_weight")
        if (
            isinstance(frequency, bool)
            or not isinstance(frequency, (int, float))
            or not math.isfinite(float(frequency))
            or float(frequency) < 0.0
            or isinstance(conditional_weight, bool)
            or not isinstance(conditional_weight, (int, float))
            or not math.isfinite(float(conditional_weight))
            or not 0.0 <= float(conditional_weight) <= 1.0
        ):
            return {
                "status": "WITHHELD_INVALID_FREQUENCY_ATOM",
                "expected_death_fn_low_high": None,
                "frequency_sensitivity_expected_death_fn_low_high": None,
                "reason": f"risk row {row_index} has an invalid frequency atom",
            }

        def add_scenario(scenario: str, scenario_frequency: float) -> None:
            weighted = float(scenario_frequency) * float(conditional_weight)
            scenario_sum = scenario_totals.setdefault(scenario, [0.0, 0.0])
            for receptor_id in sorted(receptor_ids):
                endpoints = harms.get(receptor_id)
                persons = float(population.persons_by_receptor[receptor_id])
                if (
                    not isinstance(endpoints, (list, tuple))
                    or len(endpoints) != 2
                    or any(
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(float(value))
                        or not 0.0 <= float(value) <= 1.0
                        for value in endpoints
                    )
                ):
                    raise ValueError(f"invalid receptor harm for {receptor_id}")
                scenario_sum[0] += weighted * persons * float(endpoints[0])
                scenario_sum[1] += weighted * persons * float(endpoints[1])

        try:
            add_scenario("published", float(frequency))
        except (TypeError, ValueError) as error:
            return {
                "status": "WITHHELD_INVALID_RECEPTOR_HARM",
                "expected_death_fn_low_high": None,
                "frequency_sensitivity_expected_death_fn_low_high": None,
                "reason": str(error),
            }
        p05 = atom.get("frequency_p05_per_year")
        p95 = atom.get("frequency_p95_per_year")
        if p05 is not None or p95 is not None:
            if (
                isinstance(p05, bool)
                or not isinstance(p05, (int, float))
                or not math.isfinite(float(p05))
                or float(p05) < 0.0
                or isinstance(p95, bool)
                or not isinstance(p95, (int, float))
                or not math.isfinite(float(p95))
                or float(p95) < 0.0
            ):
                return {
                    "status": "WITHHELD_INVALID_FREQUENCY_BOUNDS",
                    "expected_death_fn_low_high": None,
                    "frequency_sensitivity_expected_death_fn_low_high": None,
                    "reason": f"risk row {row_index} has invalid frequency bounds",
                }
            try:
                add_scenario("p05", float(p05))
                add_scenario("p95", float(p95))
                bounded_row_count += 1
            except (TypeError, ValueError) as error:
                return {
                    "status": "WITHHELD_INVALID_RECEPTOR_HARM",
                    "expected_death_fn_low_high": None,
                    "frequency_sensitivity_expected_death_fn_low_high": None,
                    "reason": str(error),
                }

    published = scenario_totals.get("published")
    if published is None:
        return {
            "status": "WITHHELD_MISSING_PUBLISHED_FREQUENCY",
            "expected_death_fn_low_high": None,
            "frequency_sensitivity_expected_death_fn_low_high": None,
            "reason": "no published frequency contribution was accumulated",
        }
    sensitivity = None
    if (
        bounded_row_count == len(risk_rows)
        and bool(risk_rows)
        and "p05" in scenario_totals
        and "p95" in scenario_totals
    ):
        sensitivity = {
            "p05": scenario_totals["p05"],
            "published": published,
            "p95": scenario_totals["p95"],
            "physics_reexecuted": False,
        }
    return {
        "status": "AVAILABLE_CONDITIONAL_CURRENT_WEATHER_EXPECTED_DEATH_FN",
        "expected_death_fn_low_high": published,
        "frequency_sensitivity_expected_death_fn_low_high": sensitivity,
        "population_provenance": population.provenance,
        "population_source_digest": population.source_digest,
        "population_receptor_count": len(receptor_ids),
        "frequency_learning": False,
        "reason": (
            "explicit receptor population was multiplied by the reviewed literature "
            "frequency and current-weather consequence harm; full-facility F/N remains withheld"
        ),
    }


class FacilityRealtimeConsequenceMonitor:
    """Batch coordinator for independent component monitors.

    This class combines *provenance and deadline ledgers* and can optionally
    calculate a current-weather IR contribution from an explicit reviewed
    literature frequency binding.  When an explicit receptor population ledger
    is supplied, it also reports a conditional current-weather expected-death
    F/N contribution.  It never infers a frequency from telemetry and never
    promotes either conditional view to facility annual IR/F-N.
    Each component still owns its normalizer, consequence service, provider
    release resolver, and cache.  Missing/unknown/duplicate frames and any
    component exception make the batch ``REJECTED``; accepted component
    results remain attached for diagnosis, but no stale result or zero-risk
    placeholder is manufactured for the failed component.
    """

    def __init__(
        self,
        bindings: Mapping[str, FacilityRealtimeBinding],
        *,
        facility_id: str = "facility",
        max_components: int = 128,
        population_binding: RealtimePopulationBinding | None = None,
        max_source_time_span_s: float | None = None,
    ):
        if not isinstance(bindings, Mapping) or not bindings:
            raise ValueError("nonempty component binding mapping required")
        if not isinstance(facility_id, str) or not facility_id:
            raise ValueError("facility_id must be a nonempty string")
        if isinstance(max_components, bool) or not isinstance(max_components, int):
            raise ValueError("max_components must be a positive integer")
        if not 1 <= max_components <= 10000:
            raise ValueError("max_components must be between 1 and 10000")
        if len(bindings) > max_components:
            raise ValueError("component binding count exceeds max_components")
        if max_source_time_span_s is not None:
            if (
                isinstance(max_source_time_span_s, bool)
                or not isinstance(max_source_time_span_s, (int, float))
                or not math.isfinite(float(max_source_time_span_s))
                or float(max_source_time_span_s) <= 0.0
            ):
                raise ValueError(
                    "max_source_time_span_s must be finite and positive when supplied"
                )
        if population_binding is not None and not isinstance(
            population_binding, RealtimePopulationBinding
        ):
            raise TypeError("population_binding must be a RealtimePopulationBinding")

        normalized: dict[str, FacilityRealtimeBinding] = {}
        frequency_event_owners: dict[str, str] = {}
        for key, binding in bindings.items():
            if not isinstance(key, str) or not key:
                raise ValueError("component binding keys must be nonempty strings")
            if not isinstance(binding, FacilityRealtimeBinding):
                raise TypeError("bindings must contain FacilityRealtimeBinding values")
            if binding.component_id != key:
                raise ValueError("binding key must equal binding.component_id")
            if not isinstance(binding.template, ConsequenceRequest):
                raise TypeError("binding.template must be a ConsequenceRequest")
            if binding.template.component_id != key:
                raise ValueError("template component_id does not match binding")
            if not isinstance(binding.monitor, RealtimeConsequenceMonitor):
                raise TypeError("binding.monitor must be a RealtimeConsequenceMonitor")
            if not callable(getattr(binding.normalizer, "normalize", None)):
                raise TypeError("binding.normalizer must provide normalize()")
            for tag_name, tag in (("pressure_tag", binding.pressure_tag),
                                  ("temperature_tag", binding.temperature_tag)):
                if not isinstance(tag, str) or not tag:
                    raise ValueError(f"{tag_name} must be a nonempty string")
            if binding.pressure_tag == binding.temperature_tag:
                raise ValueError("pressure and temperature tags must be distinct")
            if binding.release_resolver is not None and not callable(binding.release_resolver):
                raise TypeError("release_resolver must be callable")
            if binding.frequency_binding is not None and not isinstance(
                binding.frequency_binding, RealtimeFrequencyBinding
            ):
                raise TypeError(
                    "frequency_binding must be a RealtimeFrequencyBinding"
                )
            if binding.frequency_binding is not None:
                event_id = binding.frequency_binding.event_id
                previous_owner = frequency_event_owners.get(event_id)
                if previous_owner is not None and previous_owner != key:
                    raise ValueError(
                        "one literature event cannot be bound to multiple realtime components: "
                        f"{event_id} ({previous_owner}, {key})"
                    )
                frequency_event_owners[event_id] = key
            if binding.ambient_pressure_pa is not None:
                if (isinstance(binding.ambient_pressure_pa, bool)
                        or not isinstance(binding.ambient_pressure_pa, (int, float))
                        or not math.isfinite(float(binding.ambient_pressure_pa))
                        or binding.ambient_pressure_pa <= 0):
                    raise ValueError("ambient_pressure_pa must be finite and positive")
            normalized[key] = binding
        self.facility_id = facility_id
        self.bindings = normalized
        self.population_binding = population_binding
        self.max_source_time_span_s = (
            None
            if max_source_time_span_s is None
            else float(max_source_time_span_s)
        )

    def update_from_frames(self, frames: Mapping[str, object], *, now_s: float) -> dict:
        """Process one coherent frame per declared component.

        ``frames`` is a component-id keyed mapping.  The method deliberately
        does not wait for missing components or reuse their previous result.
        This makes the returned facility snapshot safe to reject in a control
        room when one stream is late or malformed.
        """
        if not isinstance(frames, Mapping):
            raise TypeError("frames must be a component-id mapping")
        if (isinstance(now_s, bool) or not isinstance(now_s, (int, float))
                or not math.isfinite(float(now_s)) or now_s < 0):
            raise ValueError("now_s must be finite and nonnegative")

        component_ids = tuple(sorted(self.bindings))
        unknown_ids = tuple(sorted(str(key) for key in set(frames) - set(self.bindings)))
        missing_ids = tuple(component_id for component_id in component_ids if component_id not in frames)
        stream_to_components: dict[str, list[str]] = {}
        frame_errors: dict[str, dict] = {}
        for component_id in component_ids:
            frame = frames.get(component_id)
            if frame is None:
                continue
            stream_id = getattr(frame, "stream_id", None)
            if not isinstance(stream_id, str) or not stream_id:
                frame_errors[component_id] = {
                    "status": "REJECTED",
                    "error_type": "FrameContractError",
                    "error": "frame must expose a nonempty stream_id",
                }
                continue
            stream_to_components.setdefault(stream_id, []).append(component_id)
        duplicate_streams = {
            stream_id: tuple(component_ids_for_stream)
            for stream_id, component_ids_for_stream in stream_to_components.items()
            if len(component_ids_for_stream) > 1
        }

        components: dict[str, dict] = {}
        for component_id in component_ids:
            if component_id in missing_ids:
                components[component_id] = {
                    "status": "REJECTED",
                    "error_type": "MissingFrame",
                    "error": "facility snapshot requires one frame for every declared component",
                }
            elif component_id in frame_errors:
                components[component_id] = frame_errors[component_id]
            else:
                frame = frames[component_id]
                stream_id = frame.stream_id
                if stream_id in duplicate_streams:
                    components[component_id] = {
                        "status": "REJECTED",
                        "error_type": "DuplicateFrameStream",
                        "error": f"stream_id is shared by components: {', '.join(duplicate_streams[stream_id])}",
                        "stream_id": stream_id,
                    }

        for component_id in component_ids:
            if component_id in components:
                continue
            binding = self.bindings[component_id]
            frame = frames[component_id]
            try:
                result = binding.monitor.update_from_frame(
                    binding.template,
                    binding.normalizer,
                    frame,
                    now_s=float(now_s),
                    pressure_tag=binding.pressure_tag,
                    temperature_tag=binding.temperature_tag,
                    release_resolver=binding.release_resolver,
                    ambient_pressure_pa=binding.ambient_pressure_pa,
                )
                components[component_id] = {
                    "status": "ACCEPTED",
                    "component_id": component_id,
                    "stream_id": frame.stream_id,
                    "source_time_s": float(frame.source_time_s),
                    "arrival_time_s": float(frame.arrival_time_s),
                    "frame_digest": result.get("telemetry_boundary", {}).get("frame_digest"),
                    "mapping_digest": result.get("telemetry_boundary", {}).get("mapping_digest"),
                    "equipment_release_path": result.get(
                        "equipment_release_path",
                        {
                            "status": "WITHHELD_PROVIDER_RELEASE_PATH_NOT_RECORDED",
                            "provider_release_resolved": False,
                        },
                    ),
                    "ignition": _realtime_ignition_accounting(
                        result, binding.frequency_binding
                    ),
                    "risk": _realtime_current_weather_risk(
                        result, binding.frequency_binding
                    ),
                    "result": result,
                }
            except Exception as exc:  # preserve an explicit rejection in the ledger
                components[component_id] = {
                    "status": "REJECTED",
                    "component_id": component_id,
                    "stream_id": getattr(frame, "stream_id", None),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }

        return self._aggregate_component_results(
            components,
            unknown_ids=unknown_ids,
            missing_ids=missing_ids,
            duplicate_streams=duplicate_streams,
        )

    def update_from_runtime_frames(
        self,
        frames: Mapping[str, Mapping[str, object]],
        *,
        now_s: float,
        mapping_digest: str | None = None,
    ) -> dict:
        """Evaluate one state-only runtime frame for every facility component.

        Runtime frames carry measured equipment state and a source clock.  They
        do not carry an arrival timestamp, leak geometry, accident frequency,
        ignition probability, or inventory termination.  Each declared binding
        must therefore provide an explicit provider release resolver; the
        resulting component records then use the same facility aggregation and
        fail-closed gates as historian telemetry.
        """
        if not isinstance(frames, Mapping):
            raise TypeError("frames must be a component-id mapping")
        if (
            isinstance(now_s, bool)
            or not isinstance(now_s, (int, float))
            or not math.isfinite(float(now_s))
            or now_s < 0
        ):
            raise ValueError("now_s must be finite and nonnegative")

        component_ids = tuple(sorted(self.bindings))
        unknown_ids = tuple(sorted(str(key) for key in set(frames) - set(self.bindings)))
        missing_ids = tuple(
            component_id for component_id in component_ids if component_id not in frames
        )
        stream_to_components: dict[str, list[str]] = {}
        frame_errors: dict[str, dict[str, object]] = {}
        for component_id in component_ids:
            frame = frames.get(component_id)
            if frame is None:
                continue
            if not isinstance(frame, Mapping):
                frame_errors[component_id] = {
                    "status": "REJECTED",
                    "error_type": "RuntimeFrameContractError",
                    "error": "runtime frame must be a mapping",
                }
                continue
            frame_component_id = frame.get("component_id")
            if frame_component_id != component_id:
                frame_errors[component_id] = {
                    "status": "REJECTED",
                    "error_type": "RuntimeFrameContractError",
                    "error": "runtime frame component_id does not match binding key",
                }
                continue
            source_id = frame.get("source_id")
            if not isinstance(source_id, str) or not source_id.strip():
                frame_errors[component_id] = {
                    "status": "REJECTED",
                    "error_type": "RuntimeFrameContractError",
                    "error": "runtime frame must expose a nonempty source_id",
                }
                continue
            stream_to_components.setdefault(source_id, []).append(component_id)
        duplicate_streams = {
            stream_id: tuple(component_ids_for_stream)
            for stream_id, component_ids_for_stream in stream_to_components.items()
            if len(component_ids_for_stream) > 1
        }

        components: dict[str, dict[str, object]] = {}
        for component_id in component_ids:
            if component_id in missing_ids:
                components[component_id] = {
                    "status": "REJECTED",
                    "error_type": "MissingRuntimeFrame",
                    "error": "facility runtime snapshot requires one frame for every declared component",
                }
            elif component_id in frame_errors:
                components[component_id] = frame_errors[component_id]
            else:
                frame = frames[component_id]
                source_id = str(frame["source_id"])
                if source_id in duplicate_streams:
                    components[component_id] = {
                        "status": "REJECTED",
                        "error_type": "DuplicateRuntimeFrameSource",
                        "error": (
                            "source_id is shared by components: "
                            + ", ".join(duplicate_streams[source_id])
                        ),
                        "stream_id": source_id,
                    }

        for component_id in component_ids:
            if component_id in components:
                continue
            binding = self.bindings[component_id]
            frame = frames[component_id]
            try:
                result = binding.monitor.update_from_runtime_frame(
                    binding.template,
                    frame,
                    now_s=float(now_s),
                    release_resolver=binding.release_resolver,
                    mapping_digest=mapping_digest,
                )
                components[component_id] = {
                    "status": "ACCEPTED",
                    "component_id": component_id,
                    "stream_id": str(frame["source_id"]),
                    "source_time_s": float(frame["captured_at_s"]),
                    # State-only frames intentionally have no network arrival
                    # timestamp; leaving this null prevents false latency claims.
                    "arrival_time_s": None,
                    "frame_digest": result.get("telemetry_boundary", {}).get("frame_digest"),
                    "mapping_digest": result.get("telemetry_boundary", {}).get("mapping_digest"),
                    "runtime_frame": True,
                    "equipment_release_path": result.get(
                        "equipment_release_path",
                        {
                            "status": "WITHHELD_PROVIDER_RELEASE_PATH_NOT_RECORDED",
                            "provider_release_resolved": False,
                        },
                    ),
                    "ignition": _realtime_ignition_accounting(
                        result, binding.frequency_binding
                    ),
                    "risk": _realtime_current_weather_risk(
                        result, binding.frequency_binding
                    ),
                    "result": result,
                }
            except Exception as exc:  # preserve an explicit rejection in the ledger
                components[component_id] = {
                    "status": "REJECTED",
                    "component_id": component_id,
                    "stream_id": frame.get("source_id"),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }

        snapshot = self._aggregate_component_results(
            components,
            unknown_ids=unknown_ids,
            missing_ids=missing_ids,
            duplicate_streams=duplicate_streams,
        )
        snapshot["runtime_frame_batch"] = {
            "status": "STATE_ONLY_RUNTIME_BATCH",
            "component_count": len(component_ids),
            "accepted_component_count": sum(
                entry.get("status") == "ACCEPTED" for entry in components.values()
            ),
            "arrival_time_available": False,
            "mapping_digest_argument_supplied": mapping_digest is not None,
            "release_inference": False,
            "frequency_learning": False,
            "facility_annual_risk_promotion": False,
        }
        snapshot["aggregate"]["runtime_frame_batch"] = True
        snapshot["aggregate"]["runtime_arrival_latency_available"] = False
        return snapshot

    def build_annual_campaign_result(
        self,
        snapshot: Mapping[str, object],
        *,
        annual_conditions: Sequence[Mapping[str, object]],
        scenario_bindings: Sequence[Mapping[str, object]],
        expected_component_ids: Sequence[str] = (),
    ) -> dict[str, object]:
        """Join an accepted realtime snapshot to explicit annual scenarios.

        The monitor owns the component bindings, while the campaign adapter
        owns annual weather, population, release-branch, ignition, and
        reviewed non-current-weather consequence evidence.  This convenience
        method keeps that handoff on the same monitor instance and rejects a
        snapshot produced for another facility.  The delegated result remains
        conditional/operator-limited; it never promotes a realtime snapshot
        to a qualified facility QRA or learns frequency from telemetry.
        """
        if not isinstance(snapshot, Mapping):
            raise TypeError("snapshot must be a mapping")
        if snapshot.get("facility_id") != self.facility_id:
            raise ValueError(
                "snapshot facility_id does not match the realtime monitor: "
                f"{snapshot.get('facility_id')!r} != {self.facility_id!r}"
            )
        from .realtime_campaign import build_realtime_facility_campaign_result

        expected = tuple(expected_component_ids) or tuple(sorted(self.bindings))
        return build_realtime_facility_campaign_result(
            snapshot,
            annual_conditions=annual_conditions,
            scenario_bindings=scenario_bindings,
            expected_component_ids=expected,
        )

    def _aggregate_component_results(
        self,
        components: Mapping[str, Mapping[str, object]],
        *,
        unknown_ids: tuple[str, ...] = (),
        missing_ids: tuple[str, ...] = (),
        duplicate_streams: Mapping[str, tuple[str, ...]] | None = None,
    ) -> dict:
        """Aggregate already-evaluated component records into one snapshot.

        Both historian ``Frame`` inputs and state-only runtime frames use this
        common aggregation path.  Keeping the aggregation separate prevents a
        runtime adapter from bypassing the existing facility gates.
        """
        component_ids = tuple(sorted(self.bindings))
        duplicate_streams = duplicate_streams or {}
        accepted = [entry for entry in components.values() if entry["status"] == "ACCEPTED"]
        rejected = [entry for entry in components.values() if entry["status"] != "ACCEPTED"]
        batch_status = "ACCEPTED" if not rejected and not unknown_ids else "REJECTED"
        accepted_time_rows = [
            entry
            for entry in accepted
            if isinstance(entry.get("source_time_s"), (int, float))
            and not isinstance(entry.get("source_time_s"), bool)
            and isinstance(entry.get("arrival_time_s"), (int, float))
            and not isinstance(entry.get("arrival_time_s"), bool)
        ]
        if not accepted_time_rows:
            facility_time_window = {
                "status": "WITHHELD_NO_ACCEPTED_COMPONENT_TIMES",
                "accepted_component_count": 0,
                "source_time_min_s": None,
                "source_time_max_s": None,
                "source_time_span_s": None,
                "arrival_time_min_s": None,
                "arrival_time_max_s": None,
                "arrival_time_span_s": None,
                "configured_max_source_time_span_s": self.max_source_time_span_s,
                "within_configured_source_time_window": None,
                "coherence_asserted": False,
                "coherence_policy": (
                    "component timestamps are reported only; PRISM does not infer, resample, "
                    "or synchronize missing times"
                ),
            }
        else:
            source_times = [float(entry["source_time_s"]) for entry in accepted_time_rows]
            arrival_times = [float(entry["arrival_time_s"]) for entry in accepted_time_rows]
            facility_time_window = {
                "status": (
                    "MEASURED_COMPLETE_COMPONENT_WINDOW"
                    if batch_status == "ACCEPTED" and len(accepted_time_rows) == len(component_ids)
                    else "MEASURED_PARTIAL_COMPONENT_WINDOW"
                ),
                "accepted_component_count": len(accepted_time_rows),
                "source_time_min_s": min(source_times),
                "source_time_max_s": max(source_times),
                "source_time_span_s": max(source_times) - min(source_times),
                "arrival_time_min_s": min(arrival_times),
                "arrival_time_max_s": max(arrival_times),
                "arrival_time_span_s": max(arrival_times) - min(arrival_times),
                "configured_max_source_time_span_s": self.max_source_time_span_s,
                "within_configured_source_time_window": (
                    None
                    if self.max_source_time_span_s is None
                    else max(source_times) - min(source_times)
                    <= self.max_source_time_span_s
                ),
                "coherence_asserted": False,
                "coherence_policy": (
                    "component timestamps are reported only; PRISM does not infer, resample, "
                    "or synchronize missing times"
                ),
            }
        time_window_rejection = None
        if (
            batch_status == "ACCEPTED"
            and self.max_source_time_span_s is not None
            and facility_time_window["within_configured_source_time_window"] is False
        ):
            time_window_rejection = {
                "status": "REJECTED_SOURCE_TIME_WINDOW",
                "configured_max_source_time_span_s": self.max_source_time_span_s,
                "observed_source_time_span_s": facility_time_window["source_time_span_s"],
                "reason": (
                    "complete component batch exceeded the configured source-time window; "
                    "facility aggregation was withheld"
                ),
            }
            facility_time_window["status"] = "REJECTED_SOURCE_TIME_WINDOW"
            batch_status = "REJECTED"
        deadline_misses = sum(
            entry["result"]["realtime"]["deadline_status"] == "MISSED"
            for entry in accepted
        )
        fresh_count = sum(
            bool(entry["result"]["service"]["fresh_physics_this_update"])
            for entry in accepted
        )
        cache_count = sum(
            bool(entry["result"]["service"]["exact_cache_hit"])
            for entry in accepted
        )
        processing_time_rows: dict[str, dict[str, float | bool | str | None]] = {}
        processing_time_invalid_components: list[str] = []
        realtime_mode_counts: dict[str, int] = {}
        realtime_mode_contract_invalid_components: list[str] = []
        for component_id, entry in components.items():
            if entry.get("status") != "ACCEPTED":
                continue
            service_metadata = entry.get("result", {}).get("service", {})
            service_elapsed_ms = (
                service_metadata.get("service_elapsed_ms")
                if isinstance(service_metadata, Mapping)
                else None
            )
            physics_elapsed_ms = (
                service_metadata.get("physics_run_elapsed_ms")
                if isinstance(service_metadata, Mapping)
                else None
            )
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
                for value in (service_elapsed_ms, physics_elapsed_ms)
            ):
                processing_time_invalid_components.append(component_id)
                continue
            processing_time_rows[component_id] = {
                "service_elapsed_ms": float(service_elapsed_ms),
                "physics_run_elapsed_ms": float(physics_elapsed_ms),
                "fresh_physics_this_update": bool(
                    service_metadata.get("fresh_physics_this_update")
                ),
                "exact_cache_hit": bool(service_metadata.get("exact_cache_hit")),
                "evaluation_mode": (
                    service_metadata.get("mode_contract", {}).get("evaluation_mode")
                    if isinstance(service_metadata.get("mode_contract"), Mapping)
                    else None
                ),
            }
            mode_contract = service_metadata.get("mode_contract")
            mode = (
                mode_contract.get("evaluation_mode")
                if isinstance(mode_contract, Mapping)
                else None
            )
            if mode not in {"cached_diagnostic_1hz", "fresh_physics_background"}:
                realtime_mode_contract_invalid_components.append(component_id)
            else:
                realtime_mode_counts[mode] = realtime_mode_counts.get(mode, 0) + 1
        service_elapsed_values = [
            row["service_elapsed_ms"] for row in processing_time_rows.values()
        ]
        physics_elapsed_values = [
            row["physics_run_elapsed_ms"] for row in processing_time_rows.values()
        ]
        if not processing_time_rows:
            processing_time = {
                "status": "WITHHELD_NO_ACCEPTED_COMPONENT_TIMING",
                "component_rows": {},
                "invalid_components": processing_time_invalid_components,
                "total_service_elapsed_ms": None,
                "mean_service_elapsed_ms": None,
                "max_service_elapsed_ms": None,
                "total_physics_run_elapsed_ms": None,
                "mean_physics_run_elapsed_ms": None,
                "max_physics_run_elapsed_ms": None,
                "realtime_mode_counts": {},
                "realtime_mode_contract_invalid_components": realtime_mode_contract_invalid_components,
                "measurement_policy": (
                    "one synchronous facility batch only; these timings do not establish "
                    "sustained throughput or a 1 Hz fresh-physics claim"
                ),
            }
        else:
            complete_timing = (
                len(processing_time_rows) == len(component_ids)
                and not processing_time_invalid_components
                and batch_status == "ACCEPTED"
            )
            processing_time = {
                "status": "AVAILABLE_COMPLETE_BATCH" if complete_timing else "AVAILABLE_PARTIAL_BATCH",
                "component_rows": processing_time_rows,
                "invalid_components": processing_time_invalid_components,
                "total_service_elapsed_ms": sum(service_elapsed_values),
                "mean_service_elapsed_ms": sum(service_elapsed_values) / len(service_elapsed_values),
                "max_service_elapsed_ms": max(service_elapsed_values),
                "total_physics_run_elapsed_ms": sum(physics_elapsed_values),
                "mean_physics_run_elapsed_ms": sum(physics_elapsed_values) / len(physics_elapsed_values),
                "max_physics_run_elapsed_ms": max(physics_elapsed_values),
                "realtime_mode_counts": realtime_mode_counts,
                "realtime_mode_contract_invalid_components": realtime_mode_contract_invalid_components,
                "measurement_policy": (
                    "one synchronous facility batch only; these timings do not establish "
                    "sustained throughput or a 1 Hz fresh-physics claim"
                ),
            }
        release_resolved_count = sum(
            bool(entry["result"].get("telemetry_boundary", {}).get("equipment_release_resolved"))
            for entry in accepted
        )
        release_path_rows = [
            entry.get("equipment_release_path")
            for entry in accepted
            if isinstance(entry.get("equipment_release_path"), Mapping)
        ]
        release_path_available_count = sum(
            row.get("status") == "AVAILABLE_PROVIDER_RELEASE_PATH"
            for row in release_path_rows
        )
        release_path_component_rows: dict[str, dict[str, object]] = {}
        isolation_status_counts: dict[str, int] = {}
        inventory_status_counts: dict[str, int] = {}
        termination_basis_counts: dict[str, int] = {}
        for component_id, entry in components.items():
            if entry.get("status") != "ACCEPTED":
                continue
            path = entry.get("equipment_release_path")
            if not isinstance(path, Mapping):
                continue
            isolation = path.get("isolation")
            inventory = path.get("inventory")
            termination = path.get("termination")
            isolation_status = (
                isolation.get("status")
                if isinstance(isolation, Mapping)
                else None
            )
            inventory_status = (
                inventory.get("status")
                if isinstance(inventory, Mapping)
                else None
            )
            termination_basis = (
                termination.get("basis")
                if isinstance(termination, Mapping)
                else None
            )
            row: dict[str, object] = {
                "status": path.get("status"),
                "duration_s": path.get("duration_s"),
                "termination_basis": termination_basis,
                "isolation_status": isolation_status,
                "inventory_status": inventory_status,
                "boundary_count": path.get("boundary_count"),
                "shared_inventory": (
                    inventory.get("shared_inventory")
                    if isinstance(inventory, Mapping)
                    else None
                ),
                "remaining_mass_kg": (
                    inventory.get("remaining_mass_kg")
                    if isinstance(inventory, Mapping)
                    else None
                ),
                "mass_residual_kg": (
                    inventory.get("mass_residual_kg")
                    if isinstance(inventory, Mapping)
                    else None
                ),
                "provider_port_state": _provider_port_state_component_ledger(path),
            }
            release_path_component_rows[component_id] = row
            for counts, value in (
                (isolation_status_counts, isolation_status),
                (inventory_status_counts, inventory_status),
                (termination_basis_counts, termination_basis),
            ):
                if isinstance(value, str) and value:
                    counts[value] = counts.get(value, 0) + 1
        if not release_path_component_rows:
            release_path_accounting = {
                "status": "WITHHELD_NO_ACCEPTED_RELEASE_PATH",
                "component_rows": {},
                "isolation_status_counts": {},
                "inventory_status_counts": {},
                "termination_basis_counts": {},
                "mass_aggregation_performed": False,
                "frequency_inference_performed": False,
                "policy": (
                    "release mass is never summed across components; shared two-sided "
                    "inventory remains a component-level ledger"
                ),
            }
        else:
            release_path_accounting = {
                "status": (
                    "AVAILABLE_COMPLETE_BATCH"
                    if batch_status == "ACCEPTED"
                    and len(release_path_component_rows) == len(component_ids)
                    and release_path_available_count == len(component_ids)
                    else "AVAILABLE_PARTIAL_BATCH"
                ),
                "component_rows": release_path_component_rows,
                "isolation_status_counts": isolation_status_counts,
                "inventory_status_counts": inventory_status_counts,
                "termination_basis_counts": termination_basis_counts,
                "mass_aggregation_performed": False,
                "frequency_inference_performed": False,
                "policy": (
                    "release mass is never summed across components; shared two-sided "
                    "inventory remains a component-level ledger"
                ),
            }
        release_path_accounting["strict_release_boundary"] = (
            _strict_realtime_release_boundary_gate(
                batch_status=batch_status,
                component_ids=component_ids,
                release_path_component_rows=release_path_component_rows,
            )
        )
        port_state_rows = {
            component_id: row.get("provider_port_state")
            for component_id, row in release_path_component_rows.items()
            if isinstance(row.get("provider_port_state"), Mapping)
        }
        port_state_all_interval_count = sum(
            row.get("all_intervals_bound") is True
            for row in port_state_rows.values()
        )
        port_state_accounting = {
            "status": (
                "AVAILABLE_COMPLETE_ALL_INTERVALS_BOUND"
                if batch_status == "ACCEPTED"
                and len(port_state_rows) == len(component_ids)
                and port_state_all_interval_count == len(component_ids)
                else "AVAILABLE_COMPLETE_COMPONENT_AUDIT"
                if batch_status == "ACCEPTED"
                and len(port_state_rows) == len(component_ids)
                else "AVAILABLE_PARTIAL_BATCH"
                if port_state_rows
                else "WITHHELD_NO_PROVIDER_PORT_STATE"
            ),
            "component_rows": port_state_rows,
            "component_count": len(component_ids),
            "component_with_state_count": len(port_state_rows),
            "component_all_intervals_bound_count": port_state_all_interval_count,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "promotion_policy": (
                "diagnostic coverage only; missing provider port states are not treated as zero "
                "and never open provider qualification or facility IR/F-N"
            ),
        }
        ignition_rows = {
            component_id: entry["ignition"]
            for component_id, entry in components.items()
            if entry.get("status") == "ACCEPTED" and isinstance(entry.get("ignition"), Mapping)
        }
        available_ignition_rows = {
            component_id: row
            for component_id, row in ignition_rows.items()
            if row.get("status") == "AVAILABLE_IGNITION_BRANCHES"
        }
        ignition_branch_rates = None
        if len(available_ignition_rows) == len(component_ids) and component_ids:
            branch_names = (
                "direct_fire",
                "delayed_flash_fire",
                "delayed_explosion",
                "no_ignition",
            )
            totals = {branch: 0.0 for branch in branch_names}
            complete_rates = True
            for row in available_ignition_rows.values():
                rates = row.get("weighted_branch_frequency_per_year")
                if not isinstance(rates, Mapping) or set(rates) != set(branch_names):
                    complete_rates = False
                    break
                for branch in branch_names:
                    value = rates.get(branch)
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(float(value))
                        or float(value) < 0.0
                    ):
                        complete_rates = False
                        break
                    totals[branch] += float(value)
                if not complete_rates:
                    break
            if complete_rates:
                ignition_branch_rates = totals
        if not ignition_rows:
            ignition_status = "NO_ACCEPTED_COMPONENTS"
        elif len(available_ignition_rows) == len(component_ids):
            ignition_status = "AVAILABLE_CURRENT_WEATHER_IGNITION_ACCOUNTING"
        elif available_ignition_rows:
            ignition_status = "PARTIAL_CURRENT_WEATHER_IGNITION_ACCOUNTING"
        else:
            ignition_status = "WITHHELD_CURRENT_WEATHER_IGNITION_ACCOUNTING"
        ignition_accounting = {
            "status": ignition_status,
            "component_count": len(component_ids),
            "available_component_count": len(available_ignition_rows),
            "withheld_component_count": len(component_ids) - len(available_ignition_rows),
            "component_rows": ignition_rows,
            "weighted_branch_frequency_per_year": ignition_branch_rates,
            "frequency_reallocation_performed": False,
            "facility_ir_fn_promotion": False,
            "frequency_inference_performed": False,
        }
        component_risk_rows = {
            component_id: entry["risk"]
            for component_id, entry in components.items()
            if entry.get("status") == "ACCEPTED" and "risk" in entry
        }
        component_risk_ranking = _realtime_component_risk_ranking(
            component_ids, components
        )
        current_weather_risk_rows = [
            row
            for row in component_risk_rows.values()
            if row.get("status") == "AVAILABLE_CURRENT_WEATHER_IR"
        ]
        current_weather_ir: dict[str, list[float]] = {}
        for row in current_weather_risk_rows:
            values = row.get("annual_ir_low_high")
            if not isinstance(values, Mapping):
                continue
            for receptor_id, endpoints in values.items():
                if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2:
                    continue
                totals = current_weather_ir.setdefault(str(receptor_id), [0.0, 0.0])
                totals[0] += float(endpoints[0])
                totals[1] += float(endpoints[1])
        sensitivity_rows = [
            row
            for row in current_weather_risk_rows
            if isinstance(
                row.get("frequency_sensitivity_current_weather_ir_low_high"),
                Mapping,
            )
        ]
        current_weather_frequency_sensitivity: dict[str, dict[str, list[float]]] = {}
        if len(sensitivity_rows) == len(component_ids):
            for row in sensitivity_rows:
                scenarios = row["frequency_sensitivity_current_weather_ir_low_high"]
                if not isinstance(scenarios, Mapping):
                    continue
                for scenario_id, values in scenarios.items():
                    if not isinstance(values, Mapping):
                        continue
                    scenario_totals = current_weather_frequency_sensitivity.setdefault(
                        str(scenario_id), {}
                    )
                    for receptor_id, endpoints in values.items():
                        if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2:
                            continue
                        totals = scenario_totals.setdefault(str(receptor_id), [0.0, 0.0])
                        totals[0] += float(endpoints[0])
                        totals[1] += float(endpoints[1])
        current_weather_risk_available = (
            batch_status == "ACCEPTED"
            and len(accepted) == len(component_ids)
            and len(current_weather_risk_rows) == len(component_ids)
            and bool(current_weather_ir)
        )
        conditional_expected_death_fn = (
            _realtime_conditional_expected_death_fn(
                current_weather_risk_rows, self.population_binding
            )
            if current_weather_risk_available
            else {
                "status": "WITHHELD_CURRENT_WEATHER_IR_UNAVAILABLE",
                "expected_death_fn_low_high": None,
                "frequency_sensitivity_expected_death_fn_low_high": None,
                "reason": "all declared components do not have accepted current-weather IR",
            }
        )
        aggregate_deadline_status = (
            "REJECTED"
            if rejected or unknown_ids or time_window_rejection is not None
            else ("MISSED" if deadline_misses else "MET")
        )
        return {
            "facility_id": self.facility_id,
            "status": batch_status,
            "component_count": len(component_ids),
            "accepted_component_count": len(accepted),
            "rejected_component_count": len(rejected),
            "unknown_frame_components": list(unknown_ids),
            "missing_frame_components": list(missing_ids),
            "duplicate_streams": {key: list(value) for key, value in duplicate_streams.items()},
            "time_window_rejection": time_window_rejection,
            "components": components,
            "aggregate": {
                "deadline_status": aggregate_deadline_status,
                "deadline_met": batch_status == "ACCEPTED" and deadline_misses == 0,
                "fresh_physics_count": fresh_count,
                "cache_hit_count": cache_count,
                "deadline_miss_count": deadline_misses,
                "facility_time_window": facility_time_window,
                "processing_time": processing_time,
                "realtime_mode_contract": {
                    "schema": "prism.realtime_mode_contract.v1",
                    "evaluation_mode_counts": realtime_mode_counts,
                    "invalid_component_ids": realtime_mode_contract_invalid_components,
                    "fresh_physics_1hz_claim": False,
                    "stale_fallback_used": False,
                    "frequency_learning": False,
                    "release_inference": False,
                },
                "max_source_time_span_s": self.max_source_time_span_s,
                "provider_release_resolved_component_count": release_resolved_count,
                "equipment_release_path_component_count": release_path_available_count,
                "equipment_release_path_withheld_component_count": len(accepted)
                - release_path_available_count,
                "equipment_release_path_accounting": release_path_accounting,
                "provider_port_state_accounting": port_state_accounting,
                "provider_port_state_component_count": len(port_state_rows),
                "provider_port_state_all_interval_component_count": port_state_all_interval_count,
                "provider_port_state_withheld_component_count": len(accepted) - len(port_state_rows),
                "current_weather_ignition_accounting": ignition_accounting,
                "current_weather_annual_ir_low_high": (
                    current_weather_ir if current_weather_risk_available else None
                ),
                "current_weather_ir_available": current_weather_risk_available,
                "current_weather_ir_component_count": len(current_weather_risk_rows),
                "current_weather_ir_withheld_component_count": len(accepted)
                - len(current_weather_risk_rows),
                "component_risk_ranking": component_risk_ranking,
                "current_weather_frequency_sensitivity_ir_low_high": (
                    current_weather_frequency_sensitivity
                    if current_weather_risk_available
                    and len(sensitivity_rows) == len(component_ids)
                    and current_weather_frequency_sensitivity
                    else None
                ),
                "current_weather_frequency_sensitivity_available": bool(
                    current_weather_risk_available
                    and len(sensitivity_rows) == len(component_ids)
                    and current_weather_frequency_sensitivity
                ),
                "conditional_current_weather_expected_death_fn_low_high": (
                    conditional_expected_death_fn["expected_death_fn_low_high"]
                ),
                "conditional_current_weather_expected_death_fn_available": (
                    conditional_expected_death_fn["status"]
                    == "AVAILABLE_CONDITIONAL_CURRENT_WEATHER_EXPECTED_DEATH_FN"
                ),
                "conditional_current_weather_expected_death_fn": conditional_expected_death_fn,
                "population_binding_source_digest": (
                    self.population_binding.source_digest
                    if self.population_binding is not None
                    else None
                ),
                "facility_fn_available": False,
                "frequency_learning": False,
                "release_inference": False,
                "facility_annual_risk_available": False,
                "interpretation": (
                    "component consequence outputs and provenance are available; "
                    "current-weather IR is available only when each accepted component "
                    "has an explicit reviewed literature frequency and receptor harm; "
                    "an explicit population ledger adds a conditional current-weather "
                    "expected-death F/N contribution; facility annual IR/F-N remains withheld"
                ),
            },
        }
    def update_from_rows(
        self,
        rows: Mapping[str, Mapping[str, object]],
        row_bindings: Mapping[str, Mapping[str, object]],
        *,
        now_s: float,
    ) -> dict:
        """Process one explicit tabular row for every declared component.

        ``row_bindings`` is component keyed and must provide exactly
        ``stream_id``, ``sequence``, ``source_time_s``, ``arrival_time_s``,
        ``origin``, and a source-column binding map.  This method performs no
        tag, unit, quality, timestamp, or component inference; it delegates
        each row to ``frame_from_row`` and then uses the existing atomic
        facility frame batch.  Any extra or missing component row is rejected
        before a partial batch can be interpreted as a facility snapshot.
        """
        if not isinstance(rows, Mapping) or not isinstance(row_bindings, Mapping):
            raise TypeError("rows and row_bindings must be component mappings")
        from .inspection_timeseries import frame_from_row

        frames: dict[str, object] = {}
        declared = set(self.bindings)
        row_components = set(rows)
        metadata_components = set(row_bindings)
        unknown_rows = sorted(row_components - declared)
        row_input_errors: dict[str, dict[str, str]] = {}
        for component_id in sorted(declared):
            if component_id not in rows or component_id not in row_bindings:
                continue
            metadata = row_bindings[component_id]
            try:
                if not isinstance(metadata, Mapping):
                    raise ValueError("row binding must be a mapping")
                keys = set(metadata)
                if keys != _REALTIME_ROW_BINDING_KEYS:
                    raise ValueError(
                        "row binding must contain exactly "
                        f"{sorted(_REALTIME_ROW_BINDING_KEYS)}"
                    )
                frames[component_id] = frame_from_row(
                    rows[component_id],
                    stream_id=metadata["stream_id"],
                    sequence=metadata["sequence"],
                    source_time_s=metadata["source_time_s"],
                    arrival_time_s=metadata["arrival_time_s"],
                    origin=metadata["origin"],
                    bindings=metadata["bindings"],
                )
            except (TypeError, ValueError) as error:
                row_input_errors[component_id] = {
                    "error_type": type(error).__name__,
                    "error": str(error),
                }

        # Keep the existing facility rejection accounting for extra component
        # rows, while preserving a structured error for each malformed row.
        frames.update({component_id: None for component_id in unknown_rows})
        result = self.update_from_frames(frames, now_s=now_s)
        for component_id, error in row_input_errors.items():
            result["components"][component_id] = {
                "status": "REJECTED",
                "component_id": component_id,
                "error_type": "RowInputError",
                "error": error["error"],
            }
        result["row_input_errors"] = row_input_errors
        result["missing_row_components"] = sorted(declared - row_components)
        result["missing_row_metadata_components"] = sorted(
            declared - metadata_components
        )
        result["unknown_row_metadata_components"] = sorted(
            metadata_components - declared
        )
        result["row_batch_exact_component_set"] = (
            row_components == declared and metadata_components == declared
        )
        return result


def build_realtime_facility_risk_handoff(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Export one realtime snapshot as a fail-closed facility handoff packet.

    The realtime monitor produces a *conditional current-weather* view.  The
    offline facility ledger, in contrast, requires an annual-condition ID,
    release-branch ID, ignition-branch ID, branch-specific harm, and closed
    expected-death endpoints for every risk atom.  These are different
    contracts.  This exporter preserves the realtime evidence and makes the
    missing ledger fields explicit; it never manufactures IDs, distributes a
    total harm across ignition branches, or promotes the snapshot to annual
    facility IR/F-N.

    The returned packet is intentionally not accepted by
    ``merge_facility_campaign_results``.  A separate reviewed campaign must
    supply the missing scenario metadata and branch-specific consequence
    evidence before the normal facility ledger can be built.
    """
    if not isinstance(snapshot, Mapping):
        raise TypeError("snapshot must be a mapping")
    required = {"facility_id", "status", "component_count", "components", "aggregate"}
    missing = sorted(key for key in required if key not in snapshot)
    if missing:
        raise ValueError(
            "realtime snapshot is missing required fields: " + ", ".join(missing)
        )
    components = snapshot.get("components")
    aggregate = snapshot.get("aggregate")
    if not isinstance(components, Mapping):
        raise ValueError("realtime snapshot components must be a mapping")
    if not isinstance(aggregate, Mapping):
        raise ValueError("realtime snapshot aggregate must be a mapping")
    component_count = snapshot.get("component_count")
    if (
        isinstance(component_count, bool)
        or not isinstance(component_count, int)
        or component_count < 1
        or component_count != len(components)
    ):
        raise ValueError("realtime snapshot component_count does not match components")
    if any(not isinstance(key, str) or not key.strip() for key in components):
        raise ValueError("realtime snapshot component ids must be nonempty strings")

    # Keep the original snapshot immutable for the caller while retaining a
    # reproducible digest of exactly what crossed this boundary.
    snapshot_copy = copy.deepcopy(dict(snapshot))
    snapshot_digest = canonical_digest(snapshot_copy)
    component_rows: list[dict[str, object]] = []
    realtime_risk_atoms: list[dict[str, object]] = []
    available_component_count = 0
    for component_id in sorted(components):
        entry = components[component_id]
        if not isinstance(entry, Mapping):
            raise ValueError(f"component entry must be a mapping: {component_id}")
        risk = entry.get("risk")
        risk_atom = risk.get("risk_atom") if isinstance(risk, Mapping) else None
        risk_status = risk.get("status") if isinstance(risk, Mapping) else None
        path = entry.get("equipment_release_path")
        row = {
            "component_id": component_id,
            "component_status": entry.get("status"),
            "frame_digest": entry.get("frame_digest"),
            "mapping_digest": entry.get("mapping_digest"),
            "risk_status": risk_status,
            "risk_atom_digest": (
                canonical_digest(risk_atom) if isinstance(risk_atom, Mapping) else None
            ),
            "release_path_status": (
                path.get("status") if isinstance(path, Mapping) else None
            ),
            "ledger_compatible": False,
            "ledger_blockers": [
                "missing_annual_condition_id",
                "missing_release_branch_id",
                "missing_ignition_branch_id",
                "missing_branch_specific_receptor_harm",
                "expected_deaths_not_closed",
            ],
        }
        if isinstance(risk_atom, Mapping):
            available_component_count += 1
            realtime_risk_atoms.append(
                {
                    "component_id": component_id,
                    "scope": "CURRENT_WEATHER_CONDITIONAL_REALTIME",
                    "atom": copy.deepcopy(dict(risk_atom)),
                    "ledger_compatible": False,
                    "reason": (
                        "the realtime atom contains one observed-release harm map; "
                        "it is not a branch-complete facility ledger atom"
                    ),
                }
            )
        component_rows.append(row)

    current_weather_ir_available = bool(aggregate.get("current_weather_ir_available"))
    conditional_fn_available = bool(
        aggregate.get("conditional_current_weather_expected_death_fn_available")
    )
    release_path_accounting = aggregate.get("equipment_release_path_accounting")
    release_boundary_gate = None
    if isinstance(release_path_accounting, Mapping):
        candidate = release_path_accounting.get("strict_release_boundary")
        if isinstance(candidate, Mapping):
            release_boundary_gate = copy.deepcopy(dict(candidate))
    handoff_status = (
        "DIAGNOSTIC_CURRENT_WEATHER_SNAPSHOT"
        if snapshot.get("status") == "ACCEPTED" and current_weather_ir_available
        else "REJECTED_OR_WITHHELD_REALTIME_SNAPSHOT"
    )
    return {
        "schema": "prism.realtime_facility_risk_handoff.v1",
        "handoff_status": handoff_status,
        "facility_id": str(snapshot.get("facility_id")),
        "source_snapshot_status": snapshot.get("status"),
        "source_snapshot_digest": snapshot_digest,
        "source_snapshot": snapshot_copy,
        "component_count": component_count,
        "available_realtime_risk_atom_component_count": available_component_count,
        "component_rows": component_rows,
        "realtime_risk_atoms": realtime_risk_atoms,
        "conditional_current_weather": {
            "ir_available": current_weather_ir_available,
            "annual_ir_low_high": copy.deepcopy(
                aggregate.get("current_weather_annual_ir_low_high")
            ),
            "frequency_sensitivity_ir_low_high": copy.deepcopy(
                aggregate.get("current_weather_frequency_sensitivity_ir_low_high")
            ),
            "expected_death_fn_available": conditional_fn_available,
            "expected_death_fn_low_high": copy.deepcopy(
                aggregate.get("conditional_current_weather_expected_death_fn_low_high")
            ),
        },
        "facility_ledger_merge": {
            "status": "WITHHELD_REALTIME_SNAPSHOT_NOT_FACILITY_LEDGER",
            "mergeable": False,
            "reason": (
                "a realtime current-weather snapshot does not provide the complete "
                "annual weather, release, ignition, population, and branch-specific "
                "harm ledger required by facility QRA"
            ),
            "required_inputs": [
                "annual_condition_id_and_probability",
                "release_branch_id_and_probability",
                "ignition_branch_id_and_probability",
                "branch_specific_receptor_harm_low_high",
                "expected_deaths_low_high_closed_over_receptors",
                "qualified_provider_packet_evidence",
                "independent_physical_validation_evidence",
            ],
            "frequency_inference_performed": False,
            "frequency_learning": False,
            "facility_annual_ir_available": False,
            "facility_fn_available": False,
            "facility_ir_fn_promotion": False,
        },
        "evidence_boundary": {
            "strict_release_boundary": release_boundary_gate,
            "qualified_provider_packet_count": None,
            "qualification_evaluated_by_realtime_monitor": False,
            "physical_validation_claim": False,
            "frequency_source": "copied from explicit realtime binding when present",
            "release_inference": bool(aggregate.get("release_inference", False)),
            "processing_time": copy.deepcopy(aggregate.get("processing_time")),
            "facility_time_window": copy.deepcopy(aggregate.get("facility_time_window")),
            "interpretation": (
                "handoff preserves an auditable digital-twin snapshot for a later "
                "reviewed facility campaign; it is not an annual facility risk result"
            ),
        },
    }
