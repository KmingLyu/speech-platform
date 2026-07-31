from pathlib import Path

from .config import Settings
from .exporter import export_result
from .processor import ArtifactWriter, JobLifecycle
from .repository import cancel_if_requested, complete_job, fail_job, heartbeat_job, update_job


class PostgresJobLifecycle(JobLifecycle):
    def __init__(self, settings: Settings):
        self.settings = settings

    def update(self, job_id: str, **changes) -> None:
        update_job(self.settings, job_id, **changes)

    def heartbeat(self, job_id: str) -> None:
        heartbeat_job(self.settings, job_id)

    def cancel_if_requested(self, job_id: str) -> bool:
        return cancel_if_requested(self.settings, job_id)

    def complete(
        self,
        job_id: str,
        *,
        text: str,
        artifacts: dict[str, str],
    ) -> None:
        complete_job(
            self.settings,
            job_id,
            text=text,
            artifacts=artifacts,
        )

    def fail(self, job_id: str, code: str, message: str, *, retryable: bool) -> None:
        fail_job(self.settings, job_id, code, message, retryable=retryable)


class FilesystemArtifactWriter(ArtifactWriter):
    def write(
        self,
        job_id: str,
        *,
        output_dir: Path,
        text: str,
        language: str | None,
        duration: float,
        model: str,
        output_script: str,
        segments: list[dict],
        formats: tuple[str, ...],
        job_type: str = "transcription",
        metadata: dict | None = None,
    ) -> dict[str, Path]:
        return export_result(
            job_id,
            output_dir=output_dir,
            text=text,
            language=language,
            duration=duration,
            model=model,
            output_script=output_script,
            segments=segments,
            formats=formats,
            job_type=job_type,
            metadata=metadata,
        )

    def discard(self, output_dir: Path) -> None:
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)
