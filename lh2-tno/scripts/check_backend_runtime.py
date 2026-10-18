"""Check an external PRISM backend before running a facility campaign.

The check performs no risk calculation and never promotes evidence.  It
validates the pinned source trees, dependency versions, and one minimal
persistent-worker request so a campaign cannot fail later with an opaque
child-process exit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, BackendError, PersistentIsolatedBackend


def check_backend(config_path: Path) -> dict[str, object]:
    started = time.perf_counter()
    config = BackendConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    result: dict[str, object] = {
        "schema_version": "prism.backend_runtime_check.v1",
        "status": "BACKEND_RUNTIME_CHECK_FAILED",
        "config_path": str(config_path),
        "package_pin_count": len(config.packages),
        "required_versions": dict(config.required_versions),
        "physical_validation_claim": False,
    }
    try:
        with PersistentIsolatedBackend(config) as backend:
            response = backend.run("assurance", {"outputs": [], "records": []})
        environment = response.get("environment", {})
        result.update(
            {
                "status": "BACKEND_RUNTIME_READY",
                "worker_response_ok": response.get("ok") is True,
                "environment": environment,
            }
        )
    except (BackendError, OSError, ValueError, json.JSONDecodeError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = check_backend(args.backend_config)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {
            "schema_version": "prism.backend_runtime_check.v1",
            "status": "BACKEND_RUNTIME_CHECK_FAILED",
            "error": f"{type(error).__name__}: {error}",
            "physical_validation_claim": False,
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "BACKEND_RUNTIME_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
