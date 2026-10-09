from lh2_tno.domain_recovery_audit import build_domain_recovery_audit


def _defaults(downwind):
    return {
        "domain": {
            "downwind_bounds_m": [-2.0, downwind],
            "crosswind_bounds_m": [-10.0, 10.0],
            "height_bounds_m": [0.0, 12.0],
            "cell_size_m": 0.5,
        }
    }


def _campaign(statuses):
    return {
        "status": "PARTIAL_DECLARED_SCOPE",
        "campaign_digest": "digest",
        "cases": [
            {"event_id": event_id, "status": status}
            for event_id, status in statuses.items()
        ],
        "uncomputed_cases": [],
    }


def test_persistent_domain_blocker_is_preserved_and_not_promoted():
    report = build_domain_recovery_audit(
        _campaign({"e1": "EXECUTED_DOMAIN_INCOMPLETE", "e2": "EXECUTED"}),
        _campaign({"e1": "EXECUTED_DOMAIN_INCOMPLETE", "e2": "EXECUTED"}),
        _defaults(80.0),
        _defaults(160.0),
    )
    assert report["status"] == "DOMAIN_RECOVERY_REVIEWED"
    assert report["recovery_domain_incomplete_event_count"] == 1
    assert report["persistent_domain_incomplete_event_ids"] == ["e1"]
    assert report["facility_ir_fn_promotion"] is False


def test_recovered_event_is_reported_separately():
    report = build_domain_recovery_audit(
        _campaign({"e1": "EXECUTED_DOMAIN_INCOMPLETE"}),
        _campaign({"e1": "EXECUTED_OPERATOR_LIMITED"}),
        _defaults(80.0),
        _defaults(160.0),
    )
    assert report["recovered_event_ids"] == ["e1"]
    assert report["counts"]["RECOVERED_BY_EXPLICIT_DOMAIN_RUN"] == 1
