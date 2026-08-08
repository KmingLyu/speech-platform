import sys
from pathlib import Path

import pytest


WORKER_ROOT = Path(__file__).resolve().parents[2] / "apps" / "worker"


def test_export_failure_does_not_publish_partial_artifacts(tmp_path: Path) -> None:
    sys.path.insert(0, str(WORKER_ROOT))
    for module_name in list(sys.modules):
        if module_name == "src" or module_name.startswith("src."):
            del sys.modules[module_name]
    from src.exporter import export_result

    result_dir = tmp_path / "result"

    with pytest.raises(KeyError):
        export_result(
            "tr_export_failure",
            output_dir=result_dir,
            text="Transcript",
            language="en",
            duration=1.0,
            model="large-v3-turbo",
            segments=[{"id": 0, "start": 0.0, "end": 1.0}],
            formats=("json", "txt", "srt"),
        )

    assert not result_dir.exists()
