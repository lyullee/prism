from pathlib import Path

from lh2_tno.slabx_lh2_source_validation_gate_audit import (
    audit_slabx_lh2_source_validation_gates,
)


def test_gate_audit_keeps_restricted_source_evidence_closed(tmp_path: Path):
    gates = tmp_path / "gates.csv"
    gates.write_text(
        "gate,operator,status,result,source\n"
        "A,mass flux,implemented_existing_provenance_fixture,fixture,nasa.csv\n"
        "B,flow,published_validation_envelope_only,envelope,preslhy.pdf\n"
        "F,numerics,automated,tests,pytest\n",
        encoding="utf-8",
    )
    casewise = tmp_path / "casewise.csv"
    casewise.write_text(
        "case,mass_residual_kg_s,energy_residual_w\n"
        "A,0,0\n"
        "B,1e-12,1e-9\n",
        encoding="utf-8",
    )
    report = audit_slabx_lh2_source_validation_gates(gates, casewise_path=casewise)
    assert report["status"] == "RESTRICTED_SOURCE_VALIDATION_GATES"
    assert report["gate_count"] == 3
    assert report["independent_quantitative_gate_count"] == 0
    assert report["casewise_numerical_closure"]["mass_closed_row_count"] == 2
    assert report["promotion_gates"]["full_chain_physical_validation_allowed"] is False
    assert report["physical_validation_claim"] is False


def test_gate_audit_flags_explicit_independent_status(tmp_path: Path):
    gates = tmp_path / "gates.csv"
    gates.write_text(
        "gate,operator,status,result,source\n"
        "X,source,independent_quantitative_validation,claimed,source.csv\n",
        encoding="utf-8",
    )
    report = audit_slabx_lh2_source_validation_gates(gates)
    assert report["status"] == "REVIEW_REQUIRED_SOURCE_VALIDATION_GATES"
    assert report["independent_quantitative_gate_count"] == 1
    assert report["promotion_gates"]["promotion_allowed"] is False


def test_gate_audit_rejects_missing_required_columns(tmp_path: Path):
    gates = tmp_path / "gates.csv"
    gates.write_text("gate,status\nA,automated\n", encoding="utf-8")
    try:
        audit_slabx_lh2_source_validation_gates(gates)
    except ValueError as error:
        assert "missing columns" in str(error)
    else:
        raise AssertionError("missing gate columns must fail closed")
