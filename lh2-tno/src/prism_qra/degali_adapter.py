"""Isolated native DEGALI diagnostic component for PRISM.

No silent experimental qualification, property defaults, transient sensor-field
claim, or promotion of optional research closures. Runtime revision is a code
tree hash, not the alpha package version alone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class DegaliRequest:
    rate_kg_s: float
    wind_at_release_m_s: float
    release_height_m: float
    orifice_m: float | None
    pool_diameter_m: float | None
    storage_pressure_abs_bar: float
    ambient_temperature_k: float
    relative_humidity_pct: float
    ambient_pressure_pa: float
    max_distance_m: float
    at_distance_m: float | None

    def __post_init__(self):
        for name, value in asdict(self).items():
            if value is None and name in ("orifice_m", "pool_diameter_m", "at_distance_m"):
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"finite numeric {name} required")
        for name in ("rate_kg_s", "wind_at_release_m_s", "storage_pressure_abs_bar",
                     "ambient_temperature_k", "ambient_pressure_pa", "max_distance_m"):
            if getattr(self, name) <= 0:
                raise ValueError(f"positive {name} required")
        if self.release_height_m < 0 or not 0 <= self.relative_humidity_pct <= 100:
            raise ValueError("nonnegative elevation and RH in [0,100] required")
        if (self.orifice_m is None) == (self.pool_diameter_m is None):
            raise ValueError("exactly one native jet or pool geometry required")
        if self.orifice_m is not None:
            if self.orifice_m <= 0 or self.release_height_m <= 0:
                raise ValueError("positive jet orifice/elevation required")
            if self.storage_pressure_abs_bar <= self.ambient_pressure_pa/1e5:
                raise ValueError("pressurised jet requires storage pressure above ambient")
        elif self.pool_diameter_m <= 0:
            raise ValueError("positive pool diameter required")
        if self.at_distance_m is not None and not 0 <= self.at_distance_m <= self.max_distance_m:
            raise ValueError("receptor distance must lie within requested computational extent")

    def native_kwargs(self) -> dict:
        return dict(rate=self.rate_kg_s, wind=self.wind_at_release_m_s,
                    height=self.release_height_m, orifice=self.orifice_m,
                    pool_diameter=self.pool_diameter_m,
                    storage_pressure=self.storage_pressure_abs_bar,
                    ambient_temperature=self.ambient_temperature_k,
                    relative_humidity=self.relative_humidity_pct,
                    ambient_pressure=self.ambient_pressure_pa,
                    max_distance=self.max_distance_m, at_distance=self.at_distance_m)


def request_digest(request: DegaliRequest) -> str:
    return hashlib.sha256(json.dumps(asdict(request), sort_keys=True, allow_nan=False).encode()).hexdigest()


def code_snapshot(package_root: Path) -> dict:
    files = {p.relative_to(package_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(package_root.rglob("*.py")) if "__pycache__" not in p.parts}
    if not files or not (package_root / "lh2.py").is_file():
        raise ValueError("explicit native degali package source required")
    revision = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"revision": revision, "files": files}


def run_degali(request: DegaliRequest, interpreter: Path, source_root: Path,
               timeout_s: float = 120.) -> dict:
    """Return native diagnostics, not authorized management numbers.

    Positive compute limits are runtime controls, not physical validation
    boundaries. Backend failures/timeouts retain no diagnostic values.
    """
    if (isinstance(timeout_s, bool) or not isinstance(timeout_s, (float, int))
            or not math.isfinite(timeout_s) or timeout_s <= 0):
        raise ValueError("positive finite timeout required")
    source_root = source_root.resolve()
    before = code_snapshot(source_root / "degali")
    worker = Path(__file__).with_name("degali_worker.py")
    report = {"component": "DEGALI", "request_sha256": request_digest(request),
              "source_revision": before["revision"], "source_files": before["files"],
              "management_state": "WITHHOLD_OR_ESCALATE", "management_interval": None,
              "status": "diagnostic", "physical_validation_claim": False,
              "default_promotion_allowed": False,
              "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "worker_sha256": hashlib.sha256(worker.read_bytes()).hexdigest()}
    try:
        process = subprocess.run([str(interpreter.resolve()), str(worker), str(source_root)],
                                 input=json.dumps(asdict(request), allow_nan=False),
                                 capture_output=True, text=True, timeout=timeout_s)
        if process.returncode:
            report["failure"] = f"BACKEND_EXIT:{process.returncode}"
            report["stderr"] = process.stderr[-4000:]
            return report
        if code_snapshot(source_root / "degali") != before:
            report["failure"] = "SOURCE_CHANGED_DURING_EXECUTION"
            return report
        payload = json.loads(process.stdout)
        if payload["request_sha256"] != report["request_sha256"]:
            report["failure"] = "BACKEND_REQUEST_MISMATCH"
            return report
        report["native_diagnostics"] = payload
        report["reason"] = "NO_MATCHED_REGISTERED_EVIDENCE_OR_RUNTIME_APPLICABILITY_AUTHORIZATION"
        return report
    except subprocess.TimeoutExpired:
        report["failure"] = "BACKEND_TIMEOUT"
        return report
    except (OSError, ValueError, KeyError) as exc:
        report["failure"] = f"BACKEND_PROTOCOL_ERROR:{type(exc).__name__}"
        return report
