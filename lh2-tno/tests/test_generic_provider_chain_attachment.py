import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from attach_generic_provider_chain import attach


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    handoff = json.loads(
        (ROOT / "results/20261115/generic_provider_bound_hazop_quantitative_handoff.json")
        .read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (ROOT / "results/20261115/generic_storage_provider_bound_hazop_evidence_summary.json")
        .read_text(encoding="utf-8")
    )
    return handoff, evidence


def test_provider_chain_attaches_to_one_current_and_one_forecast_request():
    handoff, evidence = _inputs()
    result = attach(handoff, evidence)

    assert result["status"] == "PROVIDER_CHAIN_ATTACHED_OPERATOR_LIMITED"
    assert result["summary"]["matched_request_count"] == 2
    assert result["summary"]["uncomputed_request_count"] == 4
    assert "SLABx_dispersion" in result["provider_evidence"]["consequence_chain"]["stages"]
    assert result["policy"]["facility_qra_promotion"] is False


def test_provider_chain_requires_exact_family_match():
    handoff, evidence = _inputs()
    evidence["exact_identity"]["hazop_scenario_family"] = "vessel_hole"
    try:
        attach(handoff, evidence)
    except ValueError as error:
        assert "exactly one" in str(error)
    else:
        raise AssertionError("mismatched provider family must be rejected")
