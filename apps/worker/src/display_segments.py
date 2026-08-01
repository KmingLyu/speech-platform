"""Derive the single-line subtitle cues exported by Diarization jobs."""

from unicodedata import east_asian_width
from math import ceil
import re


MAX_SPOKEN_UNITS_PER_SECOND = 6.0
MAX_CUE_DURATION_SECONDS = 5.0


def visual_units(text: str) -> float:
    """Count full-width characters as one unit and other characters as half."""
    return sum(1.0 if east_asian_width(character) in {"W", "F"} else 0.5 for character in text)


def _visible_label(speaker: str | None) -> str:
    return f"[{speaker or 'UNKNOWN'}] "


def _split_overlong_word(word: dict, max_chars_per_line: int) -> list[dict]:
    """Make a long timestamped word fit the foundation's capacity/duration rules.

    Semantic protected spans are deliberately deferred to issue 02. Until then,
    character boundaries preserve the complete spoken text and distribute the
    original word timing proportionally across the derived display cues.
    """
    text = word["text"].strip()
    if _is_protected_span(text):
        return [word]
    duration = float(word["end"]) - float(word["start"])
    available_units = max_chars_per_line - visual_units(_visible_label(word["speaker"]))
    if not text or available_units <= 0:
        return [word]
    part_count = max(
        1,
        ceil(duration / MAX_CUE_DURATION_SECONDS),
        ceil(visual_units(text) / available_units),
        ceil(visual_units(text) / (MAX_SPOKEN_UNITS_PER_SECOND * MAX_CUE_DURATION_SECONDS)),
    )
    if part_count == 1:
        return [word]
    boundaries = [round(index * len(text) / part_count) for index in range(part_count + 1)]
    parts = [text[boundaries[index]:boundaries[index + 1]] for index in range(part_count)]
    return [
        {
            **word,
            "start": float(word["start"]) + duration * index / part_count,
            "end": float(word["start"]) + duration * (index + 1) / part_count,
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


def _with_proportional_word_timing(words: list[dict]) -> list[dict]:
    """Estimate word timing inside already speaker-consistent timed spans."""
    timed: list[dict] = []
    index = 0
    while index < len(words):
        end_index = index + 1
        while end_index < len(words) and words[end_index]["speaker"] == words[index]["speaker"]:
            end_index += 1
        span = words[index:end_index]
        start = float(span[0]["start"])
        end = float(span[-1]["end"])
        total_units = sum(visual_units(word["text"].strip()) for word in span) or 1.0
        cursor = start
        for position, word in enumerate(span):
            if position == len(span) - 1:
                word_end = end
            else:
                word_end = cursor + (end - start) * visual_units(word["text"].strip()) / total_units
            timed.append({**word, "start": cursor, "end": word_end})
            cursor = word_end
        index = end_index
    return timed


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
    words: list[dict], *, max_chars_per_line: int, proportional_timing: bool = False,
) -> list[dict]:
    """Split attributed words into sequential, single-line public subtitle cues.

    Speaker-labelled text stays in speaker-consistent cues. Reliable speaker
    changes are therefore inviolable boundaries; attribution gaps also remain
    separate so an unknown word is never shown under a known speaker label. Within a speaker-consistent span,
    the earliest word boundary that would violate capacity, reading speed, or the
    normal five-second maximum begins the next cue. A single word may exceed the
    capacity so protected names, numbers, and hyphenated terms remain intact.
    """
    cues: list[dict] = []
    current: list[dict] = []
    source_words = _with_proportional_word_timing(words) if proportional_timing else words
    display_words = [
        display_word
        for word in source_words
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

    for word in display_words:
        if current and current[-1]["speaker"] != word["speaker"]:
            emit(current)
            current = []

        current.append(word)
        while len(current) > 1:
            text = "".join(item["text"] for item in current).strip()
            duration = float(current[-1]["end"]) - float(current[0]["start"])
            label_units = visual_units(_visible_label(current[0]["speaker"]))
            violates_constraints = (
                label_units + visual_units(text) > max_chars_per_line
                or duration > 0 and visual_units(text) / duration > MAX_SPOKEN_UNITS_PER_SECOND
                or duration > MAX_CUE_DURATION_SECONDS
            )
            if not violates_constraints:
                break
            cut = max(range(1, len(current)), key=lambda index: _boundary_priority(current, index))
            emit(current[:cut])
            current = current[cut:]

    emit(current)
    timeline_end = 0.0
    for index, cue in enumerate(cues):
        cue["start"] = max(float(cue["start"]), timeline_end)
        minimum_duration = max(1.0, visual_units(cue["text"]) / MAX_SPOKEN_UNITS_PER_SECOND)
        maximum_end = cue["start"] + MAX_CUE_DURATION_SECONDS
        if index + 1 < len(cues):
            next_cue = cues[index + 1]
            is_reliable_speaker_change = (
                cue["speaker"] is not None
                and next_cue["speaker"] is not None
                and cue["speaker"] != next_cue["speaker"]
            )
            if is_reliable_speaker_change:
                maximum_end = min(maximum_end, float(next_cue["start"]))
        cue["end"] = min(maximum_end, cue["start"] + max(
            float(cue["end"]) - float(cue["start"]),
            minimum_duration,
        ))
        timeline_end = cue["end"]
    return cues
