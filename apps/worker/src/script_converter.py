from functools import lru_cache
from typing import Literal

from opencc import OpenCC

OutputScript = Literal["original", "traditional", "simplified"]

_CONFIGS: dict[OutputScript, str | None] = {
    "original": None,
    "traditional": "s2twp.json",
    "simplified": "tw2sp.json",
}


@lru_cache(maxsize=2)
def _converter(output_script: OutputScript) -> OpenCC | None:
    config = _CONFIGS[output_script]
    return OpenCC(config) if config else None


def convert_text(text: str, output_script: OutputScript) -> str:
    converter = _converter(output_script)
    return converter.convert(text) if converter else text


def convert_segments(segments: list[dict], output_script: OutputScript) -> list[dict]:
    return [{**segment, "text": convert_text(segment["text"], output_script)} for segment in segments]


def asr_language(language: str | None) -> str | None:
    """faster-whisper accepts `zh`, not locale-specific values such as `zh-tw`."""
    normalized = (language or "").lower().replace("_", "-")
    if normalized in {"zh-tw", "zh-hant-tw", "zh-cn", "zh-hans-cn"}:
        return "zh"
    return language
