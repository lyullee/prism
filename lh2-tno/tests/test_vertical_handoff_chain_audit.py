import json
from pathlib import Path

from lh2_tno.vertical_handoff_chain_audit import build_vertical_handoff_chain_audit


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "results/20261024/native_generic_scope_vertical_merged_facility_ledger_population_v3.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog_from_campaign(campaign: dict) -> dict:
    """Build a small tracked fixture from the vertical case identities."""
    catalog = {}
    for case in campaign["cases"]:
        if not str(case.get("event_id", "")).startswith("generic-lh2-full-scope-example/vertical-handoff/"):
            continue
        identity = case["provider_packet_identity"]
        digest = identity["provider_result_digests"][0]
        catalog.setdefault(
            f"source-{digest}",
            {
                "provider_result_digest": digest,
                "duration_s": identity["duration_s"][0],
                "available_mass_kg": identity["available_mass_kg"][0],
                "cumulative_mass_out_kg": identity["cumulative_mass_out_kg"][0],
                "vertical_handoff": {"states": [{"time_s": 0.0}, {"time_s": 0.2}]},
            },
        )
    return catalog


def test_vertical_handoff_catalog_closes_operator_limited_events():
    campaign = _load(CAMPAIGN)
    result = build_vertical_handoff_chain_audit(campaign, _catalog_from_campaign(campaign))
    assert result["status"] == "VERTICAL_OPERATOR_LIMITED_CHAIN_CLOSED"
    assert result["vertical_event_count"] == 5
    assert result["vertical_chain_closed_event_count"] == 5
    assert result["vertical_case_count"] == 10
    assert result["vertical_handoff_state_history_event_count"] == 5
    assert result["qualified_provider_packet_count"] == 0
    assert result["facility_qra_claim"] is False


def test_vertical_handoff_catalog_mismatch_fails_closed():
    campaign = _load(CAMPAIGN)
    catalog = _catalog_from_campaign(campaign)
    first_key = next(iter(catalog))
    catalog[first_key]["cumulative_mass_out_kg"] *= 2.0
    result = build_vertical_handoff_chain_audit(campaign, catalog)
    assert result["status"] == "BLOCKED_VERTICAL_CHAIN_CLOSURE"
    assert result["vertical_chain_mismatch_event_ids"]


def test_vertical_handoff_without_base_packet_audit_stays_local():
    campaign = _load(CAMPAIGN)
    result = build_vertical_handoff_chain_audit(campaign, _catalog_from_campaign(campaign))
    assert result["all_declared_events_diagnostic_chain_closed"] is False
    assert result["base_packet_chain_status"] is None
