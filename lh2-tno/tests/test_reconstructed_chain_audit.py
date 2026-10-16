import json
from pathlib import Path

from lh2_tno.reconstructed_chain_audit import audit_reconstructed_hazop_chain


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_reconstructed_diagnostic_chain_is_structurally_verified():
    report = audit_reconstructed_hazop_chain(
        _load("inspection_center_reconstructed_hazop_runtime_audit.json"),
        _load("inspection_center_reconstructed_hazop_provider_event_binding.json"),
        _load("inspection_center_reconstructed_hazop_provider_consequence_chain.json"),
    )
    assert report["status"] == "RECONSTRUCTED_DIAGNOSTIC_CHAIN_VERIFIED"
    assert report["check_count"] == 5
    assert report["blocked_count"] == 0
    assert report["policy"]["facility_qra_claim"] is False


def test_reconstructed_chain_audit_rejects_qualified_claim():
    chain = _load("inspection_center_reconstructed_hazop_provider_consequence_chain.json")
    chain["policy"]["provider_packets_are_qualified"] = True
    report = audit_reconstructed_hazop_chain(
        _load("inspection_center_reconstructed_hazop_runtime_audit.json"),
        _load("inspection_center_reconstructed_hazop_provider_event_binding.json"),
        chain,
    )
    assert report["status"] == "RECONSTRUCTED_DIAGNOSTIC_CHAIN_BLOCKED"
    assert report["blocked_count"] == 1
    assert report["checks"][-1]["name"] == "diagnostic_promotion_boundary"
