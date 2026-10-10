from __future__ import annotations

import copy
import json
from pathlib import Path

from lh2_tno.isolation_response_audit import audit_isolation_response_campaign


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_ROOT = ROOT / "results/20261009/equipment_isolation_campaign"


def _inputs() -> tuple[dict, dict]:
    return (
        json.loads((CAMPAIGN_ROOT / "provider_response.json").read_text(encoding="utf-8")),
        json.loads((CAMPAIGN_ROOT / "campaign_result.json").read_text(encoding="utf-8")),
    )


def test_provider_isolation_success_and_failure_are_consumed_by_campaign() -> None:
    provider_response, campaign_result = _inputs()

    report = audit_isolation_response_campaign(provider_response, campaign_result)

    assert report["schema"] == "prism.isolation_response_audit.v1"
    assert report["status"] == "ISOLATION_RESPONSE_CHAIN_DIAGNOSTIC"
    assert report["branch_count"] == 10
    assert report["success_branch_count"] == 5
    assert report["failure_branch_count"] == 5
    assert report["campaign_case_count"] == 20
    assert report["risk_atom_count"] == 80
    assert report["blocking_reasons"] == []
    assert all(row["campaign_case_count"] == 2 for row in report["rows"])


def test_nonzero_post_close_flow_blocks_success_claim() -> None:
    provider_response, campaign_result = _inputs()
    broken = copy.deepcopy(provider_response)
    broken["AREA_0.01%"]["success"]["data"]["post_close_max_flow_kg_s"] = 1.0e-9

    report = audit_isolation_response_campaign(broken, campaign_result)

    assert report["status"] == "ISOLATION_RESPONSE_CHAIN_BLOCKED"
    assert any("zero post-close flow" in reason for reason in report["blocking_reasons"])
