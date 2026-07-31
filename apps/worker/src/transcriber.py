from pathlib import Path

from faster_whisper import WhisperModel

from .config import Settings
from .script_converter import asr_language


class Transcriber:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._models: dict[str, WhisperModel] = {}

    def transcribe(self, audio_path: Path, *, model_name: str, language: str | None) -> tuple[str, list[dict]]:
        model = self._models.get(model_name)
        if model is None:
            model = WhisperModel(
                model_name,
                device="cuda",
                compute_type="float16",
                download_root=str(self.settings.model_root),
            )
            self._models[model_name] = model
        segments, _info = model.transcribe(
            str(audio_path), language=asr_language(language), vad_filter=True, beam_size=5,
            word_timestamps=True,
        )
        normalized = [
            {
                "id": index,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "words": [
                    {"start": word.start, "end": word.end, "text": word.word}
                    for word in (segment.words or [])
                ],
            }
            for index, segment in enumerate(segments)
        ]
        return "".join(segment["text"] for segment in normalized).strip(), normalized
