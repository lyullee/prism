from __future__ import annotations

import pytest

from lh2_tno.hazop_event_mode_binding_merge import merge_hazop_event_mode_bindings


def _campaign():
    return {
        "events": [
            {
                "id": "base/event",
                "model_component_id": "tank-01",
                "profile": "LH2_VESSEL",
                "release": {"mode": "hole"},
            },
            {
                "id": "extension/event",
                "model_component_id": "pipe-01",
                "profile": "TNO_PIPE",
                "release": {"mode": "hole"},
            },
        ],
        "cases": [],
        "risk_atoms": [],
    }


def _base():
    return {
        "event_rows": [{
            "event_id": "base/event",
            "component_id": "tank-01",
            "operating_mode": "receiving",
            "hazop_scenario_id": "tank-receiving",
            "release_mode": "hole",
        }]
    }


def _extension():
    return {
        "bindings": [{
            "event_id": "old-prefix/extension/event",
            "component_id": "pipe-01",
            "operating_mode": "supply",
            "hazop_scenario_id": "pipe-supply",
            "release_mode": "hole",
        }]
    }


def test_merge_normalizes_explicit_ids_and_returns_canonical_audit():
    report = merge_hazop_event_mode_bindings(
        _campaign(),
        _base(),
        _extension(),
        event_id_replacements=(("old-prefix/", ""),),
    )
    assert report["schema_version"] == "prism.hazop_event_mode_binding_audit.v1"
    assert report["status"] == "HAZOP_EVENT_MODE_BINDING_COMPLETE"
    assert report["event_count"] == 2
    assert report["mode_bound_event_count"] == 2
    assert len(report["event_rows"]) == 2
    assert report["policy"]["mode_inference_performed"] is False
    assert report["merge"]["extension_event_count"] == 1


def test_merge_rejects_duplicate_after_normalization():
    duplicate = {
        "bindings": [{
            "event_id": "base/event",
            "component_id": "tank-01",
            "operating_mode": "standby",
            "hazop_scenario_id": "conflict",
            "release_mode": "hole",
        }]
    }
    with pytest.raises(ValueError, match="duplicate explicit HAZOP event binding"):
        merge_hazop_event_mode_bindings(_campaign(), _base(), duplicate)


def test_merge_can_explicitly_keep_base_when_extension_export_contains_copy():
    extension = {
        "bindings": [
            _base()["event_rows"][0],
            _extension()["bindings"][0],
        ]
    }
    report = merge_hazop_event_mode_bindings(
        _campaign(),
        _base(),
        extension,
        event_id_replacements=(("old-prefix/", ""),),
        overlap_policy="base_wins",
    )
    assert report["event_count"] == 2
    assert report["merge"]["skipped_extension_overlap_count"] == 1


def test_base_wins_still_rejects_conflicting_overlap_identity():
    conflict = {
        "bindings": [{
            "event_id": "base/event",
            "component_id": "other-component",
            "operating_mode": "receiving",
            "hazop_scenario_id": "tank-receiving",
            "release_mode": "hole",
        }]
    }
    with pytest.raises(ValueError, match="conflicts with base identity"):
        merge_hazop_event_mode_bindings(
            _campaign(), _base(), conflict, overlap_policy="base_wins"
        )
