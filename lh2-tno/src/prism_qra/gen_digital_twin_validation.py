#!/usr/bin/env python3
"""Generate the auditable pre-commissioning digital-twin test record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import digital_twin_validation as D
import source_term
from runtime_manifest import execution_environment, source_fingerprint


ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "코드" / "digital_twin_validation_summary.json"
MARKDOWN_PATH = ROOT / "핸드오프" / "24_DIGITAL_TWIN_SYSTEM_VALIDATION.md"


def hydrogen_source_analysis(values):
    discharge = source_term.discharge(
        float(values["TANK_PRESSURE_PA"]),
        float(values["TANK_TEMPERATURE_K"]),
        "Hydrogen",
        float(values["LEAK_DIAMETER_M"]),
    )
    return {
        "quantity": "GH2 discharge rate",
        "rate_kg_s": discharge.rate_kg_s,
        "choked": discharge.choked,
        "flow_model": discharge.flow_model,
        "throat_pressure_pa": discharge.throat_pressure_pa,
    }


def new_monitor():
    return D.DigitalTwinMonitor(
        D.default_tag_specs(), hydrogen_source_analysis,
        max_frame_age_ms=1000.0,
        constraints=(D.pressure_agreement,),
        model_version="hydrogen-safety-precommissioning-v2:" + source_fingerprint()["sha256"],
    )


def performance_cases(n_frames: int = 50):
    cases = []
    for index in range(n_frames):
        source = index * 0.1
        pressure = 35.0e6 + (index % 11) * 1.0e6
        values = D.make_values(pressure_pa=pressure)
        frame = D.TelemetryFrame(
            sequence=index + 1,
            source_time_s=source,
            arrival_time_s=source + 0.025,
            values=values,
            stream_id="performance-replay",
        )
        cases.append(D.FrameExpectation(
            frame, True, D.PlantState.STANDBY,
            {tag: sample.value for tag, sample in values.items()}, None,
        ))
    return tuple(cases)


def _gates(fault_report, performance_report, deterministic):
    f = fault_report.metrics
    p = performance_report.metrics
    rows = [
        {
            "gate": "all known injected faults detected",
            "criterion": "fault_detection_rate == 1.0",
            "observed": f.fault_detection_rate,
            "pass": f.fault_detection_rate == 1.0,
        },
        {
            "gate": "no known bad frame silently accepted",
            "criterion": "false_accepts == 0",
            "observed": f.false_accepts,
            "pass": f.false_accepts == 0,
        },
        {
            "gate": "no valid frame rejected",
            "criterion": "false_rejects == 0",
            "observed": f.false_rejects,
            "pass": f.false_rejects == 0,
        },
        {
            "gate": "state and value alignment",
            "criterion": "state_alignment_ratio == 1.0",
            "observed": f.state_alignment_ratio,
            "pass": f.state_alignment_ratio == 1.0,
        },
        {
            "gate": "accepted outputs are traceable",
            "criterion": "traceability_coverage == 1.0",
            "observed": f.traceability_coverage,
            "pass": f.traceability_coverage == 1.0,
        },
        {
            "gate": "deterministic replay",
            "criterion": "accepted output hashes match on independent replay",
            "observed": deterministic,
            "pass": deterministic,
        },
        {
            "gate": "advisory event processing budget",
            "criterion": "p95 processing latency <= 5000 ms",
            "observed": p.p95_processing_latency_ms,
            "pass": p.p95_processing_latency_ms <= 5000.0,
        },
    ]
    return rows


def build_payload():
    fault_cases = D.build_virtual_commissioning_suite()
    fault_report = D.run_replay(new_monitor(), fault_cases)
    repeated_report = D.run_replay(new_monitor(), fault_cases)
    deterministic = (
        D.replay_hashes(fault_report) == D.replay_hashes(repeated_report)
    )
    performance_report = D.run_replay(new_monitor(), performance_cases())
    gates = _gates(fault_report, performance_report, deterministic)
    fault_catalog = [
        {
            "fault": case.injected_fault,
            "detected": not result.accepted,
            "reasons": list(result.reasons),
        }
        for case, result in zip(fault_cases, fault_report.results)
        if not case.expected_accept
    ]
    maturity = [
        {
            "aspect": "convergence",
            "precommissioning_evidence": (
                "transactional synthetic historian replay; state/value "
                "alignment and rejection of stale, duplicate and out-of-order frames"
            ),
            "status": "VIRTUAL_EVIDENCE_ONLY",
            "claim": "ingestion and state-alignment readiness",
            "withheld_claim": "physical-to-digital convergence",
            "commissioning_evidence_needed": (
                "read-only SCADA/historian feed, common clock and observed "
                "physical-state comparison"
            ),
        },
        {
            "aspect": "capability",
            "precommissioning_evidence": (
                "standby, filling, unloading, relief and ESD state recognition plus "
                "execution of the real-gas GH2 source model"
            ),
            "status": "PASS_PRECOMMISSIONING_GATES",
            "claim": "observe/diagnose/predictive screening functions execute",
            "withheld_claim": "field predictive accuracy",
            "commissioning_evidence_needed": (
                "blind operational or approved commissioning observations"
            ),
        },
        {
            "aspect": "integrated view",
            "precommissioning_evidence": (
                "tag schema, operational state, model version, analysis output "
                "and SHA-256 result record share one trace identifier"
            ),
            "status": "PASS_PRECOMMISSIONING_GATES",
            "claim": "tested end-to-end evidence lineage",
            "withheld_claim": "complete facility lifecycle integration",
            "commissioning_evidence_needed": (
                "approved P&ID, equipment register, cause-and-effect and maintenance links"
            ),
        },
        {
            "aspect": "time",
            "precommissioning_evidence": (
                "source, arrival and processing times; p50/p95/p99 latency; "
                "stale and reversed-clock tests"
            ),
            "status": "PASS_VIRTUAL_PROCESSING_GATE",
            "claim": "local processing performance under replay",
            "withheld_claim": "live network or SCADA latency",
            "commissioning_evidence_needed": (
                "FAT/SAT timestamps measured across the deployed interface"
            ),
        },
        {
            "aspect": "trustworthiness",
            "precommissioning_evidence": (
                "fault injection, transactional refusal, redundant-sensor check, "
                "deterministic replay and hashed provenance"
            ),
            "status": "PASS_PRECOMMISSIONING_GATES",
            "claim": "tested detection and non-propagation of the injected faults",
            "withheld_claim": "production availability or cybersecurity certification",
            "commissioning_evidence_needed": (
                "deployed access-control, outage/restart, backup and recovery tests"
            ),
        },
    ]
    return {
        "generated_by": "gen_digital_twin_validation.py",
        "source_fingerprint": source_fingerprint(),
        "execution_environment": execution_environment(),
        "standard_basis": {
            "primary": "ISO/IEC 30186:2025",
            "aspects": [
                "convergence", "capability", "integrated view", "time",
                "trustworthiness",
            ],
            "supporting": [
                "NIST IR 8356 (2025)",
                "Shao, Hightower and Schindel (2023), Manufacturing Letters 35, 24-28",
            ],
            "qualification": (
                "ISO/IEC 30186 supplies the maturity structure. The numerical "
                "gates below are project-specific intended-use requirements, "
                "not universal ISO acceptance limits."
            ),
        },
        "intended_use": (
            "read-only pre-commissioning hydrogen safety screening and equipment "
            "management support; not ESD control and not a validated absolute-risk oracle"
        ),
        "applied_case": {
            "fluid": "GH2",
            "temperature_k": 288.0,
            "pressure_range_pa": [35.0e6, 45.0e6],
            "leak_diameter_m": 0.006,
            "note": (
                "This case exercises the production source model. It is a virtual "
                "commissioning stimulus, not independent physical validation."
            ),
        },
        "fault_injection": D.report_as_dict(fault_report),
        "fault_catalog": fault_catalog,
        "performance_replay": D.report_as_dict(performance_report),
        "deterministic_replay": deterministic,
        "acceptance_gates": gates,
        "all_precommissioning_gates_pass": all(row["pass"] for row in gates),
        "maturity_evidence": maturity,
        "claim_boundary": {
            "supported": (
                "standards-aligned pre-commissioning readiness evidence for "
                "telemetry handling, state management, model execution, timing, "
                "traceability and the injected fault set"
            ),
            "not_supported": [
                "physical-to-digital convergence at the LH2 terminal",
                "field prediction accuracy or absolute facility risk",
                "live SCADA/network latency, availability or cybersecurity certification",
                "closed-loop safety control performance",
            ],
        },
    }


def _pct(value):
    return f"{100.0 * value:.1f}%"


def render_markdown(payload):
    fault = payload["fault_injection"]["metrics"]
    perf = payload["performance_replay"]["metrics"]
    lines = [
        "# 24 - Standards-aligned digital-twin system validation",
        "",
        "## Decision boundary",
        "",
        "This record applies ISO/IEC 30186:2025 as a maturity structure and",
        "NIST IR 8356 as supporting trust guidance. The acceptance limits are",
        "project-specific intended-use gates, not limits prescribed by ISO.",
        "",
        "The tested system is a **read-only pre-commissioning hydrogen safety",
        "screening and equipment-management aid**. It is not an ESD controller,",
        "an absolute-risk oracle or a field-validated physical twin.",
        "",
        "## Execution identity",
        "",
        f"Source SHA-256: {payload['source_fingerprint']['sha256']}",
        f"Environment: {payload['execution_environment']}",
        "These timings cover telemetry plus the GH2 source kernel, not the full QRA pipeline.",
        "",
        "## Executed virtual-commissioning result",
        "",
        "| quantity | result |",
        "|---|---:|",
        f"| frames | {fault['n_frames']} |",
        f"| expected-valid frames | {fault['n_expected_valid']} |",
        f"| injected fault frames | {fault['n_injected_faults']} |",
        f"| detected injected faults | {fault['detected_faults']} |",
        f"| fault detection rate | {_pct(fault['fault_detection_rate'])} |",
        f"| false accepts | {fault['false_accepts']} |",
        f"| false rejects | {fault['false_rejects']} |",
        f"| state accuracy | {_pct(fault['state_accuracy'])} |",
        f"| state/value alignment | {_pct(fault['state_alignment_ratio'])} |",
        f"| traceability coverage | {_pct(fault['traceability_coverage'])} |",
        f"| maximum observed recovery time | {fault['max_recovery_time_ms']:.3f} ms |",
        "",
        "Faults cover dropout, wrong unit, stale data, duplicate and out-of-order",
        "sequence, uncertain quality, non-finite value, redundant-sensor bias,",
        "impossible operating state, unknown tag and reversed clock. A rejected",
        "frame is transactional: it does not replace the last accepted state.",
        "",
        "## Actual processing performance under replay",
        "",
        "Fifty accepted frames exercised the same real-gas GH2 source-term",
        "implementation used by the consequence code. The controlled 25 ms",
        "source-to-ingest delay is stimulus, not a live-network measurement.",
        "",
        "| metric | result |",
        "|---|---:|",
        f"| p50 local processing | {perf['p50_processing_latency_ms']:.3f} ms |",
        f"| p95 local processing | {perf['p95_processing_latency_ms']:.3f} ms |",
        f"| p99 local processing | {perf['p99_processing_latency_ms']:.3f} ms |",
        f"| p95 controlled source-to-result | {perf['p95_end_to_end_latency_ms']:.3f} ms |",
        f"| independent replay hashes identical | {payload['deterministic_replay']} |",
        "",
        "The 5 s gate is an advisory event-processing requirement. The separate",
        "50 ms platform/interface KPI is not claimed here because no deployed",
        "SCADA or network interface is present.",
        "",
        "## Acceptance gates",
        "",
        "| gate | criterion | observed | result |",
        "|---|---|---:|---|",
    ]
    for row in payload["acceptance_gates"]:
        observed = row["observed"]
        if isinstance(observed, float):
            observed = f"{observed:.6g}"
        lines.append(
            f"| {row['gate']} | `{row['criterion']}` | {observed} | "
            f"{'PASS' if row['pass'] else 'FAIL'} |"
        )
    lines.extend([
        "",
        "## ISO/IEC 30186 evidence profile",
        "",
        "| aspect | present evidence | status | withheld claim |",
        "|---|---|---|---|",
    ])
    for row in payload["maturity_evidence"]:
        lines.append(
            f"| {row['aspect']} | {row['precommissioning_evidence']} | "
            f"{row['status']} | {row['withheld_claim']} |"
        )
    lines.extend([
        "",
        "The five aspects are deliberately not collapsed into one maturity",
        "number. Physical convergence remains unscored until a read-only",
        "historian/SCADA connection and common-clock comparison exist.",
        "",
        "## Claim now supported",
        "",
        payload["claim_boundary"]["supported"] + ".",
        "",
        "## Claims still withheld",
        "",
    ])
    for item in payload["claim_boundary"]["not_supported"]:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Commissioning continuation",
        "",
        "1. Connect the approved tag list to a read-only historian/SCADA feed.",
        "2. Repeat the same tests with synchronized acquisition, ingest, analysis",
        "   and display timestamps across the deployed interface.",
        "3. Compare physical and digital states using blind commissioning",
        "   observations and retain the present thresholds without post-hoc change.",
        "4. Run outage/restart, access-control, backup and recovery tests in the",
        "   deployed environment.",
        "5. Only then assign a physical convergence level or claim live-digital-twin",
        "   performance.",
        "",
        "## References",
        "",
        "- ISO/IEC 30186:2025, *Digital twin - Maturity model and guidance for a maturity assessment*.",
        "- NIST IR 8356 (2025), *Security and Trust Considerations for Digital Twin Technology*.",
        "- Shao, Hightower and Schindel (2023), *Credibility consideration for digital twins in manufacturing*, Manufacturing Letters 35, 24-28.",
        "",
        "The JSON beside the code contains every frame verdict, rejection reason,",
        "latency and output hash. This Markdown file is generated from that JSON",
        "and must not be edited to change a numerical result.",
        "",
    ])
    return "\n".join(lines)


def _write(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def _discrete_signature(payload):
    """Stable facts only; wall-clock timings legitimately vary by run."""
    fault = payload["fault_injection"]
    performance = payload["performance_replay"]
    fault_metrics = dict(fault["metrics"])
    performance_metrics = dict(performance["metrics"])
    for metrics in (fault_metrics, performance_metrics):
        for name in list(metrics):
            if "latency" in name or "recovery_time" in name:
                metrics.pop(name)

    def results_without_timing(rows):
        return [
            {key: value for key, value in row.items()
             if "latency" not in key}
            for row in rows
        ]

    signature = {
        "source_fingerprint": payload["source_fingerprint"],
        "standard_basis": payload["standard_basis"],
        "intended_use": payload["intended_use"],
        "applied_case": payload["applied_case"],
        "fault_metrics": fault_metrics,
        "fault_results": results_without_timing(fault["results"]),
        "fault_catalog": payload["fault_catalog"],
        "performance_metrics": performance_metrics,
        "performance_results": results_without_timing(performance["results"]),
        "deterministic_replay": payload["deterministic_replay"],
        "maturity_evidence": payload["maturity_evidence"],
        "claim_boundary": payload["claim_boundary"],
    }
    return json.loads(json.dumps(signature, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    payload = build_payload()
    if args.check:
        if not JSON_PATH.exists() or not MARKDOWN_PATH.exists():
            raise SystemExit("generated validation record is missing")
        stored = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        if _discrete_signature(stored) != _discrete_signature(payload):
            raise SystemExit("drift: discrete validation result changed")
        if MARKDOWN_PATH.read_text(encoding="utf-8") != render_markdown(stored):
            raise SystemExit("drift: Markdown does not match stored JSON")
        if not payload["all_precommissioning_gates_pass"]:
            raise SystemExit("current performance or acceptance gate failed")
        action = "checked"
    else:
        json_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        _write(JSON_PATH, json_text)
        _write(MARKDOWN_PATH, render_markdown(payload))
        action = "wrote"
    print(
        f"{action} {JSON_PATH.name} and {MARKDOWN_PATH.name}: "
        f"{payload['fault_injection']['metrics']['n_injected_faults']} faults, "
        f"all gates pass={payload['all_precommissioning_gates_pass']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
