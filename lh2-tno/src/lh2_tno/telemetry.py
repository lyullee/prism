"""Transactional sensor normalization; no inference of unspecified metadata."""
from __future__ import annotations
import math
from typing import Literal
from pydantic import Field
from .contracts import Contract, Name, Nonnegative, Positive, canonical_digest


class TagMapping(Contract):
    tag: Name
    component_id: Name
    quantity: Literal["pressure", "temperature", "mass_flow", "level_fraction", "hydrogen_fraction", "differential_pressure"]
    source_unit: Name
    pressure_basis: Literal["absolute", "gauge", "unresolved"] | None = None
    sensor_location: Name | None = None
    required: bool = True
    scale_to_si: float | None = None
    offset_to_si: float | None = None
    minimum_si: float | None = None
    maximum_si: float | None = None


class Value(Contract):
    value: float
    unit: Name
    quality: Literal["valid", "invalid", "suspect", "missing"]


class Frame(Contract):
    stream_id: Name
    sequence: int = Field(ge=0)
    source_time_s: Nonnegative
    arrival_time_s: Nonnegative
    origin: Literal["historian_measured", "figure_digitized", "video_recovered", "reconstructed", "model_prediction", "synthetic"]
    values: dict[str, Value]


class FrameRejected(ValueError):
    pass


class TelemetryNormalizer:
    def __init__(self, mappings: tuple[TagMapping, ...], maximum_age_s: float):
        if not math.isfinite(maximum_age_s) or maximum_age_s < 0:
            raise ValueError("finite nonnegative maximum age required")
        if not mappings or len({x.tag for x in mappings}) != len(mappings):
            raise ValueError("nonempty unique mappings required")
        for x in mappings:
            if x.minimum_si is not None and x.maximum_si is not None and x.minimum_si > x.maximum_si:
                raise ValueError("invalid sensor range")
            if (x.scale_to_si is None) != (x.offset_to_si is None):
                raise ValueError("explicit conversion requires scale and offset")
        self.mappings = {x.tag: x for x in mappings}
        self.maximum_age_s = maximum_age_s
        self._last: dict[str, tuple[int, float]] = {}

    def normalize(self, frame: Frame, *, now_s: float, ambient_pressure_pa: float | None = None) -> dict:
        if not math.isfinite(now_s) or now_s < frame.arrival_time_s:
            raise FrameRejected("invalid current/arrival time")
        if frame.source_time_s > frame.arrival_time_s:
            raise FrameRejected("source timestamp is in the future")
        if now_s - frame.source_time_s > self.maximum_age_s:
            raise FrameRejected("stale frame")
        last = self._last.get(frame.stream_id)
        if last and (frame.sequence <= last[0] or frame.source_time_s <= last[1]):
            raise FrameRejected("duplicate or out-of-order frame")
        if set(frame.values) - set(self.mappings):
            raise FrameRejected("unknown tag")
        output = {}
        for tag, m in self.mappings.items():
            v = frame.values.get(tag)
            if v is None:
                if m.required: raise FrameRejected(f"missing required tag: {tag}")
                continue
            if v.quality != "valid" or v.unit != m.source_unit:
                raise FrameRejected(f"bad quality/unit: {tag}")
            if m.sensor_location is None:
                raise FrameRejected(f"unresolved sensor location: {tag}")
            if m.scale_to_si is not None:
                value = v.value*m.scale_to_si + m.offset_to_si
            else:
                known = {"pressure": {"Pa": (1,0), "kPa": (1e3,0), "MPa": (1e6,0), "bar": (1e5,0)},
                         "differential_pressure": {"Pa": (1,0), "kPa": (1e3,0)},
                         "temperature": {"K": (1,0), "degC": (1,273.15)},
                         "mass_flow": {"kg/s": (1,0)}, "level_fraction": {"1": (1,0), "%": (.01,0)},
                         "hydrogen_fraction": {"1": (1,0), "vol%": (.01,0)}}
                conversion = known[m.quantity].get(m.source_unit)
                if conversion is None: raise FrameRejected(f"unresolved conversion: {tag}")
                scale, offset = conversion
                value = v.value*scale + offset
            if m.quantity == "pressure":
                if m.pressure_basis not in {"absolute", "gauge"}:
                    raise FrameRejected(f"unresolved pressure basis: {tag}")
                if m.pressure_basis == "gauge":
                    if ambient_pressure_pa is None or not math.isfinite(ambient_pressure_pa) or ambient_pressure_pa <= 0:
                        raise FrameRejected("gauge conversion requires ambient absolute pressure")
                    value += ambient_pressure_pa
            if not math.isfinite(value): raise FrameRejected(f"nonfinite converted value: {tag}")
            if m.quantity in {"pressure", "temperature"} and value <= 0:
                raise FrameRejected(f"nonpositive absolute state: {tag}")
            if m.quantity in {"level_fraction", "hydrogen_fraction"} and not 0 <= value <= 1:
                raise FrameRejected(f"fraction out of range: {tag}")
            if m.minimum_si is not None and value < m.minimum_si or m.maximum_si is not None and value > m.maximum_si:
                raise FrameRejected(f"outside sensor range: {tag}")
            output[tag] = {"component_id":m.component_id, "quantity":m.quantity, "value_si":value,
                           "sensor_location":m.sensor_location}
        # Commit only after every conversion succeeds. Rejected frames can be corrected.
        self._last[frame.stream_id] = (frame.sequence, frame.source_time_s)
        return {"values":output, "origin":frame.origin, "independent_measurement_claim":frame.origin=="historian_measured",
                "data_age_s":now_s-frame.source_time_s, "frame_digest":frame.digest(),
                "mapping_digest":canonical_digest([x.model_dump(mode="json") for x in self.mappings.values()])}
