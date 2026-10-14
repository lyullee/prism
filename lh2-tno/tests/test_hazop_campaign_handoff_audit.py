from __future__ import annotations

from copy import deepcopy

from lh2_tno.hazop_campaign import build_hazop_facility_campaign_result
from lh2_tno.hazop_campaign_handoff_audit import audit_hazop_campaign_handoff

from test_hazop_campaign import _annual_conditions, _binding, _runtime_result


def _handoff() -> dict:
    return build_hazop_facility_campaign_result(
        _runtime_result(),
        annual_conditions=_annual_conditions(),
        scenario_bindings=[_binding()],
        expected_component_ids=("TK-01",),
    )


def test_hazop_handoff_audit_recomputes_embedded_chain_diagnostics() -> None:
    report = audit_hazop_campaign_handoff(_handoff())
    assert report["status"] == "HAZOP_CAMPAIGN_HANDOFF_AUDITED_CHAIN_PARTIAL"
    assert report["hazop_scenario_trace_status"] == "HAZOP_SCENARIO_TRACE_COMPLETE"
    assert report["chain_closed"] is False
    assert report["embedded_audit_mismatch_count"] == 0
    assert report["policy"]["facility_qra_promotion"] is False


def test_hazop_handoff_audit_blocks_embedded_trace_drift() -> None:
    handoff = _handoff()
    handoff["hazop_scenario_trace_audit"] = deepcopy(handoff["hazop_scenario_trace_audit"])
    handoff["hazop_scenario_trace_audit"]["traceable_event_count"] = 0
    report = audit_hazop_campaign_handoff(handoff)
    assert report["status"] == "HAZOP_CAMPAIGN_HANDOFF_AUDIT_BLOCKED"
    assert report["embedded_audit_mismatch_count"] == 1
    assert any("embedded audit differs" in reason for reason in report["blocking_reasons"])


def test_hazop_handoff_audit_rejects_non_handoff_schema() -> None:
    handoff = _handoff()
    handoff["schema_version"] = "prism.realtime_facility_campaign.v1"
    report = audit_hazop_campaign_handoff(handoff)
    assert report["status"] == "HAZOP_CAMPAIGN_HANDOFF_AUDIT_BLOCKED"
    assert any("unsupported HAZOP handoff schema" in reason for reason in report["blocking_reasons"])


def test_hazop_handoff_audit_requires_embedded_chain_records() -> None:
    handoff = _handoff()
    handoff.pop("risk_atom_chain_audit")
    report = audit_hazop_campaign_handoff(handoff)
    assert report["status"] == "HAZOP_CAMPAIGN_HANDOFF_AUDIT_BLOCKED"
    assert any("risk_atom_chain_audit is missing" in reason for reason in report["blocking_reasons"])
