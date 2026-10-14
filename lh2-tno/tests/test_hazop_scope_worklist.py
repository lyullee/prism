import json
from pathlib import Path

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan
from lh2_tno.hazop_scope_worklist import build_hazop_scope_worklist
from lh2_tno.provider_worklist import build_provider_release_worklist


def _inputs():
    root = Path(__file__).parents[1]
    manifest = EquipmentManifest.from_json(root / "examples" / "generic_lh2_full_scope_manifest.json")
    plan = FrequencyPlan.model_validate_json(
        (root / "examples" / "generic_lh2_full_scope_frequency_plan.json").read_text(encoding="utf-8")
    )
    scope = json.loads(
        (root / "examples" / "hazop_multiequipment_provider_isolation_execution_20261014.json").read_text(
            encoding="utf-8"
        )
    )
    provider = build_provider_release_worklist(manifest, plan)
    return manifest, scope["scope_catalog"], provider, scope


def test_scope_worklist_keeps_diagnostic_dispatch_separate_from_provider_packets():
    manifest, scope_catalog, provider, diagnostic = _inputs()
    report = build_hazop_scope_worklist(
        manifest,
        scope_catalog,
        provider,
        runtime=diagnostic,
    )

    assert report["schema"] == "prism.hazop_scope_worklist.v1"
    assert report["status"] == "SCOPE_GAPS_EXPLICIT"
    assert report["summary"] == {
        "family_component_row_count": 31,
        "dispatched_diagnostic_component_count": 7,
        "applicable_not_dispatched_component_count": 9,
        "no_frequency_binding_component_count": 15,
        "provider_event_count": 24,
        "provider_uncomputed_event_count": 24,
        "frequency_inference_performed": False,
        "packet_substitution_performed": False,
    }
    pipe = next(
        row for row in report["family_component_rows"]
        if row["family"] == "pipe_hole" and row["component_id"] == "liquid-transfer-line-01"
    )
    assert pipe["scope_status"] == "DISPATCHED_DIAGNOSTIC"
    assert pipe["provider_event_count"] == 5
    assert pipe["provider_uncomputed_event_count"] == 5
    assert report["policy"]["diagnostic_dispatch_does_not_promote_provider_packet"] is True

    vertical = [row for row in report["family_component_rows"] if row["family"] == "vertical_handoff"]
    assert len(vertical) == 3
    assert all(row["scope_status"] == "NO_FREQUENCY_EVENT_BINDING" for row in vertical)
    assert all(
        any("no exact initiating-frequency event" in reason for reason in row["blocking_reasons"])
        for row in vertical
    )


def test_scope_worklist_does_not_allow_observed_component_outside_family_applicability():
    manifest, scope_catalog, provider, _ = _inputs()
    altered = json.loads(json.dumps(scope_catalog))
    next(row for row in altered["rows"] if row["family"] == "pipe_hole")["observed_component_ids"] = [
        "storage-tank-01"
    ]

    try:
        build_hazop_scope_worklist(manifest, altered, provider)
    except ValueError as error:
        assert "non-applicable component" in str(error)
    else:
        raise AssertionError("invalid family/component dispatch must fail closed")


def test_scope_worklist_requires_all_declared_family_rows():
    manifest, scope_catalog, provider, _ = _inputs()
    altered = json.loads(json.dumps(scope_catalog))
    altered["rows"] = [row for row in altered["rows"] if row["family"] != "vertical_handoff"]

    try:
        build_hazop_scope_worklist(manifest, altered, provider)
    except ValueError as error:
        assert "missing family row" in str(error)
    else:
        raise AssertionError("missing family row must fail closed")

