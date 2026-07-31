from pathlib import Path
from typing import Protocol


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

    def __init__(self, model: str = "pyannote/speaker-diarization-community-1"):
        self.pipeline = None
        self.model = model

    def _load(self):
        if self.pipeline is None:
            from pyannote.audio import Pipeline

            self.pipeline = Pipeline.from_pretrained(self.model)
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
