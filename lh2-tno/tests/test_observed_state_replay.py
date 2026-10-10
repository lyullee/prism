from pathlib import Path

from lh2_tno.observed_state_evidence import build_observed_state_evidence
from lh2_tno.observed_state_replay import audit_observed_state_replay


def _source(path: str, digest: str):
    return {
        "source_id": "historian-tank-01",
        "path": path,
        "source_path": path,
        "source_sha256": digest,
        "format": "csv",
        "component_id": "tank-01",
        "origin": "historian_measured",
        "signal_map": {"pressure": {"column": "PT-01", "unit": "Pa"}},
        "samples": [
            {"captured_at_s": 0.0, "values": {"pressure": {"value_si": 250000.0}}},
            {"captured_at_s": 1.0, "values": {"pressure": {"value_si": 251000.0}}},
        ],
    }


def _manifest(path: str):
    return {
        "schema_version": "prism.observed_state_input_manifest.v1",
        "source_root": ".",
        "sources": [
            {
                "source_id": "historian-tank-01",
                "path": path,
                "component_id": "tank-01",
                "origin": "historian_measured",
            }
        ],
    }


def test_observed_state_replay_matches_hash_and_regeneration(tmp_path: Path):
    source_path = tmp_path / "tank.csv"
    source_path.write_text("PT-01\n250000\n", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    source = _source("tank.csv", digest)
    evidence = build_observed_state_evidence([source])
    report = audit_observed_state_replay(
        _manifest("tank.csv"),
        evidence,
        regenerated_evidence=evidence,
        source_root=tmp_path,
    )
    assert report["status"] == "SOURCE_REPLAY_MATCHED"
    assert report["matched_source_count"] == 1
    assert report["regeneration"]["canonical_digest_match"] is True


def test_observed_state_replay_blocks_changed_source(tmp_path: Path):
    source_path = tmp_path / "tank.csv"
    source_path.write_text("PT-01\n250001\n", encoding="utf-8")
    source = _source("tank.csv", "a" * 64)
    evidence = build_observed_state_evidence([source])
    report = audit_observed_state_replay(
        _manifest("tank.csv"), evidence, source_root=tmp_path
    )
    assert report["status"] == "SOURCE_REPLAY_BLOCKED"
    assert any("SHA-256" in item for item in report["blocking_reasons"])
