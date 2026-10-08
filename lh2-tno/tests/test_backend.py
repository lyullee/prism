from pathlib import Path
import sys
import pytest
from lh2_tno.backend import BackendConfig, BackendError, IsolatedBackend, PackagePin, tree_digest


def test_changed_code_is_detected_before_execution(tmp_path):
    (tmp_path/"module.py").write_text("x=1\n")
    b=IsolatedBackend(BackendConfig(interpreter=sys.executable,packages=(PackagePin(name="demo",root=str(tmp_path),sha256=tree_digest(tmp_path)),)))
    (tmp_path/"module.py").write_text("x=2\n")
    with pytest.raises(BackendError,match="revision mismatch"):b.run("assurance",{})


def test_worker_failure_has_no_numeric_result(tmp_path):
    (tmp_path/"module.py").write_text("x=1\n")
    b=IsolatedBackend(BackendConfig(interpreter=sys.executable,packages=(PackagePin(name="demo",root=str(tmp_path),sha256=tree_digest(tmp_path)),)))
    with pytest.raises(BackendError):b.run("integrated_source",{})
