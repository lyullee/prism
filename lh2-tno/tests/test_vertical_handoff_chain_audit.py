import json
from pathlib import Path

from lh2_tno.vertical_handoff_chain_audit import build_vertical_handoff_chain_audit


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "results/20261024/native_generic_scope_vertical_merged_facility_ledger_population_v3.json"
CATALOG = ROOT / "results/20261020/vertical_vent_all_bins/resolved_release_catalog.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_vertical_handoff_catalog_closes_operator_limited_events():
    result = build_vertical_handoff_chain_audit(_load(CAMPAIGN), _load(CATALOG))
    assert result["status"] == "VERTICAL_OPERATOR_LIMITED_CHAIN_CLOSED"
    assert result["vertical_event_count"] == 5
    assert result["vertical_chain_closed_event_count"] == 5
    assert result["vertical_case_count"] == 10
    assert result["vertical_handoff_state_history_event_count"] == 5
    assert result["qualified_provider_packet_count"] == 0
    assert result["facility_qra_claim"] is False


def test_vertical_handoff_catalog_mismatch_fails_closed():
    catalog = _load(CATALOG)
    first_key = next(iter(catalog))
    catalog[first_key]["cumulative_mass_out_kg"] *= 2.0
    result = build_vertical_handoff_chain_audit(_load(CAMPAIGN), catalog)
    assert result["status"] == "BLOCKED_VERTICAL_CHAIN_CLOSURE"
    assert result["vertical_chain_mismatch_event_ids"]


def test_vertical_handoff_without_base_packet_audit_stays_local():
    result = build_vertical_handoff_chain_audit(_load(CAMPAIGN), _load(CATALOG))
    assert result["all_declared_events_diagnostic_chain_closed"] is False
    assert result["base_packet_chain_status"] is None
