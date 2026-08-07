import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "apps" / "worker"))

from src.display_segments import display_segments


def test_display_segments_preserve_unmodified_asr_segment_timing_and_boundaries() -> None:
    cues = display_segments(
        [
            {
                "start": 0.2, "end": 0.5, "speaker": "SPEAKER_00", "text": "Hello.",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 1.0,
            },
            {
                "start": 1.2, "end": 1.6, "speaker": "SPEAKER_00", "text": " Next.",
                "asr_segment_id": 1, "asr_segment_start": 1.0, "asr_segment_end": 2.0,
            },
        ],
        max_chars_per_line=30,
    )

    assert cues == [
        {"id": 0, "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Hello."},
        {"id": 1, "start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "Next."},
    ]


def test_display_segments_split_a_cross_speaker_asr_segment_at_word_timestamps() -> None:
    cues = display_segments(
        [
            {
                "start": 0.2, "end": 0.5, "speaker": "SPEAKER_00", "text": "Hello",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 1.0,
            },
            {
                "start": 0.5, "end": 0.8, "speaker": "SPEAKER_01", "text": " world",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 1.0,
            },
        ],
        max_chars_per_line=30,
    )

    assert cues == [
        {"id": 0, "start": 0.2, "end": 0.5, "speaker": "SPEAKER_00", "text": "Hello"},
        {"id": 1, "start": 0.5, "end": 0.8, "speaker": "SPEAKER_01", "text": "world"},
    ]


def test_display_segments_preserve_an_asr_segment_despite_sentence_boundaries() -> None:
    cues = display_segments(
        [
            {
                "start": 0.0, "end": 0.5, "speaker": "SPEAKER_00", "text": "Hello.",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 1.0,
            },
            {
                "start": 0.5, "end": 1.0, "speaker": "SPEAKER_00", "text": " Next.",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 1.0,
            },
        ],
        max_chars_per_line=30,
    )

    assert cues == [
        {"id": 0, "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Hello. Next."},
    ]


def test_display_segments_ignore_reading_speed_and_duration_when_within_capacity() -> None:
    cues = display_segments(
        [
            {
                "start": 0.0, "end": 0.1, "speaker": "SPEAKER_00", "text": "Fast",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 0.2,
            },
            {
                "start": 0.1, "end": 0.2, "speaker": "SPEAKER_00", "text": " words",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 0.2,
            },
        ],
        max_chars_per_line=30,
    )

    assert cues == [
        {"id": 0, "start": 0.0, "end": 0.2, "speaker": "SPEAKER_00", "text": "Fast words"},
    ]


def test_display_segments_preserve_asr_timing_and_silence() -> None:
    cues = display_segments(
        [
            {
                "start": 0.0, "end": 0.2, "speaker": "SPEAKER_00", "text": "Short.",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 1.3,
            },
            {
                "start": 1.0, "end": 1.3, "speaker": "SPEAKER_00", "text": " Next.",
                "asr_segment_id": 0, "asr_segment_start": 0.0, "asr_segment_end": 1.3,
            },
        ],
        max_chars_per_line=30,
    )

    assert cues == [
        {"id": 0, "start": 0.0, "end": 1.3, "speaker": "SPEAKER_00", "text": "Short. Next."},
    ]
