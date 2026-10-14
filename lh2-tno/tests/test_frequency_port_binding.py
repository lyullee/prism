import json
from pathlib import Path

import pytest

from lh2_tno.frequency_port_binding import (
    FrequencyPortBindingError,
    bind_frequency_ports_to_campaign,
    bind_frequency_ports_to_campaign_result,
)


ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_full_scope_crosswalk_binds_generated_events_to_declared_ports():
    campaign, audit = bind_frequency_ports_to_campaign(
        _load("results/20261031/native_generic_scope_packets_pipefix/campaign_rebound_state_bound.json"),
        _load("examples/generic_lh2_frequency_port_crosswalk.json"),
        manifest=_load("examples/generic_lh2_full_scope_manifest.json"),
    )

    assert audit["generated_event_count"] == 24
    assert audit["generated_port_scoped_event_count"] == 24
    assert audit["provider_request_port_mismatch_count"] == 0
    assert all(asset.get("port_ids") or asset.get("port_ids_by_loc") for asset in campaign["frequency_plan"]["assets"])


def test_non_precomputed_plan_requires_manifest_for_port_binding():
    with pytest.raises(FrequencyPortBindingError, match="manifest is required"):
        bind_frequency_ports_to_campaign(
            _load("results/20261031/native_generic_scope_packets_pipefix/campaign_rebound_state_bound.json"),
            _load("examples/generic_lh2_frequency_port_crosswalk.json"),
        )


def test_result_binding_propagates_one_explicit_port_to_all_rows():
    result = {
        "events": [{"id": "event-1"}],
        "cases": [{"event_id": "event-1"}],
        "uncomputed_cases": [],
        "risk_atoms": [{"event_id": "event-1"}],
    }

    bound, audit = bind_frequency_ports_to_campaign_result(
        result, {"event-1": ["component.accident-out"]}
    )

    assert audit["port_scoped_event_count"] == 1
    assert bound["events"][0]["port_ids"] == ["component.accident-out"]
    assert bound["cases"][0]["frequency_port_ids"] == ["component.accident-out"]
    assert bound["risk_atoms"][0]["frequency_port_ids"] == ["component.accident-out"]
