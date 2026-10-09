import json

from lh2_tno.provider_worklist_evidence import build_provider_worklist_packet_evidence


def _worklist(required_opening=0.01):
    return {
        "work_items": [{
            "id": "scope/pipe/G1/provider-release",
            "event_id": "scope/pipe/G1",
            "component_id": "pipe-01",
            "accident_port_ids": ["pipe-out"],
            "required_opening_diameter_m": required_opening,
        }],
    }


def _write_packet(
    root,
    *,
    opening=0.01,
    event_id="scope/pipe/G1",
    component_id="pipe-01",
    with_sidecars=False,
):
    directory = root / "pipe_case"
    directory.mkdir()
    data = {
        "event_kind": "accidental_leak",
        "event_id": event_id,
        "component_id": component_id,
        "port_id": "pipe-out",
        "duration_s": 0.2,
        "available_mass_kg": 1.0,
        "cumulative_mass_out_kg": 0.1,
        "termination_provenance": "explicit provider termination",
        "termination_basis": "synthetic_diagnostic_horizon",
        "property_basis": {"fluid": "Hydrogen"},
        "provider_source_digest": "a" * 64,
        "provider_result_digest": "b" * 64,
        "failure_opening_diameter_m": opening,
        "steps": [{"time_s": 0.0, "mass_flow_kg_s": 0.5}],
    }
    (directory / "provider_response.json").write_text(
        json.dumps({
            "provider_export_schema": "prism.external_accident_history.v1",
            "provider_model": "synthetic-provider",
            "data": data,
        }),
        encoding="utf-8",
    )
    resolved = dict(data)
    resolved["provider_export_schema"] = "prism.resolved_release.v1"
    (directory / "resolved_release.json").write_text(json.dumps(resolved), encoding="utf-8")
    (directory / "verification.json").write_text(json.dumps({
        "status": "EXTERNAL_PROVIDER_EXECUTED_OPERATOR_LIMITED",
        "provider_packet_promoted": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
    }), encoding="utf-8")
    if with_sidecars:
        (directory / "provider_qualification.json").write_text(json.dumps({
            "schema_version": "prism.provider_qualification_evidence.v1",
            "status": "qualified_actual",
            "provider_origin": "reviewed_actual",
            "evidence_id": "provider-evidence-001",
            "event_id": event_id,
            "component_id": component_id,
            "port_ids": ["pipe-out"],
            "provider_source_digests": ["a" * 64],
            "provider_result_digests": ["b" * 64],
        }), encoding="utf-8")
        (directory / "physical_validation.json").write_text(json.dumps({
            "status": "independent_validated",
            "evidence_id": "validation-001",
            "evidence_digest": "c" * 64,
        }), encoding="utf-8")
    chain = root / "pipe_case_chain"
    chain.mkdir()
    (chain / "verification.json").write_text(
        json.dumps({"status": "END_TO_END_DIAGNOSTIC_EXECUTED"}), encoding="utf-8"
    )
    (chain / "request.json").write_text(
        json.dumps({"resolved_release": resolved}), encoding="utf-8"
    )


def test_worklist_evidence_exact_matches_strict_packet_and_chain(tmp_path):
    _write_packet(tmp_path)
    report = build_provider_worklist_packet_evidence(_worklist(), tmp_path)
    assert report["status"] == "PARTIAL_DIAGNOSTIC_EVIDENCE"
    assert report["worklist_event_count"] == 1
    assert report["candidate_event_count"] == 1
    assert report["exact_match_event_count"] == 1
    assert report["strict_packet_valid_event_count"] == 1
    assert report["consequence_chain_event_count"] == 1
    assert report["qualified_provider_packet_count"] == 0
    assert report["frequency_bound"] is False
    readiness = report["rows"][0]["evidence"]["qualification_readiness"]
    assert readiness["status"] == "BLOCKED_REVIEW"
    assert "qualification_sidecar_missing" in readiness["blockers"]
    assert "operator_limited_input" in readiness["blockers"]
    assert report["qualification_readiness"]["blocker_counts"]["physical_validation_evidence_missing"] == 1


def test_worklist_evidence_rejects_opening_mismatch(tmp_path):
    _write_packet(tmp_path, opening=0.02)
    report = build_provider_worklist_packet_evidence(_worklist(), tmp_path)
    assert report["candidate_event_count"] == 1
    assert report["exact_match_event_count"] == 0
    assert report["rows"][0]["status"] == "PROVIDER_PACKET_CANDIDATE_REJECTED"


def test_worklist_evidence_keeps_missing_events_uncomputed(tmp_path):
    _write_packet(tmp_path)
    report = build_provider_worklist_packet_evidence(
        {
            "work_items": _worklist()["work_items"] + [{
                "id": "scope/missing/G1/provider-release",
                "event_id": "scope/missing/G1",
                "component_id": "missing-01",
                "accident_port_ids": ["missing-out"],
                "required_opening_diameter_m": 0.01,
            }]
        },
        tmp_path,
    )
    assert report["worklist_event_count"] == 2
    assert report["candidate_event_count"] == 1
    assert report["rows"][1]["status"] == "UNCOMPUTED_PROVIDER_PACKET"


def test_worklist_evidence_recognizes_exact_qualification_and_validation_sidecars(tmp_path):
    _write_packet(tmp_path, with_sidecars=True)
    report = build_provider_worklist_packet_evidence(_worklist(), tmp_path)
    readiness = report["rows"][0]["evidence"]["qualification_readiness"]
    assert readiness["qualification_sidecar_present"] is True
    assert readiness["physical_validation_evidence_present"] is True
    assert "qualification_sidecar_missing" not in readiness["blockers"]
    assert "physical_validation_evidence_missing" not in readiness["blockers"]
    assert report["qualification_readiness"]["qualification_sidecar_present_count"] == 1
    assert report["qualification_readiness"]["physical_validation_evidence_present_count"] == 1
    assert readiness["qualification_sidecar_path"].endswith("provider_qualification.json")
    assert readiness["physical_validation_evidence_path"].endswith("physical_validation.json")


def test_worklist_evidence_keeps_mismatched_sidecar_blocked(tmp_path):
    _write_packet(tmp_path, with_sidecars=True)
    sidecar = tmp_path / "pipe_case" / "provider_qualification.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["provider_result_digests"] = ["d" * 64]
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    report = build_provider_worklist_packet_evidence(_worklist(), tmp_path)
    readiness = report["rows"][0]["evidence"]["qualification_readiness"]
    assert readiness["qualification_sidecar_present"] is False
    assert "qualification_sidecar_digest_mismatch" in readiness["blockers"]
    assert readiness["physical_validation_evidence_present"] is True
