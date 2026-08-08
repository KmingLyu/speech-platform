import sys
from pathlib import Path


WORKER_ROOT = Path(__file__).parents[2] / "apps" / "worker"
sys.path.insert(0, str(WORKER_ROOT))

from src.script_converter import convert_transcript


def test_convert_transcript_normalizes_all_text_fields_once() -> None:
    text, segments = convert_transcript(
        "软件",
        [{
            "id": 0,
            "start": 0.0,
            "end": 1.0,
            "text": "软件",
            "words": [{"start": 0.0, "end": 1.0, "text": "软件"}],
        }],
        "zh-tw",
    )

    assert text == "軟體"
    assert segments[0]["text"] == "軟體"
    assert segments[0]["words"][0]["text"] == "軟體"


def test_convert_transcript_preserves_text_without_script_conversion() -> None:
    text, segments = convert_transcript(
        "软件",
        [{"id": 0, "start": 0.0, "end": 1.0, "text": "软件", "words": []}],
        None,
    )

    assert text == "软件"
    assert segments[0]["text"] == "软件"
