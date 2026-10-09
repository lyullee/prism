"""Version-pinned external models in separate Python interpreters."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
from queue import Empty, Queue
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

    def run(self, operation: Literal["integrated_source", "liquid_jet_source", "vent_stack", "equipment_network_exit", "equipment_dynamic_isolation", "equipment_dynamic_inventory", "declared_pool", "assurance", "thermal_damage", "consequence_chain", "facility_risk_aggregate"], payload: dict) -> dict:
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


class PersistentIsolatedBackend:
    """Pinned backend session for repeated fresh-physics updates.

    ``IsolatedBackend`` starts a clean interpreter for every request.  This
    session keeps one worker alive so scientific-library imports are paid once,
    while source pins and the worker revision are still checked around every
    request.  A failed or timed-out request is never converted into a cache
    result.
    """

    def __init__(self, config: BackendConfig):
        if not isinstance(config, BackendConfig):
            raise TypeError("config must be BackendConfig")
        self.config = config
        self._worker_path = Path(__file__).with_name("worker.py")
        self._adapter_digest = tree_digest(self._worker_path.parent)
        self._worker_digest = hashlib.sha256(self._worker_path.read_bytes()).hexdigest()
        self._lock = threading.Lock()
        self._closed = False
        self._validate_pins()
        try:
            self._process = subprocess.Popen(
                [self.config.interpreter, "-B", "-X", "utf8", str(self._worker_path), "--serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as error:
            raise BackendError(f"persistent backend could not start: {error}") from error

    def _validate_pins(self) -> None:
        for pin in self.config.packages:
            if tree_digest(Path(pin.root)) != pin.sha256:
                raise BackendError(f"revision mismatch: {pin.name}")
        if tree_digest(self._worker_path.parent) != self._adapter_digest:
            raise BackendError("adapter source revision mismatch")

    def _terminate(self) -> None:
        process = getattr(self, "_process", None)
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)

    def _readline(self, timeout_s: float) -> str:
        if self._process.stdout is None:
            raise BackendError("persistent backend stdout is unavailable")
        result: Queue[str | BaseException] = Queue(maxsize=1)

        def read() -> None:
            try:
                result.put(self._process.stdout.readline())
            except BaseException as error:  # pragma: no cover - OS-specific pipe failures
                result.put(error)

        threading.Thread(target=read, daemon=True).start()
        try:
            value = result.get(timeout=timeout_s)
        except Empty as error:
            self._terminate()
            raise BackendError("persistent backend deadline exceeded; no result available") from error
        if isinstance(value, BaseException):
            raise BackendError(f"persistent backend read failed: {value}") from value
        if not value:
            self._terminate()
            stderr = self._process.stderr.read()[-1000:] if self._process.stderr is not None else ""
            raise BackendError(f"persistent backend exited without a result: {stderr}")
        return value

    def run(
        self,
        operation: Literal[
            "integrated_source", "liquid_jet_source", "vent_stack",
            "equipment_network_exit", "equipment_dynamic_isolation",
            "equipment_dynamic_inventory", "declared_pool", "assurance",
            "thermal_damage", "consequence_chain", "facility_risk_aggregate",
        ],
        payload: dict,
    ) -> dict:
        if self._closed:
            raise BackendError("persistent backend is closed")
        started = time.perf_counter()
        request = {
            "operation": operation,
            "payload": payload,
            "packages": [item.model_dump() for item in self.config.packages],
            "required_versions": self.config.required_versions,
        }
        with self._lock:
            self._validate_pins()
            if self._process.poll() is not None:
                raise BackendError("persistent backend worker is not running")
            try:
                if self._process.stdin is None:
                    raise BackendError("persistent backend stdin is unavailable")
                self._process.stdin.write(json.dumps(request, allow_nan=False) + "\n")
                self._process.stdin.flush()
                result = json.loads(self._readline(float(self.config.timeout_s)))
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
                self._terminate()
                raise BackendError(f"persistent backend returned invalid JSON: {error}") from error
            if not result.get("ok"):
                raise BackendError(result.get("error", "backend failure"))
            self._validate_pins()
            result.update({
                "request_digest": canonical_digest(payload),
                "backend_config_digest": self.config.digest(),
                "worker_sha256": self._worker_digest,
                "adapter_source_digest": self._adapter_digest,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "physical_validation_claim": False,
                "persistent_worker": True,
            })
            return result

    def close(self) -> None:
        """Stop the warm worker and release its pipes."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._terminate()
            for stream in (
                getattr(self._process, "stdin", None),
                getattr(self._process, "stdout", None),
                getattr(self._process, "stderr", None),
            ):
                if stream is not None:
                    stream.close()

    def __enter__(self) -> "PersistentIsolatedBackend":
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()

    def __del__(self):  # pragma: no cover - interpreter shutdown ordering
        try:
            self.close()
        except Exception:
            pass
