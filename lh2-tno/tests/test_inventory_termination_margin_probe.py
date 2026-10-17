"""Regression checks for the tracked inventory-termination evidence."""

from __future__ import annotations

import json
from pathlib import Path


def test_inventory_margin_probe_keeps_open_provider_cases_open() -> None:
    path = (
        Path(__file__).parents[1]
        / "results"
        / "20261115"
        / "native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current"
        / "inventory_termination_margin_probe.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["schema_version"] == "prism.inventory_termination_margin_probe.v1"
    assert record["request_policy"]["no_extrapolation"] is True
    assert record["request_policy"]["no_termination_basis_substitution"] is True
    assert record["request_policy"]["facility_qra_claim"] is False
    assert record["depleted_case_count"] == 0
    assert record["open_case_count"] == 5
    assert all(
        row["status"] in {"HORIZON_OR_INTERVAL_OPEN", "PROVIDER_ERROR"}
        for row in record["rows"]
    )
