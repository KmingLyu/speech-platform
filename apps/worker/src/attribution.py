from dataclasses import dataclass


@dataclass(frozen=True)
class AttributionResult:
    words: list[dict]
    statistics: dict[str, int]


def _speaker_for_word(word: dict, turns: list[dict]) -> str | None:
    overlaps: dict[str, float] = {}
    for turn in turns:
        start = max(float(word["start"]), float(turn["start"]))
        end = min(float(word["end"]), float(turn["end"]))
        if end > start:
            speaker = str(turn["speaker"])
            overlaps[speaker] = overlaps.get(speaker, 0.0) + end - start
    if not overlaps:
        return None
    ranked = sorted(overlaps.items(), key=lambda item: item[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _temporal_distance(word: dict, turn: dict) -> float:
    word_start = float(word["start"])
    word_end = float(word["end"])
    turn_start = float(turn["start"])
    turn_end = float(turn["end"])
    if word_end < turn_start:
        return turn_start - word_end
    if turn_end < word_start:
        return word_start - turn_end
    return 0.0


def _nearest_speakers(word: dict, turns: list[dict]) -> list[str]:
    distances: dict[str, float] = {}
    for turn in turns:
        speaker = str(turn["speaker"])
        distance = _temporal_distance(word, turn)
        distances[speaker] = min(distance, distances.get(speaker, distance))
    nearest_distance = min(distances.values())
    return sorted(
        speaker for speaker, distance in distances.items() if distance == nearest_distance
    )


def _infer_speaker_for_word(
    word: dict,
    words: list[dict],
    word_index: int,
    turns: list[dict],
) -> str:
    candidates = _nearest_speakers(word, turns)
    for index in range(word_index - 1, -1, -1):
        previous_speaker = words[index].get("speaker")
        if previous_speaker in candidates:
            return previous_speaker
    for index in range(word_index + 1, len(words)):
        next_speaker = words[index].get("speaker")
        if next_speaker in candidates:
            return next_speaker
    return candidates[0]


def attribute_words(words: list[dict], turns: list[dict]) -> AttributionResult:
    attributed = [{**word, "speaker": _speaker_for_word(word, turns)} for word in words]
    inferred_word_count = 0
    for index, word in enumerate(attributed):
        if word["speaker"] is None:
            word["speaker"] = _infer_speaker_for_word(word, attributed, index, turns)
            inferred_word_count += 1
    attributed_count = sum(word["speaker"] is not None for word in attributed)
    return AttributionResult(
        words=attributed,
        statistics={
            "word_count": len(words),
            "attributed_word_count": attributed_count,
            "unattributed_word_count": len(words) - attributed_count,
            "inferred_word_count": inferred_word_count,
        },
    )
