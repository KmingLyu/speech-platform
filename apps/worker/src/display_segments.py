"""Derive the single-line subtitle cues exported by Diarization jobs."""

from unicodedata import east_asian_width
from math import ceil


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


def display_segments(words: list[dict], *, max_chars_per_line: int) -> list[dict]:
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
    display_words = [
        display_word
        for word in words
        for display_word in _split_overlong_word(word, max_chars_per_line)
    ]

    def emit() -> None:
        if not current:
            return
        cues.append({
            "id": len(cues),
            "start": current[0]["start"],
            "end": current[-1]["end"],
            "speaker": current[0]["speaker"],
            "text": "".join(word["text"] for word in current).strip(),
        })

    for word in display_words:
        if current and current[-1]["speaker"] != word["speaker"]:
            emit()
            current = []

        candidate = [*current, word]
        text = "".join(item["text"] for item in candidate).strip()
        duration = float(candidate[-1]["end"]) - float(candidate[0]["start"])
        label_units = visual_units(_visible_label(candidate[0]["speaker"]))
        exceeds_capacity = label_units + visual_units(text) > max_chars_per_line
        exceeds_speed = duration > 0 and visual_units(text) / duration > MAX_SPOKEN_UNITS_PER_SECOND
        exceeds_duration = duration > MAX_CUE_DURATION_SECONDS
        if current and (exceeds_capacity or exceeds_speed or exceeds_duration):
            emit()
            current = [word]
        else:
            current = candidate

    emit()
    timeline_end = 0.0
    for cue in cues:
        cue["start"] = max(float(cue["start"]), timeline_end)
        minimum_duration = max(1.0, visual_units(cue["text"]) / MAX_SPOKEN_UNITS_PER_SECOND)
        cue["end"] = cue["start"] + max(
            float(cue["end"]) - float(cue["start"]),
            minimum_duration,
        )
        timeline_end = cue["end"]
    return cues
