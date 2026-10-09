from pathlib import Path

from lh2_tno.engineering_document_evidence import (
    audit_root,
    classify_document,
    public_summary,
)


def test_document_classes_are_generic_and_do_not_create_packets():
    assert classify_document("P&ID/2톤 저장탱크_P&ID.pdf")["document_class"] == "pid_topology_candidate"
    assert classify_document("비상대응절차서.pdf")["document_class"] == "emergency_procedure_candidate"
    assert classify_document("하역 운전절차서.pdf")["document_class"] == "operating_procedure_candidate"
    assert classify_document("unknown.pdf")["document_class"] == "unclassified_document"


def test_audit_is_metadata_only_and_public_summary_hides_absolute_path(tmp_path: Path):
    (tmp_path / "2톤 저장탱크_P&ID.pdf").write_bytes(b"not a real pdf")
    report = audit_root(tmp_path)
    assert report["status"] == "ENGINEERING_DOCUMENT_SCREENING_ONLY"
    assert report["aggregate"]["accident_release_packet_count"] == 0
    assert report["promotion_gates"]["state_snapshot_binding_allowed"] is False
    summary = public_summary(report)
    assert summary["source_root"] == "<engineering-document-root>"
    assert str(tmp_path) not in str(summary)
    assert summary["files"][0]["raw_text_copied"] is False
