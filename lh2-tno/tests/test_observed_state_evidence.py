import pytest

from lh2_tno.observed_state_evidence import build_observed_state_evidence


def _source():
    return {
        "source_id": "historian-tank-01",
        "source_path": "external://center/tank.csv",
        "source_sha256": "a" * 64,
        "format": "csv",
        "component_id": "tank-01",
        "origin": "historian_measured",
        "samples": [
            {
                "captured_at_s": 0,
                "values": {
                    "pressure": {"value_si": 250000.0, "sensor_location": "PT-01"},
                    "temperature": {"value_si": 23.15, "sensor_location": "TT-01"},
                },
            },
            {
                "captured_at_s": 1,
                "values": {
                    "pressure": {"value_si": 251000.0, "sensor_location": "PT-01"},
                    "temperature": {"value_si": 23.25, "sensor_location": "TT-01"},
                },
            },
        ],
    }


def test_observed_state_evidence_is_state_only_and_summarized():
    report = build_observed_state_evidence([_source()])
    assert report["schema_version"] == "prism.observed_equipment_state_evidence.v1"
    assert report["status"] == "OBSERVATION_STATE_EVIDENCE_ONLY"
    assert report["source_count"] == 1
    assert report["sample_count"] == 2
    assert report["component_count"] == 1
    assert report["policy"]["release_scenario_generated"] is False
    assert report["policy"]["frequency_inference_performed"] is False
    assert report["policy"]["provider_packet_promoted"] is False
    summary = report["component_rows"][0]
    assert summary["component_id"] == "tank-01"
    assert summary["quantity_statistics"]["pressure"]["count"] == 2


def test_observed_state_evidence_rejects_accident_owned_fields():
    source = _source()
    source["samples"][0]["annual_frequency_per_year"] = 1e-4
    with pytest.raises(ValueError, match="accident-owned"):
        build_observed_state_evidence([source])


def test_observed_state_evidence_requires_si_positive_temperature_and_pressure():
    source = _source()
    source["samples"][0]["values"]["temperature"]["value_si"] = -1.0
    with pytest.raises(ValueError, match="temperature"):
        build_observed_state_evidence([source])
