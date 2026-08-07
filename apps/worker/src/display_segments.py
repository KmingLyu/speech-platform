"""Derive the single-line subtitle cues exported by Diarization jobs."""

from itertools import groupby
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


def display_segments(words: list[dict], *, max_chars_per_line: int) -> list[dict]:
    """Derive single-speaker cues without crossing ASR segment boundaries."""
    cues: list[dict] = []
    display_words: list[dict] = []
    for word in words:
        split_words = _split_overlong_word(word, max_chars_per_line)
        display_words.extend(
            {**display_word, "_split_for_display": len(split_words) > 1}
            for display_word in split_words
        )

    def emit(words_to_emit: list[dict], *, preserve_asr_timing: bool = False) -> None:
        if not words_to_emit:
            return
        start = words_to_emit[0]["start"]
        end = words_to_emit[-1]["end"]
        if preserve_asr_timing:
            start = words_to_emit[0].get("asr_segment_start", start)
            end = words_to_emit[-1].get("asr_segment_end", end)
        cues.append({
            "id": len(cues),
            "start": start,
            "end": end,
            "speaker": words_to_emit[0]["speaker"],
            "text": "".join(word["text"] for word in words_to_emit).strip(),
        })

    def emit_with_capacity(words_to_emit: list[dict], *, preserve_asr_timing: bool) -> None:
        remaining = words_to_emit
        split_for_capacity = False
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
                split_for_capacity = True
                continue
            cut = max(
                cuts_that_fit,
                key=lambda index: _boundary_priority(remaining, index),
            )
            emit(remaining[:cut])
            remaining = remaining[cut:]
            split_for_capacity = True
        emit(remaining, preserve_asr_timing=preserve_asr_timing and not split_for_capacity)

    for _, source_words_iter in groupby(
        display_words,
        key=lambda word: word.get("asr_segment_id", "__ungrouped__"),
    ):
        source_words = list(source_words_iter)
        source_was_split = any(word["_split_for_display"] for word in source_words)
        for _, speaker_words_iter in groupby(source_words, key=lambda word: word["speaker"]):
            speaker_words = list(speaker_words_iter)
            emit_with_capacity(
                speaker_words,
                preserve_asr_timing=(
                    len(speaker_words) == len(source_words) and not source_was_split
                ),
            )
    return cues
