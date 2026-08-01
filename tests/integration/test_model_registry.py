import importlib
import sys
import types
from pathlib import Path

import pytest


WORKER_ROOT = Path(__file__).parents[2] / "apps" / "worker"


@pytest.fixture
def model_registry_modules():
    """Load worker modules without leaking their shared ``src`` name to API tests."""
    saved_modules = {
        name: module for name, module in sys.modules.items()
        if name == "src" or name.startswith("src.")
    }
    for name in saved_modules:
        del sys.modules[name]
    sys.path.insert(0, str(WORKER_ROOT))
    try:
        yield (
            importlib.import_module("src.config").Settings,
            importlib.import_module("src.model_registry"),
        )
    finally:
        sys.path.remove(str(WORKER_ROOT))
        for name in tuple(sys.modules):
            if name == "src" or name.startswith("src."):
                del sys.modules[name]
        sys.modules.update(saved_modules)


def settings_for(settings_type, model_root: Path):
    return settings_type(
        database_url="postgresql://unused",
        data_root=model_root / "data",
        model_root=model_root,
        whisper_model="unused",
        worker_id="test-worker",
        poll_interval_seconds=1,
        max_attempts=1,
        diarization_model_revision="pinned-revision",
    )


def test_validation_rejects_model_directory_without_pipeline_config(
    tmp_path: Path, model_registry_modules,
) -> None:
    settings_type, registry = model_registry_modules
    settings = settings_for(settings_type, tmp_path)
    model_path = tmp_path / "diarization" / "pinned-revision"
    model_path.mkdir(parents=True)
    (model_path / "partial-download").touch()

    with pytest.raises(RuntimeError, match="incomplete: missing .*config.yaml"):
        registry.validate_pinned_model(settings)


def test_download_resumes_partial_model_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_registry_modules,
) -> None:
    settings_type, registry = model_registry_modules
    settings = settings_for(settings_type, tmp_path)
    model_path = tmp_path / "diarization" / "pinned-revision"
    model_path.mkdir(parents=True)
    (model_path / "partial-download").touch()
    calls: list[dict] = []

    def snapshot_download(**kwargs):
        calls.append(kwargs)
        (Path(kwargs["local_dir"]) / "config.yaml").write_text("pipeline: {}\n")

    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(snapshot_download=snapshot_download))

    assert registry.download_pinned_model(settings) == model_path
    assert calls == [{
        "repo_id": settings.diarization_model,
        "revision": "pinned-revision",
        "local_dir": str(model_path),
        "token": None,
    }]
