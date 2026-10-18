import json
import sys
from pathlib import Path

from scripts.build_backend_config import build_config
from scripts.check_backend_runtime import check_backend


def test_build_config_pins_public_prism_source(tmp_path: Path):
    config = build_config(
        package_specs=[],
        interpreter=sys.executable,
        timeout_s=10.0,
        required_versions={},
    )

    assert config["packages"][0]["name"] == "prism_qra"
    assert Path(config["packages"][0]["root"]).is_dir()
    assert config["timeout_s"] == 10.0


def test_runtime_check_accepts_current_public_backend(tmp_path: Path):
    config = build_config(
        package_specs=[],
        interpreter=sys.executable,
        timeout_s=10.0,
        required_versions={},
    )
    config_path = tmp_path / "backend.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = check_backend(config_path)

    assert result["status"] == "BACKEND_RUNTIME_READY"
    assert result["worker_response_ok"] is True
    assert result["physical_validation_claim"] is False


def test_runtime_check_reports_bad_source_digest(tmp_path: Path):
    config = build_config(
        package_specs=[],
        interpreter=sys.executable,
        timeout_s=10.0,
        required_versions={},
    )
    config["packages"][0]["sha256"] = "0" * 64
    config_path = tmp_path / "backend.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = check_backend(config_path)

    assert result["status"] == "BACKEND_RUNTIME_CHECK_FAILED"
    assert "revision mismatch" in result["error"]
