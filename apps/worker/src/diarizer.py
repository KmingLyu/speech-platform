import logging
from pathlib import Path
from typing import Protocol

from .device import BackendDevice
from .failures import diarization_model_unavailable


logger = logging.getLogger(__name__)


class DiarizationEngine(Protocol):
    def diarize(
        self,
        audio_path: Path,
        *,
        min_speakers: int | None,
        max_speakers: int | None,
    ) -> list[dict]: ...


class PyannoteCommunityDiarization:
    """Use Community-1's non-overlapping exclusive speaker diarization output."""

    def __init__(
        self,
        model: str = "pyannote/speaker-diarization-community-1",
        revision: str | None = None,
        model_root: Path | None = None,
        device: BackendDevice | None = None,
        *,
        allow_runtime_fallback: bool = False,
    ):
        self.pipeline = None
        self.model = model
        self.revision = revision
        self.model_root = model_root
        self.device = device or BackendDevice(backend="pyannote", device="cpu")
        self.allow_runtime_fallback = allow_runtime_fallback

    def _load(self):
        if self.pipeline is None:
            if not self.revision:
                raise diarization_model_unavailable("DIARIZATION_MODEL_REVISION is not configured")
            from pyannote.audio import Pipeline

            model_path = (self.model_root / "diarization" / self.revision
                          if self.model_root is not None else None)
            if model_path is None or not model_path.is_dir():
                raise diarization_model_unavailable(
                    f"Pinned model directory is missing: {model_path}"
                )
            pipeline = Pipeline.from_pretrained(str(model_path))
            import torch

            try:
                pipeline.to(torch.device(self.device.device))
            except Exception:
                if self.device.device != "cuda" or not self.allow_runtime_fallback:
                    raise
                logger.warning(
                    "GPU initialization failed; falling back to CPU "
                    "backend=pyannote model=%s device=cpu",
                    self.model,
                    exc_info=True,
                )
                pipeline.to(torch.device("cpu"))
            self.pipeline = pipeline
        return self.pipeline

    def diarize(self, audio_path: Path, *, min_speakers: int | None, max_speakers: int | None) -> list[dict]:
        kwargs = {
            key: value for key, value in {
                "min_speakers": min_speakers, "max_speakers": max_speakers,
            }.items() if value is not None
        }
        output = self._load()(str(audio_path), **kwargs)
        exclusive = output.exclusive_speaker_diarization
        return [
            {"start": turn.start, "end": turn.end, "speaker": speaker}
            for turn, _, speaker in exclusive.itertracks(yield_label=True)
        ]
