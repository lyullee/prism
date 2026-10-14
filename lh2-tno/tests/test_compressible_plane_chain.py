from pathlib import Path
from types import SimpleNamespace
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_compressible_plane_chain import (  # noqa: E402
    CompressiblePlaneChainError,
    bind_facility,
    build_request,
)


ROOT = Path(__file__).resolve().parents[1]
FACILITY = ROOT / "examples" / "compressible_plane_chain_facility.json"


def _release(**overrides):
    values = {
        "component_id": "ambient-vaporizer-01",
        "port_id": "vaporizer-accident-out",
        "position_enu_m": (0.0, 0.0, 1.0),
        "property_basis": SimpleNamespace(fluid="Hydrogen"),
        "termination_basis": "inventory_depletion",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_bind_facility_requires_exact_provider_position():
    facility = bind_facility(FACILITY, _release())
    assert facility.id == "compressible-plane-chain-diagnostic"

    with pytest.raises(CompressiblePlaneChainError, match="position"):
        bind_facility(FACILITY, _release(position_enu_m=(1.0, 0.0, 1.0)))


def test_build_request_rejects_frequency_owned_by_context(tmp_path):
    context = {
        "annual_frequency_per_year": 1.0e-4,
        "release_termination": {
            "basis": "provider_declared",
            "time_s": "provider_duration",
            "provenance": "test",
        },
    }
    path = tmp_path / "context.json"
    path.write_text(json.dumps(context), encoding="utf-8")
    with pytest.raises(CompressiblePlaneChainError, match="initiating frequency"):
        build_request(_release(), path)
