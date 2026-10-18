"""Strict regression comparison of values AND evidence metadata."""
from __future__ import annotations

import math


def differences(current, baseline, path="results") -> list[str]:
    if isinstance(current, bool) or isinstance(baseline, bool):
        equal = type(current) is type(baseline) and current == baseline
    elif isinstance(current, (int, float)) and isinstance(baseline, (int, float)):
        equal = (math.isfinite(current) and math.isfinite(baseline)
                 and math.isclose(current, baseline, rel_tol=1e-9, abs_tol=0.0))
    elif isinstance(current, dict) and isinstance(baseline, dict):
        out = []
        for key in sorted(current.keys() | baseline.keys()):
            name = f"{path}.{key}"
            if key not in baseline:
                out.append(f"NEW {name}")
            elif key not in current:
                out.append(f"REMOVED {name}")
            else:
                out.extend(differences(current[key], baseline[key], name))
        return out
    elif isinstance(current, (list, tuple)) and isinstance(baseline, (list, tuple)):
        if len(current) != len(baseline):
            return [f"CHANGED {path}: length {len(baseline)} -> {len(current)}"]
        return [change for i, (a, b) in enumerate(zip(current, baseline))
                for change in differences(a, b, f"{path}[{i}]")]
    else:
        equal = type(current) is type(baseline) and current == baseline
    return [] if equal else [f"CHANGED {path}: {baseline!r} -> {current!r}"]
