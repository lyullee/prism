"""Version-pinned external models in separate Python interpreters."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Literal
from pydantic import Field
from .contracts import Contract, Name, Positive, canonical_digest


def tree_digest(root: Path) -> str:
    files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    if not files: raise ValueError(f"no Python source at {root}")
    contents = {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return canonical_digest(contents)


class PackagePin(Contract):
    name: Name
    root: Name
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BackendConfig(Contract):
    interpreter: Name
    packages: tuple[PackagePin, ...]
    timeout_s: Positive = 120
    required_versions: dict[str, str] = Field(default_factory=dict)


class BackendError(RuntimeError):
    pass


class IsolatedBackend:
    def __init__(self, config: BackendConfig):
        if len({p.name for p in config.packages}) != len(config.packages) or not config.packages:
            raise ValueError("nonempty unique backend packages required")
        self.config = config

    def run(self, operation: Literal["integrated_source", "vent_stack", "equipment_network_exit", "declared_pool", "assurance", "thermal_damage", "consequence_chain"], payload: dict) -> dict:
        started=time.perf_counter()
        for pin in self.config.packages:
            if tree_digest(Path(pin.root)) != pin.sha256:
                raise BackendError(f"source revision mismatch: {pin.name}")
        request={"operation":operation,"payload":payload,"packages":[x.model_dump() for x in self.config.packages],
                 "required_versions":self.config.required_versions}
        encoded=json.dumps(request,allow_nan=False)
        worker=Path(__file__).with_name("worker.py")
        adapter_digest=tree_digest(worker.parent)
        worker_digest=hashlib.sha256(worker.read_bytes()).hexdigest()
        try:
            p=subprocess.run([self.config.interpreter,"-B","-X","utf8",str(worker)],input=encoded,text=True,encoding="utf-8",
                             capture_output=True,timeout=self.config.timeout_s)
        except subprocess.TimeoutExpired as e:
            raise BackendError("backend deadline exceeded; no result available") from e
        except OSError as e:
            raise BackendError(f"backend could not start: {e}") from e
        if p.returncode: raise BackendError(f"backend process failed: {p.stderr[-1000:]}")
        try: result=json.loads(p.stdout)
        except ValueError as e: raise BackendError("invalid backend JSON") from e
        if not result.get("ok"): raise BackendError(result.get("error","backend failure"))
        for pin in self.config.packages:
            if tree_digest(Path(pin.root)) != pin.sha256:
                raise BackendError(f"source changed during computation: {pin.name}")
        if tree_digest(worker.parent)!=adapter_digest:
            raise BackendError('adapter source changed during computation')
        json.dumps(result,allow_nan=False)
        result.update({"request_digest":canonical_digest(payload),"backend_config_digest":self.config.digest(),
                       "worker_sha256":worker_digest,
                       "adapter_source_digest":adapter_digest,
                       "elapsed_ms":(time.perf_counter()-started)*1000,"physical_validation_claim":False})
        return result
