from __future__ import annotations

import json
from pathlib import Path

from scripts.run_native_external_equipment_recheck import (
    exporter_commands,
    summarise_packet,
    tree_digest,
)
from scripts.run_native_external_equipment_chain_recheck import chain_commands


def test_exporter_commands_cover_all_declared_native_equipment() -> None:
    commands = exporter_commands(Path("external-root"), Path("out"))
    assert set(commands) == {
        "layered_tank",
        "dynamic_pipe",
        "stroke_limited_valve",
        "mapped_pump",
        "dynamic_vaporizer",
        "dynamic_reliquefier",
        "vent_stack",
    }
    assert all("--lh2dt-root" in command for command in commands.values())
    assert "--compressible-handoff" in commands["stroke_limited_valve"]
    assert "--post-isolation-observation-s" in commands["mapped_pump"]


def test_tree_digest_is_stable_and_ignores_cache(tmp_path: Path) -> None:
    root = tmp_path / "external"
    (root / "lh2dt").mkdir(parents=True)
    (root / "lh2dt" / "model.py").write_text("value = 1\n", encoding="utf-8")
    (root / "lh2dt" / "__pycache__").mkdir()
    (root / "lh2dt" / "__pycache__" / "model.pyc").write_bytes(b"cache")
    first = tree_digest(root)
    (root / "lh2dt" / "__pycache__" / "other.py").write_text("cache", encoding="utf-8")
    assert tree_digest(root) == first
    (root / "lh2dt" / "model.py").write_text("value = 2\n", encoding="utf-8")
    assert tree_digest(root) != first


def test_summarise_packet_preserves_diagnostic_gate(tmp_path: Path) -> None:
    packet_dir = tmp_path / "packet"
    packet_dir.mkdir()
    (packet_dir / "verification.json").write_text(
        json.dumps({
            "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
            "provider_model": "lh2dt.LayeredTank",
            "provider_source_digest": "source",
            "provider_result_digest": "result",
            "termination_basis": "reviewed_isolation_success",
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
            "state_snapshot_digest_match": True,
        }),
        encoding="utf-8",
    )
    summary = summarise_packet("tank", packet_dir, ["python", "export.py"], exit_code=0, stdout="ok")
    assert summary["verification_present"] is True
    assert summary["provider_packet_promoted"] is False
    assert summary["termination_basis"] == "reviewed_isolation_success"
    assert summary["state_snapshot_digest_match"] is True


def test_chain_commands_keep_high_speed_valve_on_compressible_path() -> None:
    commands = chain_commands(
        Path("packets"),
        Path("chains"),
        backend_config=Path("backend.json"),
        facility=Path("facility.json"),
        context=Path("context.json"),
    )
    assert set(commands) == {
        "tank", "pipe", "pump", "vaporizer", "reliquefier", "vent", "valve_compressible",
    }
    assert "run_compressible_plane_chain.py" in commands["valve_compressible"][1]
    assert "--handoff" in commands["valve_compressible"]
    assert "validate_lh2dt_prism_packet_chain.py" in commands["tank"][1]
