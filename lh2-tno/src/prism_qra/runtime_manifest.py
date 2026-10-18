"""Non-sensitive execution and source fingerprint for reproducibility."""
from __future__ import annotations

import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform


def source_fingerprint() -> dict:
    root = Path(__file__).resolve().parent
    names = ("digital_twin_validation.py", "source_term.py",
             "gen_digital_twin_validation.py", "runtime_manifest.py")
    hashes = {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
              for name in names}
    digest = hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    return {"sha256": digest, "files": hashes}


def execution_environment() -> dict:
    return {"python":platform.python_version(), "os":platform.platform(),
            "processor":platform.processor(), "logical_cpu_count":os.cpu_count(),
            "libraries": {name:version(name) for name in ("CoolProp","numpy","pydantic")},
            "load_condition":"not controlled; concurrent local work may affect timing",
            "measured_path":"telemetry boundary plus GH2 source kernel only"}
