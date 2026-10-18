"""
Dispersion call memoisation and process-pool execution.

Two facts about slabx-lh2 shape this:

    cold start ~3.4 s     -> a process per request is not viable
    global monkey-patch   -> threads raise ConcurrentPatchError; the unit
                             of parallelism is a process, not a thread

and one fact about the pipeline: the same (rate, wind, stability, T, rh,
duration, release geometry) recurs across every wind sector and every
grid point, so the
integration is run once and reused. With twelve sectors that alone is a
twelvefold saving before any parallelism.

The cache key deliberately excludes grid position, because dispersion does
not depend on where the receptor is -- only on the source and the weather.
That is also why no precomputed lookup table is needed: at roughly half a
second per distinct condition, the distinct conditions are few enough to
compute on demand.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Iterable

_CACHE: dict[tuple, object] = {}
_HITS = _MISSES = 0


def key_of(rate_kg_s: float, wind_m_s: float, stability: str,
           temperature_c: float, relative_humidity: float,
           duration_s: float, height_m: float = 0.5,
           nozzle_mm: float = 25.4,
           liquid_fraction: float = 0.559) -> tuple:
    """Rounded so that numerically identical conditions share a slot."""
    return (round(rate_kg_s, 9), round(wind_m_s, 3), stability,
            round(temperature_c, 2), round(relative_humidity, 1),
            round(duration_s, 1), round(height_m, 3),
            round(nozzle_mm, 3), round(liquid_fraction, 4))


def _compute(k: tuple):
    import slabx_adapter as sx
    rate, wind, stab, tc, rh, dur, height, nozzle, liquid_fraction = k
    return k, sx.dispersion(rate, wind, temperature_c=tc,
                            relative_humidity=rh, duration_s=dur,
                            stability=stab, height_m=height,
                            nozzle_mm=nozzle,
                            liquid_fraction=liquid_fraction)


def get(k: tuple):
    global _HITS, _MISSES
    if k in _CACHE:
        _HITS += 1
        return _CACHE[k]
    _MISSES += 1
    _, v = _compute(k)
    _CACHE[k] = v
    return v


def warm(keys: Iterable[tuple], workers: int | None = None) -> dict:
    """Fill the cache in a process pool. Threads would trip the global
    patch, so processes it is."""
    todo = [k for k in dict.fromkeys(keys) if k not in _CACHE]
    if not todo:
        return {"computed": 0, "workers": 0}
    workers = workers or min(len(todo), os.cpu_count() or 1)
    if workers <= 1:
        for k in todo:
            _CACHE[k] = _compute(k)[1]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for k, v in ex.map(_compute, todo):
                _CACHE[k] = v
    return {"computed": len(todo), "workers": workers}


def stats() -> dict:
    total = _HITS + _MISSES
    return {"hits": _HITS, "misses": _MISSES, "entries": len(_CACHE),
            "hit_rate": _HITS / total if total else 0.0}


def clear() -> None:
    global _HITS, _MISSES
    _CACHE.clear()
    _HITS = _MISSES = 0
