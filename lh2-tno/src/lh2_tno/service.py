"""Digital-twin entry point for known leak scenarios and normalized sensors."""
from __future__ import annotations
from collections import OrderedDict
import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
from pathlib import Path
import time
from .backend import BackendError, tree_digest
from .consequences import ConsequenceRequest
from .contracts import canonical_digest


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


def request_from_equipment_resolver(template, normalized, resolver: Callable):
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
    return request


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
            'cache_key':key,'realtime_fresh_physics_claim':False}
        return result

    def update_from_telemetry(self,template,normalized,*,pressure_tag,temperature_tag,release_resolver=None):
        if release_resolver is None:
            request = request_from_telemetry(
                template, normalized, pressure_tag=pressure_tag, temperature_tag=temperature_tag
            )
        else:
            request = request_from_equipment_resolver(template, normalized, release_resolver)
        result=self.evaluate(request)
        result['telemetry_boundary']={k:normalized[k] for k in
            ('origin','independent_measurement_claim','data_age_s','frame_digest','mapping_digest')}
        result['telemetry_boundary']['data_age_at_output_s']=normalized['data_age_s']+result['service']['service_elapsed_ms']/1000
        result['telemetry_boundary']['equipment_release_resolved'] = release_resolver is not None
        result['telemetry_boundary']['interpretation'] = (
            'equipment resolver supplied provider release; no inferred leak size or learned frequency'
            if release_resolver is not None
            else 'known leak geometry; sensor pressure/temperature update, no inferred leak size or learned frequency'
        )
        return result


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
        result = self.service.update_from_telemetry(
            template,
            normalized,
            pressure_tag=pressure_tag,
            temperature_tag=temperature_tag,
            release_resolver=release_resolver,
        )
        source_time = float(frame.source_time_s)
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
        return result


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


class FacilityRealtimeConsequenceMonitor:
    """Batch coordinator for independent component monitors.

    This class combines *provenance and deadline ledgers*, not annual risk.
    Each component still owns its normalizer, consequence service, provider
    release resolver, and cache.  Missing/unknown/duplicate frames and any
    component exception make the batch ``REJECTED``; accepted component
    results remain attached for diagnosis, but no stale result or zero-risk
    placeholder is manufactured for the failed component.
    """

    def __init__(self, bindings: Mapping[str, FacilityRealtimeBinding], *,
                 facility_id: str = "facility", max_components: int = 128):
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

        normalized: dict[str, FacilityRealtimeBinding] = {}
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
            if binding.ambient_pressure_pa is not None:
                if (isinstance(binding.ambient_pressure_pa, bool)
                        or not isinstance(binding.ambient_pressure_pa, (int, float))
                        or not math.isfinite(float(binding.ambient_pressure_pa))
                        or binding.ambient_pressure_pa <= 0):
                    raise ValueError("ambient_pressure_pa must be finite and positive")
            normalized[key] = binding
        self.facility_id = facility_id
        self.bindings = normalized

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
                    "frame_digest": result.get("telemetry_boundary", {}).get("frame_digest"),
                    "mapping_digest": result.get("telemetry_boundary", {}).get("mapping_digest"),
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

        accepted = [entry for entry in components.values() if entry["status"] == "ACCEPTED"]
        rejected = [entry for entry in components.values() if entry["status"] != "ACCEPTED"]
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
        release_resolved_count = sum(
            bool(entry["result"].get("telemetry_boundary", {}).get("equipment_release_resolved"))
            for entry in accepted
        )
        aggregate_deadline_status = (
            "REJECTED" if rejected or unknown_ids else ("MISSED" if deadline_misses else "MET")
        )
        batch_status = "ACCEPTED" if not rejected and not unknown_ids else "REJECTED"
        return {
            "facility_id": self.facility_id,
            "status": batch_status,
            "component_count": len(component_ids),
            "accepted_component_count": len(accepted),
            "rejected_component_count": len(rejected),
            "unknown_frame_components": list(unknown_ids),
            "missing_frame_components": list(missing_ids),
            "duplicate_streams": {key: list(value) for key, value in duplicate_streams.items()},
            "components": components,
            "aggregate": {
                "deadline_status": aggregate_deadline_status,
                "deadline_met": batch_status == "ACCEPTED" and deadline_misses == 0,
                "fresh_physics_count": fresh_count,
                "cache_hit_count": cache_count,
                "deadline_miss_count": deadline_misses,
                "provider_release_resolved_component_count": release_resolved_count,
                "frequency_learning": False,
                "release_inference": False,
                "facility_annual_risk_available": False,
                "interpretation": (
                    "component consequence outputs and provenance are available; "
                    "facility annual IR/F-N remains withheld"
                ),
            },
        }
