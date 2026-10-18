from dataclasses import replace
from pathlib import Path
import subprocess

import pytest

from degali_adapter import DegaliRequest, code_snapshot, request_digest, run_degali


def request():
    return DegaliRequest(.285, 2.5, .5, .0254, None, 6.01325, 288.15, 65.,
                         101325., 10., 6.)


@pytest.mark.parametrize("changes", [
    {"rate_kg_s": float("nan")}, {"wind_at_release_m_s": 0.},
    {"orifice_m": None}, {"pool_diameter_m": 9.1}, {"relative_humidity_pct": 101.},
    {"release_height_m": 0.}, {"storage_pressure_abs_bar": .9},
    {"at_distance_m": 11.}, {"rate_kg_s": True},
])
def test_bad_requests_fail_before_backend(changes):
    with pytest.raises(ValueError):
        replace(request(), **changes)


def test_explicit_native_unit_mapping_and_request_digest():
    r = request()
    assert r.native_kwargs()["storage_pressure"] == 6.01325
    assert r.native_kwargs()["wind"] == 2.5
    assert request_digest(r) != request_digest(replace(r, rate_kg_s=.28))


def test_timeout_returns_no_management_or_diagnostic_numbers(tmp_path, monkeypatch):
    package = tmp_path / "degali"
    package.mkdir()
    (package / "lh2.py").write_text("# fixture only", encoding="utf-8")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("test-worker", 1.)

    monkeypatch.setattr(subprocess, "run", timeout)
    result = run_degali(request(), Path("test-interpreter"), tmp_path, 1.)
    assert result["failure"] == "BACKEND_TIMEOUT"
    assert result["management_interval"] is None and "native_diagnostics" not in result


def test_source_revision_changes_with_code(tmp_path):
    p = tmp_path / "lh2.py"
    p.write_text("# before", encoding="utf-8")
    before = code_snapshot(tmp_path)
    p.write_text("# after", encoding="utf-8")
    assert code_snapshot(tmp_path)["revision"] != before["revision"]
