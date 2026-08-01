import importlib
import logging
import sys
import types
from pathlib import Path

import pytest


WORKER_ROOT = Path(__file__).parents[2] / "apps" / "worker"
sys.path.insert(0, str(WORKER_ROOT))
device_module = importlib.import_module("src.device")


def test_auto_prefers_cuda_for_each_available_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        device_module, "_probe_faster_whisper_cuda", lambda: (True, None)
    )
    monkeypatch.setattr(device_module, "_probe_pyannote_cuda", lambda: (True, None))

    plan = device_module.resolve_inference_devices("auto")

    assert plan.transcription.device == "cuda"
    assert plan.transcription.compute_type == "float16"
    assert plan.diarization.device == "cuda"
    assert plan.allow_runtime_fallback is True


def test_auto_falls_back_per_backend_and_logs_cpu_usage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        device_module,
        "_probe_faster_whisper_cuda",
        lambda: (False, "no CTranslate2 CUDA device"),
    )
    monkeypatch.setattr(device_module, "_probe_pyannote_cuda", lambda: (True, None))

    plan = device_module.resolve_inference_devices("auto")
    with caplog.at_level(logging.INFO, logger="src.device"):
        device_module.log_inference_devices(plan)

    assert plan.transcription.device == "cpu"
    assert plan.transcription.compute_type == "int8"
    assert plan.diarization.device == "cuda"
    assert "backend=faster-whisper" in caplog.text
    assert "device=cpu" in caplog.text
    assert "no CTranslate2 CUDA device" in caplog.text


def test_explicit_cuda_fails_fast_when_any_backend_cannot_use_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        device_module, "_probe_faster_whisper_cuda", lambda: (True, None)
    )
    monkeypatch.setattr(
        device_module,
        "_probe_pyannote_cuda",
        lambda: (False, "torch.cuda.is_available() is false"),
    )

    with pytest.raises(RuntimeError, match="pyannote"):
        device_module.resolve_inference_devices("cuda")


def test_invalid_device_preference_is_rejected() -> None:
    with pytest.raises(ValueError, match="INFERENCE_DEVICE"):
        device_module.resolve_inference_devices("metal")


def test_diarizer_runtime_cuda_failure_falls_back_to_cpu_and_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    moves: list[str] = []

    class Pipeline:
        @classmethod
        def from_pretrained(cls, _path: str):
            return cls()

        def to(self, target: str):
            moves.append(target)
            if target == "cuda":
                raise RuntimeError("CUDA allocation failed")
            return self

    monkeypatch.setitem(sys.modules, "pyannote", types.ModuleType("pyannote"))
    monkeypatch.setitem(
        sys.modules, "pyannote.audio", types.SimpleNamespace(Pipeline=Pipeline)
    )
    monkeypatch.setitem(
        sys.modules, "torch", types.SimpleNamespace(device=lambda value: value)
    )
    diarizer_module = importlib.import_module("src.diarizer")
    model_path = tmp_path / "diarization" / "revision"
    model_path.mkdir(parents=True)
    diarizer = diarizer_module.PyannoteCommunityDiarization(
        revision="revision",
        model_root=tmp_path,
        device=device_module.BackendDevice(backend="pyannote", device="cuda"),
        allow_runtime_fallback=True,
    )

    with caplog.at_level(logging.WARNING, logger="src.diarizer"):
        diarizer._load()

    assert moves == ["cuda", "cpu"]
    assert "falling back to CPU" in caplog.text
    assert "backend=pyannote" in caplog.text


def test_transcriber_runtime_cuda_failure_uses_cpu_int8_and_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempts: list[dict] = []

    class WhisperModel:
        def __init__(self, _model_name: str, **kwargs):
            attempts.append(kwargs)
            if kwargs["device"] == "cuda":
                raise RuntimeError("CUDA initialization failed")

        def transcribe(self, *_args, **_kwargs):
            return iter(()), None

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WhisperModel)
    )
    monkeypatch.setitem(
        sys.modules,
        "src.script_converter",
        types.SimpleNamespace(asr_language=lambda value: value),
    )
    sys.modules.pop("src.transcriber", None)
    transcriber_module = importlib.import_module("src.transcriber")
    settings = types.SimpleNamespace(model_root=tmp_path)
    transcriber = transcriber_module.Transcriber(
        settings,
        device_module.BackendDevice(
            backend="faster-whisper", device="cuda", compute_type="float16"
        ),
        allow_runtime_fallback=True,
    )

    with caplog.at_level(logging.WARNING, logger="src.transcriber"):
        transcriber.transcribe(
            tmp_path / "audio.flac", model_name="model", language=None
        )

    assert [(item["device"], item["compute_type"]) for item in attempts] == [
        ("cuda", "float16"),
        ("cpu", "int8"),
    ]
    assert "falling back to CPU" in caplog.text
    assert "backend=faster-whisper" in caplog.text
