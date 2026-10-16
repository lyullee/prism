from __future__ import annotations

import json

from lh2_tno.process_forecast import build_forecast_frames
from scripts.merge_process_forecast_frames import main


def test_merge_process_forecast_cli_writes_component_set(tmp_path, monkeypatch, capsys):
    records = []
    for component_id, mode, pressure in (
        ("intake-tank", "receiving", (0.50, 0.51)),
        ("supply-boundary", "supply", (0.60, 0.61)),
    ):
        records.append(build_forecast_frames(
            [{"pressure": pressure[0]}, {"pressure": pressure[1]}],
            facility_id="facility",
            component_id=component_id,
            operating_mode=mode,
            mapping={"PT": {"source_column": "pressure", "quantity": "pressure", "unit": "MPa"}},
            source_id=f"forecast://{component_id}",
            source_provenance="test rows",
        ))
    paths = []
    for index, record in enumerate(records):
        path = tmp_path / f"frames-{index}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        paths.append(path)
    output = tmp_path / "merged.json"
    monkeypatch.setattr(
        "sys.argv",
        ["merge_process_forecast_frames.py", "--frames", str(paths[0]), "--frames", str(paths[1]), "--output", str(output)],
    )

    assert main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "PROCESS_FORECAST_FRAME_SET_MERGED"
    assert result["component_ids"] == ["intake-tank", "supply-boundary"]
    assert len(result["frames"]) == 4
    assert json.loads(capsys.readouterr().out)["frame_count"] == 4
