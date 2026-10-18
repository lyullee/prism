"""Isolated, immutable FFI Test 4 SLAB replay with source-integrity checks.

Uses the reviewed external computation script, writes only a new local run
directory, then independently checks every sensor state and saved metric.
This retrospective replay is not new independent physical validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from audit_component_evidence import audit_levels, fingerprint, read_csv


def source_snapshot(root: Path) -> dict:
    paths = sorted(root.rglob("*.py"))
    if not paths or not (root / "slabx").is_dir():
        raise ValueError("explicit SLAB source root required")
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in paths if "__pycache__" not in p.parts}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"sha256": digest, "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interpreter", type=Path, required=True)
    parser.add_argument("--computation-script", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout-s", type=float, default=1800.)
    args = parser.parse_args()
    if args.timeout_s <= 0:
        raise ValueError("positive timeout required")
    for p in (args.interpreter, args.computation_script, args.observations):
        if not p.is_file():
            raise FileNotFoundError(p)
    if args.out.exists():
        raise FileExistsError("run directory already exists; never overwrite evidence")
    snapshot = source_snapshot(args.source_root.resolve())
    anchors = {"configuration": fingerprint(args.computation_script),
               "observations": fingerprint(args.observations)}
    environment = subprocess.run(
        [str(args.interpreter.resolve()), "-c",
         "import json,platform,importlib.metadata as m; "
         "print(json.dumps({'python':platform.python_version(),"
         "'numpy':m.version('numpy'),'CoolProp':m.version('CoolProp')}))"],
        capture_output=True, text=True, check=True, timeout=30)
    args.out.mkdir(parents=True)
    report = {"source_snapshot_before": snapshot, "anchors_before": anchors,
              "environment": json.loads(environment.stdout),
              "evidence_use": "retrospective-external-evaluation",
              "physical_validation_claim": False, "default_promotion_allowed": False,
              "replay_status": "running", "runner": fingerprint(Path(__file__))}
    report_path = args.out / "replay_audit.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    command = [str(args.interpreter.resolve()), str(args.computation_script.resolve()),
               "--slabx-src", str(args.source_root.resolve()),
               "--observations", str(args.observations.resolve()),
               "--out", str(args.out.resolve()), "--levels", "320", "640"]
    print("Starting fingerprinted 320/640 Test 4 replay", flush=True)
    started = time.perf_counter()
    try:
        run = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_s)
        (args.out / "computation_stdout.txt").write_text(run.stdout, encoding="utf-8")
        (args.out / "computation_stderr.txt").write_text(run.stderr, encoding="utf-8")
        report["returncode"] = run.returncode
        report["elapsed_s"] = time.perf_counter()-started
        report["source_snapshot_after"] = source_snapshot(args.source_root.resolve())
        report["anchors_after"] = {"configuration": fingerprint(args.computation_script),
                                   "observations": fingerprint(args.observations)}
        if run.returncode:
            raise RuntimeError(f"component replay failed: exit={run.returncode}")
        if (report["source_snapshot_after"] != snapshot or report["anchors_after"] != anchors):
            raise RuntimeError("source/configuration/observations changed during replay")
        audit = audit_levels(read_csv(args.out / "sensor_predictions_n320.csv"),
                             read_csv(args.out / "sensor_predictions_n640.csv"),
                             read_csv(args.out / "refinement_summary.csv"),
                             read_csv(args.observations))
        report["sensor_audit"] = audit
        if not audit["stored_refinement_gate_passed"]:
            raise RuntimeError("independent sensor-wise refinement gate failed")
        report["replay_status"] = "model-replayed-and-sensor-audited"
        report["predictions"] = fingerprint(args.out / "sensor_predictions_n640.csv")
    except Exception as exc:
        report["replay_status"] = "failed-or-withheld"
        report["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["elapsed_s"] = time.perf_counter()-started
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": report["replay_status"], "elapsed_s": report["elapsed_s"],
                      "metrics": report["sensor_audit"]["metrics"]}), flush=True)


if __name__ == "__main__":
    main()
