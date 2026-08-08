from functools import lru_cache

from opencc import OpenCC

_CONFIGS: dict[str, str | None] = {
    "zh-tw": "s2twp.json",
    "zh-cn": "tw2sp.json",
}


@lru_cache(maxsize=2)
def _converter(language: str | None) -> OpenCC | None:
    config = _CONFIGS.get(language or "")
    return OpenCC(config) if config else None


def convert_text(text: str, language: str | None) -> str:
    converter = _converter(language)
    return converter.convert(text) if converter else text


def convert_segments(segments: list[dict], language: str | None) -> list[dict]:
    return [
        {
            **segment,
            "text": convert_text(segment["text"], language),
            "words": [
                {**word, "text": convert_text(word["text"], language)}
                for word in segment.get("words", [])
            ],
        }
        for segment in segments
    ]


def convert_transcript(
    text: str, segments: list[dict], language: str | None
) -> tuple[str, list[dict]]:
    """Normalize every Transcript text field once after ASR."""
    return convert_text(text, language), convert_segments(segments, language)


def asr_language(language: str | None) -> str | None:
    """faster-whisper accepts `zh`, not locale-specific values such as `zh-tw`."""
    normalized = (language or "").lower().replace("_", "-")
    if normalized in {"zh-tw", "zh-hant-tw", "zh-cn", "zh-hans-cn"}:
        return "zh"
    return language
