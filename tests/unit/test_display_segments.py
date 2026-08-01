import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "apps" / "worker"))

from src.display_segments import display_segments


def test_display_segments_split_at_sentence_boundaries_before_line_capacity() -> None:
    cues = display_segments(
        [
            {"start": 0.0, "end": 0.5, "speaker": "SPEAKER_00", "text": "Hello."},
            {"start": 0.5, "end": 1.0, "speaker": "SPEAKER_00", "text": " Next."},
        ],
        max_chars_per_line=30,
    )

    assert cues == [
        {"id": 0, "start": 0.0, "end": 0.5, "speaker": "SPEAKER_00", "text": "Hello."},
        {"id": 1, "start": 0.5, "end": 1.0, "speaker": "SPEAKER_00", "text": "Next."},
    ]


def test_display_segments_ignore_reading_speed_and_duration_when_within_capacity() -> None:
    cues = display_segments(
        [
            {"start": 0.0, "end": 0.1, "speaker": "SPEAKER_00", "text": "Fast"},
            {"start": 0.1, "end": 0.2, "speaker": "SPEAKER_00", "text": " words"},
        ],
        max_chars_per_line=30,
    )

    assert cues == [
        {"id": 0, "start": 0.0, "end": 0.2, "speaker": "SPEAKER_00", "text": "Fast words"},
    ]


def test_display_segments_preserve_source_word_timing_and_silence() -> None:
    cues = display_segments(
        [
            {"start": 0.0, "end": 0.2, "speaker": "SPEAKER_00", "text": "Short."},
            {"start": 1.0, "end": 1.3, "speaker": "SPEAKER_00", "text": " Next."},
        ],
        max_chars_per_line=30,
    )

    assert cues == [
        {"id": 0, "start": 0.0, "end": 0.2, "speaker": "SPEAKER_00", "text": "Short."},
        {"id": 1, "start": 1.0, "end": 1.3, "speaker": "SPEAKER_00", "text": "Next."},
    ]
