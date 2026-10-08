"""Rules for using a transient source model's returned time history.

The integrated LH2 source can stop naturally when the vessel pressure has
equalised with ambient pressure.  This module makes that distinction explicit:
the chain either receives the complete declared horizon, or it uses the
model's returned history up to its final left-held interval.  It never pads a
short history with an invented flow rate.
"""
from __future__ import annotations

import math
from typing import Literal


def effective_source_duration(
    requested_duration_s: float,
    time_step_s: float,
    returned_times_s: list[float] | tuple[float, ...],
    mode: Literal["declared", "model_natural"] = "declared",
) -> float:
    """Return the physical interval covered by a returned left-held history.

    ``returned_times_s`` contains the start time of each source interval.
    For natural termination, the final interval is therefore covered through
    ``last_start + dt``.  The result is clipped at the requested horizon.
    """
    if mode not in {"declared", "model_natural"}:
        raise ValueError("unsupported source duration mode")
    if not math.isfinite(requested_duration_s) or requested_duration_s <= 0:
        raise ValueError("requested source duration must be positive and finite")
    if not math.isfinite(time_step_s) or time_step_s <= 0:
        raise ValueError("source time step must be positive and finite")
    if not returned_times_s:
        raise ValueError("source returned no usable intervals")
    times = [float(x) for x in returned_times_s]
    if any(not math.isfinite(x) or x < 0 for x in times):
        raise ValueError("source history times must be finite and nonnegative")
    if not math.isclose(times[0], 0.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError("source history must start at time zero")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("source history times must strictly increase")
    if times[-1] >= requested_duration_s + max(1e-10, requested_duration_s * 1e-10):
        raise ValueError("source history extends past the requested horizon")
    expected = math.ceil(requested_duration_s / time_step_s - 1e-10)
    if mode == "declared":
        if len(times) != expected:
            raise ValueError("source ended early; declared horizon is incomplete")
        return requested_duration_s
    # A natural model stop is represented by the final left-held interval.
    # If the model reaches the requested horizon, this is exactly the declared
    # duration; otherwise the chain ends at the final returned interval.
    return min(requested_duration_s, times[-1] + time_step_s)
