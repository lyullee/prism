from lh2_tno.realtime_mode_trace import audit_realtime_hazop_mode_trace


def _single(mode="receiving"):
    return {
        "component_id": "TK-01",
        "telemetry_boundary": {"operating_mode": mode},
        "equipment_release_path": {"operating_mode": mode},
    }


def test_realtime_mode_trace_accepts_single_monitor_result():
    report = audit_realtime_hazop_mode_trace(_single())
    assert report["status"] == "REALTIME_HAZOP_MODE_TRACE_VERIFIED"
    assert report["operating_mode_counts"] == {"receiving": 1}
    assert report["policy"]["frequency_inference_performed"] is False


def test_realtime_mode_trace_accepts_facility_batch_accounting():
    result = {
        "components": {
            "TK-01": {
                "status": "ACCEPTED",
                "result": {"telemetry_boundary": {"operating_mode": "receiving"}},
                "equipment_release_path": {"operating_mode": "receiving"},
            },
            "PV-01": {
                "status": "ACCEPTED",
                "result": {"telemetry_boundary": {"operating_mode": "supply"}},
                "equipment_release_path": {"operating_mode": "supply"},
            },
        },
        "aggregate": {
            "equipment_release_path_accounting": {
                "component_rows": {
                    "TK-01": {"operating_mode": "receiving"},
                    "PV-01": {"operating_mode": "supply"},
                },
                "operating_mode_counts": {"receiving": 1, "supply": 1},
            }
        },
    }
    report = audit_realtime_hazop_mode_trace(result)
    assert report["status"] == "REALTIME_HAZOP_MODE_TRACE_VERIFIED"
    assert report["facility_batch_accounting_present"] is True


def test_realtime_mode_trace_rejects_mismatch():
    report = audit_realtime_hazop_mode_trace({
        "component_id": "TK-01",
        "telemetry_boundary": {"operating_mode": "receiving"},
        "equipment_release_path": {"operating_mode": "supply"},
    })
    assert report["status"] == "REALTIME_HAZOP_MODE_TRACE_BLOCKED"
    assert any("differ" in reason for reason in report["blocking_reasons"])
