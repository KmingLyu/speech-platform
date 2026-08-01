"""Derive the single-line subtitle cues exported by Diarization jobs."""

from math import ceil
import re
from unicodedata import east_asian_width


def visual_units(text: str) -> float:
    """Count full-width characters as one unit and other characters as half."""
    return sum(1.0 if east_asian_width(character) in {"W", "F"} else 0.5 for character in text)


def _visible_label(speaker: str | None) -> str:
    return f"[{speaker or 'UNKNOWN'}] "


def _split_overlong_word(word: dict, max_chars_per_line: int) -> list[dict]:
    """Make a long timestamped word fit the line capacity without changing its span.

    Semantic protected spans are deliberately deferred to issue 02. Until then,
    character boundaries preserve the complete spoken text and distribute the
    original word timing proportionally across the derived display cues.
    """
    text = word["text"].strip()
    if _is_protected_span(text):
        return [word]
    start = float(word["start"])
    duration = float(word["end"]) - start
    available_units = max_chars_per_line - visual_units(_visible_label(word["speaker"]))
    if not text or available_units <= 0:
        return [word]
    part_count = max(
        1,
        ceil(visual_units(text) / available_units),
    )
    if part_count == 1:
        return [word]
    boundaries = [round(index * len(text) / part_count) for index in range(part_count + 1)]
    parts = [text[boundaries[index]:boundaries[index + 1]] for index in range(part_count)]
    return [
        {
            **word,
            "start": start + duration * index / part_count,
            "end": start + duration * (index + 1) / part_count,
            "text": part,
        }
        for index, part in enumerate(parts)
        if part
    ]


def _is_protected_span(text: str) -> bool:
    """Keep identifiers, number-and-unit phrases, and common Chinese names whole."""
    compact = text.strip()
    return bool(
        re.fullmatch(r"[A-Za-z]+(?:[- ][A-Za-z0-9]+)+", compact)
        or re.fullmatch(r"\d+(?:\.\d+)?[A-Za-z%℃°]+", compact)
        or re.fullmatch(r"[王李張陳林黃吳劉蔡楊許鄭謝郭洪邱曾廖賴周徐蘇葉莊呂江何蕭羅高潘簡朱鍾彭游詹胡施沈余趙盧梁顏柯翁魏孫戴范方宋鄧杜傅侯曹薛丁溫紀范藍連唐馬董石卓程姚康馮古姜湯汪白鄒尤巫鐘][\u4e00-\u9fff]{2}", compact)
    )


def _boundary_priority(words: list[dict], cut: int) -> tuple[int, float]:
    """Rank allowed cuts by linguistic boundary, then by visual balance."""
    text = words[cut - 1]["text"].rstrip()
    if text.endswith(("。", "！", "？", ".", "!", "?")):
        priority = 4
    elif text.endswith(("，", "、", "；", "：", ",", ";", ":")):
        priority = 3
    elif cut < len(words) and float(words[cut]["start"]) - float(words[cut - 1]["end"]) >= 0.25:
        priority = 2
    else:
        priority = 1
    return priority, visual_units("".join(word["text"] for word in words[:cut]).strip())


def display_segments(
    words: list[dict], *, max_chars_per_line: int,
) -> list[dict]:
    """Split attributed words into sequential, single-line public subtitle cues.

    Speaker-labelled text stays in speaker-consistent cues. Reliable speaker
    changes are therefore inviolable boundaries; attribution gaps also remain
    separate so an unknown word is never shown under a known speaker label.
    Sentence-ending punctuation creates a cue before line capacity is considered.
    Within a sentence, line capacity prefers punctuation and pause boundaries.
    A single protected word may exceed capacity so names, numbers, and hyphenated
    terms remain intact.
    """
    cues: list[dict] = []
    current: list[dict] = []
    display_words = [
        display_word
        for word in words
        for display_word in _split_overlong_word(word, max_chars_per_line)
    ]

    def emit(words_to_emit: list[dict]) -> None:
        if not words_to_emit:
            return
        cues.append({
            "id": len(cues),
            "start": words_to_emit[0]["start"],
            "end": words_to_emit[-1]["end"],
            "speaker": words_to_emit[0]["speaker"],
            "text": "".join(word["text"] for word in words_to_emit).strip(),
        })

    def emit_sentence(words_to_emit: list[dict]) -> None:
        remaining = words_to_emit
        while len(remaining) > 1:
            text = "".join(item["text"] for item in remaining).strip()
            label_units = visual_units(_visible_label(remaining[0]["speaker"]))
            if label_units + visual_units(text) <= max_chars_per_line:
                break
            cuts_that_fit = [
                index
                for index in range(1, len(remaining))
                if label_units + visual_units(
                    "".join(word["text"] for word in remaining[:index]).strip(),
                ) <= max_chars_per_line
            ]
            if not cuts_that_fit:
                emit(remaining[:1])
                remaining = remaining[1:]
                continue
            cut = max(
                cuts_that_fit,
                key=lambda index: _boundary_priority(remaining, index),
            )
            emit(remaining[:cut])
            remaining = remaining[cut:]
        emit(remaining)

    for word in display_words:
        if current and current[-1]["speaker"] != word["speaker"]:
            emit_sentence(current)
            current = []

        current.append(word)
        if current and current[-1]["text"].rstrip().endswith(
            ("。", "！", "？", ".", "!", "?"),
        ):
            emit_sentence(current)
            current = []

    emit_sentence(current)
    return cues
