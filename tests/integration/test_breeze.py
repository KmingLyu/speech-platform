import importlib
import json
import os
import sys
import types
from pathlib import Path

import httpx
import pytest

from harness import run_fake_worker


@pytest.fixture
def worker_modules():
    saved = {key: value for key, value in sys.modules.items() if key == "src" or key.startswith("src.")}
    for key in saved:
        del sys.modules[key]
    root = str(Path(__file__).parents[2] / "apps" / "worker")
    sys.path.insert(0, root)
    try:
        yield importlib.import_module("src.asr_models")
    finally:
        sys.path.remove(root)
        for key in tuple(sys.modules):
            if key == "src" or key.startswith("src."):
                del sys.modules[key]
        sys.modules.update(saved)


def install_model(registry, root: Path) -> Path:
    path = registry.breeze_model_path(root)
    path.mkdir(parents=True)
    for filename in registry.REQUIRED_FILES:
        (path / filename).write_text("{}")
    (path / "manifest.json").write_text(json.dumps(registry.MANIFEST))
    return path


def test_breeze_preparation_pins_source_and_publishes_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, worker_modules,
) -> None:
    registry = worker_modules
    calls = []

    def download(**kwargs):
        assert kwargs["repo_id"] == "MediaTek-Research/Breeze-ASR-25"
        assert kwargs["revision"] == registry.BREEZE_REVISION
        source = Path(kwargs["local_dir"])
        source.mkdir()
        (source / "README.md").write_text("Upstream model license: Apache-2.0")
        return str(source)

    class Converter:
        def __init__(self, source, **kwargs):
            assert Path(source).is_dir()
            assert kwargs["copy_files"] == ["tokenizer.json", "preprocessor_config.json"]

        def convert(self, output, **kwargs):
            assert not registry.breeze_model_path(tmp_path).exists()
            assert kwargs == {"quantization": "float16"}
            calls.append(output)
            Path(output).mkdir()
            for filename in registry.REQUIRED_FILES:
                (Path(output) / filename).write_text("{}")

    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(snapshot_download=download))
    monkeypatch.setitem(sys.modules, "ctranslate2.converters", types.SimpleNamespace(TransformersConverter=Converter))
    path = registry.prepare_breeze_model(tmp_path)
    assert path == registry.validate_breeze_model(tmp_path)
    assert (path / "README.md").is_file()
    assert registry.prepare_breeze_model(tmp_path) == path
    assert len(calls) == 1


def test_failed_conversion_is_not_published_and_can_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, worker_modules,
) -> None:
    registry = worker_modules

    class BrokenConverter:
        def __init__(self, *_args, **_kwargs):
            pass

        def convert(self, output, **_kwargs):
            Path(output).mkdir()
            (Path(output) / "model.bin").write_text("partial")
            raise RuntimeError("interrupted conversion")

    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(snapshot_download=lambda **kwargs: "unused"))
    monkeypatch.setitem(sys.modules, "ctranslate2.converters", types.SimpleNamespace(TransformersConverter=BrokenConverter))
    with pytest.raises(RuntimeError, match="interrupted"):
        registry.prepare_breeze_model(tmp_path)
    assert not registry.breeze_model_path(tmp_path).exists()
    assert list(registry.breeze_model_path(tmp_path).parent.iterdir()) == []


@pytest.mark.parametrize("damage", ["missing", "empty", "revision", "invalid-json"])
def test_breeze_rejects_incomplete_or_wrong_builds(tmp_path: Path, worker_modules, damage: str) -> None:
    registry = worker_modules
    path = install_model(registry, tmp_path)
    if damage == "missing":
        (path / "tokenizer.json").unlink()
    elif damage == "empty":
        (path / "model.bin").write_bytes(b"")
    elif damage == "revision":
        (path / "manifest.json").write_text(json.dumps({**registry.MANIFEST, "revision": "wrong"}))
    else:
        (path / "manifest.json").write_text("not-json")
    with pytest.raises(RuntimeError, match="not prepared"):
        registry.resolve_asr_model("breeze-asr-25", tmp_path)
    assert registry.resolve_asr_model("large-v3-turbo", tmp_path) == "large-v3-turbo"


def test_breeze_uses_existing_word_alignment_and_unloads_on_model_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, worker_modules,
) -> None:
    registry = worker_modules
    model_path = install_model(registry, tmp_path)
    events = []

    class WhisperModel:
        def __init__(self, model_name, **kwargs):
            events.append(("load", model_name, kwargs["device"]))
            self.model = types.SimpleNamespace(unload_model=lambda: events.append(("unload", model_name)))

        def transcribe(self, audio, **kwargs):
            assert kwargs["word_timestamps"] is True
            assert kwargs["language"] == "zh"
            assert kwargs["hotwords"] == "PV-1 软件"
            word = types.SimpleNamespace(start=0.1, end=0.9, word=" Breeze")
            segment = types.SimpleNamespace(start=0.0, end=1.0, text=" Breeze", words=[word])
            return iter([segment]), None

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WhisperModel))
    transcriber = importlib.import_module("src.transcriber").Transcriber(
        types.SimpleNamespace(model_root=tmp_path),
        importlib.import_module("src.device").BackendDevice(backend="faster-whisper", device="cpu", compute_type="int8"),
        allow_runtime_fallback=False,
    )
    for model in ("large-v3-turbo", "breeze-asr-25", "breeze-asr-25", "large-v3-turbo"):
        text, segments = transcriber.transcribe(
            tmp_path / "audio.flac", model_name=model, language="zh-tw", hotwords="PV-1 软件",
        )
    assert text == "Breeze"
    aligned = importlib.import_module("src.alignment").WhisperWordAlignment().align(
        tmp_path / "audio.flac", text=text, segments=segments, language="zh-tw",
    )
    assert aligned.words == [{"start": 0.1, "end": 0.9, "text": " Breeze"}]
    assert events == [
        ("load", "large-v3-turbo", "cpu"), ("unload", "large-v3-turbo"),
        ("load", str(model_path), "cpu"), ("unload", str(model_path)),
        ("load", "large-v3-turbo", "cpu"),
    ]


@pytest.mark.parametrize("resource", ["transcriptions", "diarizations"])
def test_breeze_selection_survives_retry_and_all_artifacts(resource: str) -> None:
    with httpx.Client(base_url=os.environ["API_URL"]) as client:
        created = client.post(f"/v1/{resource}", data={
            "youtube_url": "https://youtu.be/breeze-fixture", "model": "breeze-asr-25",
            "language": "zh-tw", "hotwords": "PV-1",
        })
        assert created.status_code == 202
        location = created.headers["Location"]
        run_fake_worker(env={"FAKE_SOURCE_FAILURE": "retryable", "MAX_ATTEMPTS": "1"})
        assert client.get(location).json()["status"] == "failed"
        assert client.post(f"{location}/retry").status_code == 202
        run_fake_worker()
        job = client.get(location).json()
        assert job["status"] == "completed"
        assert job["configuration"]["model"] == "breeze-asr-25"
        assert job["configuration"]["hotwords"] == ["PV-1"]
        for format in ("json", "txt", "srt"):
            artifact = client.get(location, params={"format": format})
            assert artifact.status_code == 200
            if format == "json":
                assert artifact.json()["metadata"]["model"] == "breeze-asr-25"
