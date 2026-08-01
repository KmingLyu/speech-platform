import logging
from pathlib import Path

from faster_whisper import WhisperModel

from .config import Settings
from .device import BackendDevice
from .script_converter import asr_language


logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(
        self,
        settings: Settings,
        device: BackendDevice,
        *,
        allow_runtime_fallback: bool,
    ):
        self.settings = settings
        self.device = device
        self.allow_runtime_fallback = allow_runtime_fallback
        self._models: dict[str, WhisperModel] = {}

    def _load_model(self, model_name: str) -> WhisperModel:
        try:
            return WhisperModel(
                model_name,
                device=self.device.device,
                compute_type=self.device.compute_type,
                download_root=str(self.settings.model_root),
            )
        except Exception:
            if self.device.device != "cuda" or not self.allow_runtime_fallback:
                raise
            logger.warning(
                "GPU initialization failed; falling back to CPU "
                "backend=faster-whisper model=%s device=cpu compute_type=int8",
                model_name,
                exc_info=True,
            )
            return WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                download_root=str(self.settings.model_root),
            )

    def transcribe(self, audio_path: Path, *, model_name: str, language: str | None) -> tuple[str, list[dict]]:
        model = self._models.get(model_name)
        if model is None:
            model = self._load_model(model_name)
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
