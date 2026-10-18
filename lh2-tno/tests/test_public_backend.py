import json
import hashlib
from pathlib import Path

import pytest

from lh2_tno.backend import BackendError, IsolatedBackend, PackagePin, PersistentIsolatedBackend
from lh2_tno import public_backend
from lh2_tno.contracts import Facility
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.pipeline import ResearchPipeline


def _aggregate_payload():
    return {
        "receptor_ids": ["worker"],
        "atoms": [
            {"event_id": "tank-hole", "annual_condition_id": "wind-a", "ignition_branch": "fire",
             "conditional_weight": .25, "initiating_frequency_per_year": 2e-4,
             "receptor_harm_low_high": {"worker": [.1, .3]}, "expected_deaths_low_high": [1., 3.]},
            {"event_id": "pipe-hole", "annual_condition_id": "wind-b", "ignition_branch": "flash",
             "conditional_weight": .5, "initiating_frequency_per_year": 4e-5,
             "receptor_harm_low_high": {"worker": [.2, .4]}, "expected_deaths_low_high": [2., 4.]},
        ],
    }


@pytest.mark.parametrize("persistent", [False, True])
def test_public_qra_computes_ir_fn_and_harm_in_real_workers(persistent):
    config = public_backend.installed_backend_config(("prism_qra",))
    pin, = config.packages
    # Discovery uses the adapter's own distribution, not another installed checkout.
    assert Path(pin.root) == Path(public_backend.__file__).resolve().parents[1] / "prism_qra"
    backend = PersistentIsolatedBackend(config) if persistent else IsolatedBackend(config)
    try:
        result = backend.run("facility_risk_aggregate", _aggregate_payload())
        # Independent arithmetic: f * weather/branch weight * lethality.
        assert result["data"]["ir_low_high"]["worker"] == pytest.approx([9e-6, 2.3e-5])
        low, high = result["data"]["fn_low_high"]
        assert low["expected_deaths"] == [1., 2.]
        assert high["expected_deaths"] == [3., 4.]
        assert low["cumulative_frequency_per_year"] == pytest.approx([7e-5, 2e-5])
        assert high["cumulative_frequency_per_year"] == pytest.approx([7e-5, 2e-5])
        harm = backend.run("thermal_damage", {"equivalent_heat_flux_w_m2": 25000., "exposure_s": 10.})
        assert 0. < harm["data"]["harm_probability"] < 1.
        assert result["physical_validation_claim"] is False
        assert result["backend_config_digest"] == config.digest()
    finally:
        if persistent:
            backend.close()


def test_public_backend_requires_missing_models_instead_of_substituting(monkeypatch):
    monkeypatch.setattr(public_backend.importlib.util, "find_spec", lambda _: None)
    with pytest.raises(ValueError, match="not installed: lh2dt"):
        public_backend.installed_backend_config(("prism_qra", "lh2dt"))


def test_public_backend_cli_writes_an_explicit_reusable_config(tmp_path):
    target = tmp_path / "config" / "backend.json"
    assert public_backend.main(["--packages", "prism_qra", "--output", str(target)]) == 0
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert [p["name"] for p in stored["packages"]] == ["prism_qra"]
    assert len(stored["packages"][0]["sha256"]) == 64


def test_public_backend_checks_requested_interfaces_before_writing_config(tmp_path):
    target = tmp_path / "missing_source_backend.json"
    with pytest.raises(SystemExit) as error:
        public_backend.main([
            "--packages", "prism_qra", "--require-operation", "integrated_source",
            "--output", str(target),
        ])
    assert error.value.code == 2
    assert not target.exists()


def test_qra_only_interface_audit_does_not_claim_a_complete_physics_backend():
    config = public_backend.installed_backend_config(("prism_qra",))
    audit = public_backend.backend_interface_audit(config)
    assert audit["facility_risk_aggregate"]["interface_files_present"] is True
    assert audit["consequence_chain"]["interface_files_present"] is False
    assert "source_interfaces/freejet_handoff.py" in audit["consequence_chain"]["missing_interfaces"]
    assert all(row["physical_validation_claim"] is False for row in audit.values())


def test_canonical_and_legacy_qra_pins_cannot_be_mixed():
    config = public_backend.installed_backend_config(("prism_qra",))
    old = PackagePin(name="tno", root=config.packages[0].root, sha256=config.packages[0].sha256)
    config = config.model_copy(update={"packages": (*config.packages, old)})
    with pytest.raises(BackendError, match="aliases cannot be combined"):
        IsolatedBackend(config).run("facility_risk_aggregate", _aggregate_payload())


def test_legacy_qra_pin_keeps_the_same_numerical_result():
    config = public_backend.installed_backend_config(("prism_qra",))
    old = PackagePin(name="tno", root=config.packages[0].root, sha256=config.packages[0].sha256)
    config = config.model_copy(update={"packages": (old,)})
    result = IsolatedBackend(config).run("facility_risk_aggregate", _aggregate_payload())
    assert result["data"]["ir_low_high"]["worker"] == pytest.approx([9e-6, 2.3e-5])


def test_bundled_source_interfaces_retain_the_recorded_physics_source():
    root = Path(public_backend.__file__).resolve().parents[1] / "prism_lh2_models"
    provenance = json.loads((root / "SOURCE_PROVENANCE.json").read_text(encoding="utf-8"))
    assert len(provenance["files"]) == 9
    for row in provenance["files"]:
        canonical = (root / row["file"]).read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode()
        assert hashlib.sha256(canonical).hexdigest() == row["utf8_lf_sha256"]
    assert (root / "LICENSE").is_file()
    assert provenance["physical_validation_claim"] is False


def test_public_packages_execute_the_lh2_source_to_harm_chain():
    root = Path(__file__).resolve().parents[1]
    config = public_backend.installed_backend_config(
        require_operations=("integrated_source", "consequence_chain"),
    )
    facility = Facility.model_validate_json((root / "examples/consequence_facility.json").read_text(encoding="utf-8"))
    request = ConsequenceRequest.model_validate_json((root / "examples/consequence_request.json").read_text(encoding="utf-8"))
    result = ResearchPipeline(facility, IsolatedBackend(config)).consequences(request)
    data = result["data"]
    assert data["full_chain_executed"] is True
    assert data["source_ownership"]
    assert data["mass_ledger"]["end_to_end_residual_kg"] == pytest.approx(0., abs=1e-8)
    assert sum(data["ignition_branch_probabilities"].values()) == pytest.approx(1.)
    assert any(max(r["harm_given_observed_release_low_high"]) > 0. for r in data["receptors"])
    assert data["physical_validation_claim"] is False
    assert result["physical_validation_claim"] is False
