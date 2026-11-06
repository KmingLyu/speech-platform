import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def isolated_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ROOT / "apps/worker"))
    from src.device import BackendDevice
    from src.isolated_diarization import IsolatedDiarization

    packages = tmp_path / "packages"
    audio = packages / "pyannote" / "audio"
    audio.mkdir(parents=True)
    (packages / "pyannote" / "__init__.py").touch()
    (packages / "torch.py").write_text(
        "import types\ndevice = str\ncuda = types.SimpleNamespace(is_available=lambda: True)\n"
    )
    library = packages / "nvidia" / "cudnn" / "lib"
    library.mkdir(parents=True)
    (library / "libcudnn_graph.so.9").write_text("discovery fixture")
    (audio / "__init__.py").write_text('''
import os, sys, types
assert os.getpid() != int(os.environ["TEST_PARENT_PID"])
assert "ctranslate2" not in sys.modules
assert "faster_whisper" not in sys.modules
assert os.environ["LD_LIBRARY_PATH"].split(":")[0] == os.environ["TEST_TORCH_LIB"]
class Pipeline:
    @classmethod
    def from_pretrained(cls, path):
        print("pipeline loading output")
        return cls()
    def to(self, device):
        if device == "cuda" and os.getenv("TEST_CUDA_FAILURE"):
            raise RuntimeError("fixture CUDA initialization failure")
        return self
    def __call__(self, path, **kwargs):
        if os.getenv("TEST_NATIVE_EXIT"):
            os._exit(139)
        assert kwargs == {"min_speakers": 1, "max_speakers": 4}
        turn = types.SimpleNamespace(start=0.5, end=1.5)
        timeline = types.SimpleNamespace(itertracks=lambda **kw: [(turn, None, "SPEAKER_00")])
        return types.SimpleNamespace(exclusive_speaker_diarization=timeline)
''')
    monkeypatch.setenv("PYTHONPATH", str(packages))
    monkeypatch.setenv("LD_LIBRARY_PATH", "/original/asr/lib")
    monkeypatch.setenv("TEST_PARENT_PID", str(os.getpid()))
    monkeypatch.setenv("TEST_TORCH_LIB", str(library))
    model_root = tmp_path / "models"
    (model_root / "diarization" / "revision").mkdir(parents=True)

    def backend(*, fallback=True, revision="revision"):
        return IsolatedDiarization(
            model="pyannote/speaker-diarization-community-1", revision=revision,
            model_root=model_root, device=BackendDevice(backend="pyannote", device="cuda"),
            allow_runtime_fallback=fallback,
        )

    return backend


def test_diarization_runs_in_fresh_process_and_preserves_parent_environment(isolated_backend, capfd):
    turns = isolated_backend().diarize(Path("audio.flac"), min_speakers=1, max_speakers=4)
    assert turns == [{"start": 0.5, "end": 1.5, "speaker": "SPEAKER_00"}]
    assert os.environ["LD_LIBRARY_PATH"] == "/original/asr/lib"
    assert "pipeline loading output" in capfd.readouterr().err


def test_child_retains_auto_cpu_fallback(isolated_backend, monkeypatch, capfd):
    monkeypatch.setenv("TEST_CUDA_FAILURE", "1")
    assert isolated_backend().diarize(Path("audio.flac"), min_speakers=1, max_speakers=4)
    assert "falling back to CPU" in capfd.readouterr().err


def test_child_preserves_classified_model_failure(isolated_backend):
    from src.failures import RetryableFailure

    with pytest.raises(RetryableFailure) as error:
        isolated_backend(revision=None).diarize(Path("audio.flac"), min_speakers=1, max_speakers=4)
    assert error.value.failure.code == "diarization_model_unavailable"


def test_strict_cuda_does_not_fall_back_in_child(isolated_backend, monkeypatch, capfd):
    from src.failures import RetryableFailure

    monkeypatch.setenv("TEST_CUDA_FAILURE", "1")
    with pytest.raises(RetryableFailure):
        isolated_backend(fallback=False).diarize(Path("audio.flac"), min_speakers=1, max_speakers=4)
    assert "falling back to CPU" not in capfd.readouterr().err


def test_native_child_exit_is_reported_without_killing_worker(isolated_backend, monkeypatch):
    from src.failures import RetryableFailure

    monkeypatch.setenv("TEST_NATIVE_EXIT", "1")
    with pytest.raises(RetryableFailure) as error:
        isolated_backend().diarize(Path("audio.flac"), min_speakers=1, max_speakers=4)
    assert error.value.failure.code == "diarization_process_failed"
    assert "139" in str(error.value)


def test_torch_cuda_probe_uses_its_own_process(isolated_backend):
    from src.device import _probe_pyannote_cuda

    assert _probe_pyannote_cuda() == (True, None)
    assert os.environ["LD_LIBRARY_PATH"] == "/original/asr/lib"
