import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "apps" / "worker"))

from src.attribution import attribute_words


def test_infers_an_unattributed_word_from_the_nearest_speaker_turn() -> None:
    result = attribute_words(
        [{"start": 1.5, "end": 2.0, "text": " mystery"}],
        [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"start": 2.2, "end": 3.0, "speaker": "SPEAKER_01"},
        ],
    )

    assert result.words == [{
        "start": 1.5,
        "end": 2.0,
        "text": " mystery",
        "speaker": "SPEAKER_01",
    }]
    assert result.statistics == {
        "word_count": 1,
        "attributed_word_count": 1,
        "unattributed_word_count": 0,
        "inferred_word_count": 1,
    }


def test_prefers_previous_attribution_when_nearest_turns_are_tied() -> None:
    result = attribute_words(
        [
            {"start": 0.0, "end": 1.0, "text": "before"},
            {"start": 1.5, "end": 2.0, "text": "gap"},
            {"start": 2.5, "end": 3.0, "text": "after"},
        ],
        [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"start": 2.5, "end": 3.0, "speaker": "SPEAKER_01"},
        ],
    )

    assert [word["speaker"] for word in result.words] == [
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_01",
    ]


def test_uses_stable_speaker_order_when_every_word_needs_inference() -> None:
    result = attribute_words(
        [{"start": 1.5, "end": 2.0, "text": "only word"}],
        [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_00"},
        ],
    )

    assert result.words[0]["speaker"] == "SPEAKER_00"
    assert result.statistics["unattributed_word_count"] == 0
