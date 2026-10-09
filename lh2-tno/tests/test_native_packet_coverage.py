import json

from lh2_tno.native_packet_coverage import build_native_packet_coverage_ledger


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_native_packet_coverage_keeps_packet_and_chain_evidence_separate(tmp_path):
    root = tmp_path / "repo"
    packet = root / "results" / "packet"
    event_id = "facility/pipe/AREA_100%"
    release = {
        "provider_export_schema": "prism.resolved_release.v1",
        "event_id": event_id,
        "component_id": "pipe-01",
        "port_id": "out",
        "event_kind": "accidental_leak",
        "phase_basis": "two_phase",
        "failure_opening_diameter_m": 0.025,
        "duration_s": 0.2,
        "available_mass_kg": 1.0,
        "cumulative_mass_out_kg": 0.4,
        "integrated_mass_kg": 0.4,
        "termination_basis": "model_pressure_equalization",
        "termination_provenance": "native model",
    }
    _write(packet / "provider_response.json", {
        "provider_export_schema": "prism.external_accident_history.v1",
        "provider_model": "lh2dt.DynamicHEMPipe",
        "data": {"event_id": event_id},
    })
    _write(packet / "resolved_release.json", release)
    _write(packet / "verification.json", {
        "status": "END_TO_END_DIAGNOSTIC_EXECUTED",
        "provider_packet_promoted": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "consequence_chain_executed": True,
    })
    chain = root / "results" / "packet_chain"
    _write(chain / "verification.json", {"status": "END_TO_END_DIAGNOSTIC_EXECUTED"})
    _write(chain / "request.json", {"resolved_release": release})

    ledger = build_native_packet_coverage_ledger(
        root,
        [packet],
        {"work_items": [{"event_id": event_id}]},
    )

    assert ledger["status"] == "PARTIAL_NATIVE_DIAGNOSTIC_EVIDENCE"
    assert ledger["packet_count"] == 1
    assert ledger["exact_worklist_event_count"] == 1
    assert ledger["consequence_chain_event_count"] == 1
    assert ledger["rows"][0]["mass_residual_kg"] == 0.0
    assert ledger["policy"]["provider_packet_promoted"] is False
