import os
import subprocess
import sys
from pathlib import Path


WORKER_ROOT = Path("/workspace/apps/worker")
FAKE_WORKER = Path("/workspace/tests/integration/fake_worker.py")


def run_fake_worker(
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Claim and process exactly one queued job with deterministic worker fakes."""
    return subprocess.run(
        [sys.executable, str(FAKE_WORKER)],
        cwd=WORKER_ROOT,
        env={**os.environ, **(env or {})},
        check=check,
        capture_output=True,
        text=True,
    )
