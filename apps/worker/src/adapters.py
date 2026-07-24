from pathlib import Path

from .config import Settings
from .exporter import export_result
from .processor import ArtifactWriter, JobLifecycle
from .repository import complete_job, fail_job, update_job


class PostgresJobLifecycle(JobLifecycle):
    def __init__(self, settings: Settings):
        self.settings = settings

    def update(self, job_id: str, **changes) -> None:
        update_job(self.settings, job_id, **changes)

    def complete(
        self,
        job_id: str,
        *,
        text: str,
        json_path: str,
        txt_path: str,
        srt_path: str,
    ) -> None:
        complete_job(
            self.settings,
            job_id,
            text=text,
            json_path=json_path,
            txt_path=txt_path,
            srt_path=srt_path,
        )

    def fail(self, job_id: str, code: str, message: str) -> None:
        fail_job(self.settings, job_id, code, message)


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
    ) -> tuple[Path, Path, Path]:
        return export_result(
            job_id,
            output_dir=output_dir,
            text=text,
            language=language,
            duration=duration,
            model=model,
            output_script=output_script,
            segments=segments,
        )
