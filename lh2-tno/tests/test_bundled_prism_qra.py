import csv
import json
from pathlib import Path

import prism_cli as tno_host


def test_bundled_standard_qra_generates_and_reads_templates(tmp_path):
    template_dir = tmp_path / "inputs"
    assert tno_host.main([
        "--mode", "standard", "template", "--directory", str(template_dir)
    ]) == 0
    # The generated footer contains explanatory comments, which the public
    # engine must ignore when it reads the edited CSV files.
    sections = template_dir / "sections.csv"
    rows = list(csv.DictReader(
        line for line in sections.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ))
    assert rows and rows[0]["section_id"] == "LH2_TANK"
    result = tmp_path / "standard_result.json"
    assert tno_host.main([
        "--mode", "standard", "run", "--name", "demo",
        "--sections", str(template_dir / "sections.csv"),
        "--components", str(template_dir / "components.csv"),
        "--assemblies", str(template_dir / "assemblies.csv"),
        "--ignition", "purple", "--blocking", "none", "--samples", "0",
        "--extent", "100", "--cell", "25", "--out", str(result),
    ]) == 0
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["execution_mode"] == "standard"
    assert payload["mode_dispatch"]["engine"] == "bundled_prism_qra"
