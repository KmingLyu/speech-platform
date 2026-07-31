from dataclasses import dataclass


@dataclass(frozen=True)
class AttributionResult:
    segments: list[dict]
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


def attribute_words(words: list[dict], turns: list[dict]) -> AttributionResult:
    attributed = [{**word, "speaker": _speaker_for_word(word, turns)} for word in words]
    segments: list[dict] = []
    for word in attributed:
        if segments and segments[-1]["speaker"] == word["speaker"]:
            segments[-1]["end"] = word["end"]
            segments[-1]["text"] += word["text"]
        else:
            segments.append({
                "id": len(segments),
                "start": word["start"],
                "end": word["end"],
                "speaker": word["speaker"],
                "text": word["text"].strip(),
            })
    attributed_count = sum(word["speaker"] is not None for word in attributed)
    return AttributionResult(
        segments=segments,
        statistics={
            "word_count": len(words),
            "attributed_word_count": attributed_count,
            "unattributed_word_count": len(words) - attributed_count,
        },
    )
