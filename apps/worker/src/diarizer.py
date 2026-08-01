from pathlib import Path
from typing import Protocol

from .failures import diarization_model_unavailable


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

    def __init__(self, model: str = "pyannote/speaker-diarization-community-1",
                 revision: str | None = None, model_root: Path | None = None):
        self.pipeline = None
        self.model = model
        self.revision = revision
        self.model_root = model_root

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
            self.pipeline = Pipeline.from_pretrained(str(model_path))
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
