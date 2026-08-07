import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "apps" / "worker"))

from src.alignment import associate_words_with_asr_segments


def test_associate_words_with_asr_segments_preserves_source_boundaries() -> None:
    associated = associate_words_with_asr_segments(
        [
            {"start": 0.2, "end": 0.8, "text": "first"},
            {"start": 1.2, "end": 1.8, "text": "second"},
        ],
        [
            {"id": 3, "start": 0.0, "end": 1.0, "text": "first"},
            {"id": 4, "start": 1.0, "end": 2.0, "text": "second"},
        ],
    )

    assert associated == [
        {
            "start": 0.2, "end": 0.8, "text": "first",
            "asr_segment_id": 3, "asr_segment_start": 0.0, "asr_segment_end": 1.0,
        },
        {
            "start": 1.2, "end": 1.8, "text": "second",
            "asr_segment_id": 4, "asr_segment_start": 1.0, "asr_segment_end": 2.0,
        },
    ]
