from pathlib import Path

from lh2_tno.partial_boundary_evidence import (
    audit_partial_boundary_evidence,
    audit_text_anchors,
)


def test_anchor_audit_is_page_specific_and_normalizes_separators():
    rows = audit_text_anchors(
        ["pressure PT-102; PSV action", "XV203 close"],
        [
            {"page": 1, "anchor": "PT102", "kind": "pressure_trigger"},
            {"page": 2, "anchor": "XV-203", "kind": "isolation_command"},
            {"page": 1, "anchor": "missing", "kind": "other"},
        ],
    )
    assert [row["anchor_found"] for row in rows] == [True, True, False]


def test_partial_boundary_audit_withholds_all_promotion_gates(tmp_path):
    path = tmp_path / "procedure.pdf"
    path.write_bytes(b"procedure evidence")
    result = audit_partial_boundary_evidence(
        [
            {
                "document_id": "doc-1",
                "role": "procedure",
                "path": path,
                "anchors": [
                    {"page": 1, "anchor": "PSV", "kind": "pressure_trigger"},
                ],
            }
        ],
        page_loader=lambda _: ["PSV action at high pressure"],
    )
    assert result["status"] == "PARTIAL_OPERATIONAL_BOUNDARY_EVIDENCE"
    assert result["supports"]["pressure_trigger_observation"] is True
    assert result["supports"]["relief_setpoint_certified"] is False
    assert result["supports"]["provider_termination_boundary"] is False
    assert result["promotion_gates"] == {
        "provider_packet_promoted": False,
        "frequency_applied": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }


def test_missing_document_remains_fail_closed():
    result = audit_partial_boundary_evidence(
        [{"path": Path("does-not-exist.pdf"), "anchors": []}],
        page_loader=lambda _: [],
    )
    assert result["status"] == "PARTIAL_OPERATIONAL_BOUNDARY_EVIDENCE_WITH_READ_ERRORS"
    assert result["document_count"] == 0
    assert result["promotion_gates"]["provider_packet_promoted"] is False
