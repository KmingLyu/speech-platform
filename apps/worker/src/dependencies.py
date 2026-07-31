from pathlib import Path
from typing import cast

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
from .script_converter import OutputScript, convert_segments, convert_text
from .source import acquire_source
from .transcriber import Transcriber
from .diarizer import PyannoteCommunityDiarization
from .alignment import WhisperWordAlignment


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
        output_script: str,
    ) -> tuple[str, list[dict]]:
        script = cast(OutputScript, output_script)
        return (
            convert_text(text, script),
            convert_segments(segments, script),
        )


def production_dependencies(settings: Settings) -> WorkerDependencies:
    transcription: TranscriptionEngine = Transcriber(settings)
    return WorkerDependencies(
        jobs=PostgresJobLifecycle(settings),
        sources=ProductionSourceAcquirer(),
        media=FfmpegMediaProcessor(),
        transcription=transcription,
        converter=ProductionTranscriptConverter(),
        artifacts=FilesystemArtifactWriter(),
        alignment=WhisperWordAlignment(),
        diarization=PyannoteCommunityDiarization(),
    )
