"""Exercise the Linux loader boundary that selects cuDNN's split libraries."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_entrypoint_preserves_override_arguments_stdin_and_exit_status() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "src.runtime", sys.executable, "-c",
         "import sys; print(sys.argv[1]); print(sys.stdin.read()); sys.exit(7)",
         "an argument with spaces"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "apps/worker")},
        input="smoke input", text=True, capture_output=True,
    )
    assert result.returncode == 7
    assert result.stdout.splitlines() == ["an argument with spaces", "smoke input"]


@pytest.mark.skipif(sys.platform != "linux" or shutil.which("cc") is None,
                    reason="Requires Linux's dynamic loader and a C compiler")
def test_container_entrypoint_prefers_wheel_cudnn_before_child_starts(tmp_path: Path) -> None:
    old = tmp_path / "system"
    wheel = tmp_path / "site-packages"
    bundled = wheel / "nvidia" / "cudnn" / "lib"
    for directory, version in ((old, 90100), (bundled, 92400)):
        directory.mkdir(parents=True)
        source = directory / "version.c"
        source.write_text(f"unsigned long cudnnGetVersion(void) {{ return {version}; }}\n")
        subprocess.run([
            "cc", "-shared", "-fPIC", str(source),
            "-Wl,-soname,libcudnn_graph.so.9", "-o", str(directory / "libcudnn_graph.so.9"),
        ], check=True)

    entrypoint = []
    for line in (ROOT / "apps/worker/Dockerfile").read_text().splitlines():
        if line.startswith("ENTRYPOINT "):
            entrypoint = json.loads(line.removeprefix("ENTRYPOINT "))
    code = (
        "import ctypes, os; "
        "library = ctypes.CDLL('libcudnn_graph.so.9'); "
        "print(library.cudnnGetVersion()); "
        "print(os.environ['LD_LIBRARY_PATH'])"
    )
    child = subprocess.run(
        [*entrypoint, sys.executable, "-c", code],
        env={**os.environ, "PYTHONPATH": f"{wheel}:{ROOT / 'apps/worker'}",
             "LD_LIBRARY_PATH": str(old)},
        capture_output=True, text=True, check=True,
    )
    lines = child.stdout.splitlines()
    assert lines[0] == "92400", f"Loaded system cuDNN 9.1 instead of bundled 9.24: {child.stdout}"
    assert lines[1].split(":") == [str(bundled), str(old)]
