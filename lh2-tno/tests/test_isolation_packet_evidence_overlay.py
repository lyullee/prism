from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_isolation_packet_evidence_overlay.py"
SPEC = importlib.util.spec_from_file_location("isolation_packet_overlay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_overlay_rebinds_exact_isolation_packets_without_promotion() -> None:
    base = _load(
        ROOT
        / "results"
        / "20261109"
        / "generic_scope_packet_evidence_source_state_closure_rebound.json"
    )
    overlay = _load(ROOT / "examples" / "generic_lh2_isolation_packet_overlay.json")
    result = MODULE.build_overlay(
        base,
        overlay,
        packet_root=ROOT,
        base_packet_root=ROOT / "results" / "20261031" / "native_generic_scope_packets_pipefix",
    )

    assert result["status"] == "CUSTOM_ISOLATION_PACKET_OVERLAY_DIAGNOSTIC"
    assert result["overlay"]["selected_count"] == 12
    assert result["overlay"]["qualified_provider_packet_count"] == 0
    assert result["overlay"]["provider_packet_promoted"] is False
    assert result["overlay"]["facility_qra_claim"] is False

    rows = {row["event_id"]: row for row in result["rows"]}
    for event_id in overlay["mappings"]:
        row = rows[event_id["event_id"]]
        evidence = row["evidence"]
        assert evidence["strict_packet_valid"] is True
        assert evidence["overlay_type"] == "reviewed_isolation_success_diagnostic"
        assert evidence["overlay_provider_termination_basis"] == "reviewed_isolation_success"
        assert event_id["expected_port_id"] in evidence["overlay_provider_port_ids"]
