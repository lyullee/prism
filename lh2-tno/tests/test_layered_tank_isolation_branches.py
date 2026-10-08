import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "build_layered_tank_isolation_branches.py"
_SPEC = importlib.util.spec_from_file_location("build_layered_tank_isolation_branches", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_branch_coverage_keeps_partial_events_and_probability_accounting():
    report = _MODULE._coverage(
        {
            "work_items": [
                {"event_id": "tank/event", "component_id": "tank-1"},
                {"event_id": "pipe/event", "component_id": "pipe-1"},
            ]
        },
        [
            {
                "event_id": "tank/event",
                "status": "PACKET_BUILT_SYNTHETIC",
                "probability_given_event": 0.99,
            },
            {
                "event_id": "tank/event",
                "status": "PACKET_BUILT_SYNTHETIC",
                "probability_given_event": 0.01,
            },
            {
                "event_id": "pipe/event",
                "status": "UNCOMPUTED",
                "probability_given_event": 0.99,
            },
        ],
    )

    assert report["status"] == "PARTIAL_EXACT_MATCH"
    assert report["exact_match_count"] == 1
    assert report["unmatched_event_count"] == 1
    assert report["built_branch_count"] == 2
    assert report["uncomputed_branch_count"] == 1
    assert report["work_items"][0]["branch_probability_covered"] == pytest.approx(1.0)


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_finite_positive_guard_rejects_invalid_provider_controls(value):
    with pytest.raises(ValueError, match="control"):
        _MODULE._finite_positive("control", value)
