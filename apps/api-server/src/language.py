from functools import lru_cache
from typing import Literal

from opencc import OpenCC

OutputScript = Literal["original", "traditional", "simplified"]

# Keep these OpenCC configs in step with the Worker's `script_converter`, so a
# Hotword is biased toward exactly the characters the Transcript will use.
_CONVERSION_CONFIGS: dict[OutputScript, str | None] = {
    "original": None,
    "traditional": "s2twp.json",
    "simplified": "tw2sp.json",
}


def output_script_for(language: str | None) -> OutputScript:
    """Map a requested Chinese locale to the transcript's output script."""
    normalized = (language or "").lower().replace("_", "-")
    if normalized in {"zh-tw", "zh-hant-tw"}:
        return "traditional"
    if normalized in {"zh-cn", "zh-hans-cn"}:
        return "simplified"
    return "original"


@lru_cache(maxsize=len(_CONVERSION_CONFIGS))
def _converter(output_script: OutputScript) -> OpenCC | None:
    config = _CONVERSION_CONFIGS[output_script]
    return OpenCC(config) if config else None


def convert_text(text: str, output_script: OutputScript) -> str:
    converter = _converter(output_script)
    return converter.convert(text) if converter else text
