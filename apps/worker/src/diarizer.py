from typing import Protocol


class DiarizationEngine(Protocol):
    def diarize(
        self,
        segments: list[dict],
        *,
        min_speakers: int | None,
        max_speakers: int | None,
    ) -> list[dict]: ...


class FakeDiarizationEngine:
    """Deterministic adapter used by the local/integration pipeline.

    It deliberately keeps the public result segment-level; real alignment and
    pyannote attribution are introduced by the subsequent diarization issues.
    """

    def diarize(self, segments: list[dict], *, min_speakers: int | None, max_speakers: int | None) -> list[dict]:
        return [
            {**segment, "speaker": f"SPEAKER_{index % 2:02d}"}
            for index, segment in enumerate(segments)
        ]
