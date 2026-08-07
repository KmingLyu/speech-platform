from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AlignmentResult:
    words: list[dict]
    strategy: str
    language: str | None
    fallback_used: bool = False
    fallback_reason: str | None = None


class AlignmentEngine(Protocol):
    def align(
        self,
        audio_path: Path,
        *,
        text: str,
        segments: list[dict],
        language: str | None,
    ) -> AlignmentResult: ...


class AlignmentUnavailable(RuntimeError):
    """The preferred alignment strategy cannot process this input."""


def associate_words_with_asr_segments(words: list[dict], segments: list[dict]) -> list[dict]:
    """Retain each aligned word's source ASR segment for display segmentation."""
    associated: list[dict] = []
    for word in words:
        word_start = float(word["start"])
        word_end = float(word["end"])
        overlaps = [
            (
                max(0.0, min(word_end, float(segment["end"])) - max(word_start, float(segment["start"]))),
                -index,
                segment,
            )
            for index, segment in enumerate(segments)
        ]
        if not overlaps:
            raise AlignmentUnavailable("No ASR segments are available for word association")
        _, _, source = max(overlaps, key=lambda item: (item[0], item[1]))
        associated.append({
            **word,
            "asr_segment_id": source["id"],
            "asr_segment_start": float(source["start"]),
            "asr_segment_end": float(source["end"]),
        })
    return associated


class WhisperWordAlignment:
    """Use word timestamps emitted by faster-whisper as the alignment seam."""

    def align(
        self,
        _audio_path: Path,
        *,
        text: str,
        segments: list[dict],
        language: str | None,
    ) -> AlignmentResult:
        del text
        words = [
            {"start": float(word["start"]), "end": float(word["end"]), "text": str(word["text"])}
            for segment in segments
            for word in segment.get("words", [])
        ]
        if not words:
            raise AlignmentUnavailable("Whisper did not provide word timestamps")
        return AlignmentResult(
            words=words,
            strategy="whisper_word_timestamps",
            language=language,
        )


class ForcedAlignmentWithWhisperFallback:
    """Prefer a forced aligner and retain a deterministic Whisper fallback."""

    def __init__(self, forced: AlignmentEngine | None, fallback: AlignmentEngine):
        self.forced = forced
        self.fallback = fallback

    def align(
        self,
        audio_path: Path,
        *,
        text: str,
        segments: list[dict],
        language: str | None,
    ) -> AlignmentResult:
        if self.forced is not None:
            try:
                result = self.forced.align(
                    audio_path, text=text, segments=segments, language=language,
                )
                if result.words:
                    return result
            except Exception as error:
                reason = str(error) or error.__class__.__name__
            else:
                reason = "Forced alignment returned no word timestamps"
        else:
            reason = "No forced alignment model is configured"

        result = self.fallback.align(
            audio_path, text=text, segments=segments, language=language,
        )
        return AlignmentResult(
            words=result.words,
            strategy=result.strategy,
            language=result.language,
            fallback_used=True,
            fallback_reason=reason,
        )
