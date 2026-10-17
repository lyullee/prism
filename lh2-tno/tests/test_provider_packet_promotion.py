import json
from pathlib import Path

import pytest

from lh2_tno.provider_packet_promotion import (
    ProviderPacketPromotionError,
    build_provider_packet_evidence_from_records,
    load_provider_packet_evidence_catalog,
)


ROOT = Path(__file__).parents[1]


def _release() -> dict:
    catalog = json.loads(
        (ROOT / "examples" / "provider_release_catalog_synthetic.json").read_text(
            encoding="utf-8"
        )
    )
    release = dict(catalog["releases"][0])
    release["input_origin"] = "reviewed_measurement"
    return release


def _qualification(**updates: object) -> dict:
    value = {
        "schema_version": "prism.provider_qualification_evidence.v1",
        "status": "qualified_actual",
        "provider_origin": "reviewed_actual",
        "evidence_id": "lh2-provider-actual-001",
        "provider_source_digest": "0" * 64,
    }
    value.update(updates)
    return value


def test_saved_release_and_qualification_sidecar_promote_exact_identity(tmp_path):
    release_path = tmp_path / "release.json"
    qualification_path = tmp_path / "qualification.json"
    release_path.write_text(json.dumps(_release()), encoding="utf-8")
    qualification_path.write_text(json.dumps(_qualification()), encoding="utf-8")

    evidence = build_provider_packet_evidence_from_records(
        release_path, qualification_path
    )

    assert evidence.event_id == "provider-accident-01"
    assert evidence.component_id == "storage-tank-01"
    assert evidence.port_ids == ("tank-out",)
    assert evidence.provider_source_digests == ("0" * 64,)
    assert evidence.provider_result_digests == ("1" * 64,)
    assert evidence.evidence_id == "lh2-provider-actual-001"


def test_synthetic_input_origin_is_never_promoted():
    release = _release()
    release["input_origin"] = "synthetic"

    with pytest.raises(ProviderPacketPromotionError, match="synthetic"):
        build_provider_packet_evidence_from_records(release, _qualification())


def test_model_prediction_input_origin_is_never_promoted():
    release = _release()
    release["input_origin"] = "model_prediction"

    with pytest.raises(ProviderPacketPromotionError, match="reviewed_measurement"):
        build_provider_packet_evidence_from_records(release, _qualification())


def test_qualification_sidecar_must_match_source_digest():
    with pytest.raises(ProviderPacketPromotionError, match="provider_source_digest"):
        build_provider_packet_evidence_from_records(
            _release(), _qualification(provider_source_digest="2" * 64)
        )


def test_evidence_catalog_accepts_wrapped_rows_and_rejects_duplicate_events():
    evidence = build_provider_packet_evidence_from_records(_release(), _qualification())
    wrapped = {"provider_packet_evidence": [evidence.model_dump(mode="json")]}

    loaded = load_provider_packet_evidence_catalog(wrapped)

    assert loaded == (evidence,)
    with pytest.raises(ProviderPacketPromotionError, match="event_id values must be unique"):
        load_provider_packet_evidence_catalog([evidence.model_dump(mode="json")] * 2)
