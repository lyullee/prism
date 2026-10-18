"""Isolated native DEGALI process worker; JSON request on stdin."""
from dataclasses import asdict
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import sys

from degali_adapter import DegaliRequest, request_digest


def main():
    source_root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source_root))
    from degali.lh2 import assess
    import degali.lh2
    if Path(degali.lh2.__file__).resolve() != source_root / "degali" / "lh2.py":
        raise RuntimeError("unexpected backend import location")
    request = DegaliRequest(**json.load(sys.stdin))
    result = assess(**request.native_kwargs())

    def finite_or_unresolved(value):
        return float(value) if math.isfinite(value) else None

    trajectory = result.trajectory.tolist()
    if any(not all(math.isfinite(x) for x in row) for row in trajectory):
        raise ValueError("nonfinite native trajectory")
    payload = {"request_sha256": request_digest(request), "inputs": asdict(request),
               "distance_to_lfl_m": finite_or_unresolved(result.distance_to_lfl),
               "distance_to_stoichiometric_m": finite_or_unresolved(result.distance_to_stoichiometric),
               "lowest_flammable_height_m": finite_or_unresolved(result.lowest_flammable_height),
               "neutral_buoyancy_mole_fraction": finite_or_unresolved(result.neutral_buoyancy),
               "regime": result.regime, "trajectory_x_z_molefraction": trajectory,
               "warnings": result.warnings, "notes": result.notes,
               "observation_operator": "native steady trajectory centreline; not fixed-sensor time mean",
               "unresolved_crossing_is_no_reach": False,
               "environment": {"python": platform.python_version(),
                               "numpy": version("numpy"), "CoolProp": version("CoolProp")}}
    print(json.dumps(payload, allow_nan=False))


if __name__ == "__main__":
    main()
