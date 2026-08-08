from pathlib import Path

from .adapters import FilesystemArtifactWriter, PostgresJobLifecycle
from .config import Settings
from .media import normalize_audio, probe_duration
from .processor import (
    MediaProcessor,
    SourceAcquirer,
    TranscriptConverter,
    TranscriptionEngine,
    WorkerDependencies,
)
from .script_converter import convert_transcript
from .source import acquire_source
from .transcriber import Transcriber
from .diarizer import PyannoteCommunityDiarization
from .device import InferenceDevices
from .alignment import ForcedAlignmentWithWhisperFallback, WhisperWordAlignment


class ProductionSourceAcquirer(SourceAcquirer):
    def acquire(self, job: dict, job_root: Path) -> Path:
        return acquire_source(job, job_root)


class FfmpegMediaProcessor(MediaProcessor):
    def probe_duration(self, source_path: Path) -> float:
        return probe_duration(source_path)

    def normalize_audio(self, source_path: Path, output_path: Path) -> Path:
        return normalize_audio(source_path, output_path)


class ProductionTranscriptConverter(TranscriptConverter):
    def convert(
        self,
        text: str,
        segments: list[dict],
        language: str | None,
    ) -> tuple[str, list[dict]]:
        return convert_transcript(text, segments, language)


def production_dependencies(
    settings: Settings,
    devices: InferenceDevices,
) -> WorkerDependencies:
    transcription: TranscriptionEngine = Transcriber(
        settings,
        devices.transcription,
        allow_runtime_fallback=devices.allow_runtime_fallback,
    )
    return WorkerDependencies(
        jobs=PostgresJobLifecycle(settings),
        sources=ProductionSourceAcquirer(),
        media=FfmpegMediaProcessor(),
        transcription=transcription,
        converter=ProductionTranscriptConverter(),
        artifacts=FilesystemArtifactWriter(),
        alignment=(
            WhisperWordAlignment()
            if settings.alignment_strategy == "whisper_word_timestamps"
            else ForcedAlignmentWithWhisperFallback(None, WhisperWordAlignment())
        ),
        diarization=PyannoteCommunityDiarization(
            model=settings.diarization_model,
            revision=settings.diarization_model_revision,
            model_root=settings.model_root,
            device=devices.diarization,
            allow_runtime_fallback=devices.allow_runtime_fallback,
        ),
    )
