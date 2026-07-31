from pathlib import Path
from typing import Protocol


class AlignmentEngine(Protocol):
    def align(
        self,
        audio_path: Path,
        *,
        text: str,
        segments: list[dict],
        language: str | None,
    ) -> list[dict]: ...


class WhisperWordAlignment:
    """Use word timestamps emitted by faster-whisper as the alignment seam."""

    def align(
        self,
        _audio_path: Path,
        *,
        text: str,
        segments: list[dict],
        language: str | None,
    ) -> list[dict]:
        del text, language
        return [
            {"start": float(word["start"]), "end": float(word["end"]), "text": str(word["text"])}
            for segment in segments
            for word in segment.get("words", [])
        ]
