import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .config import Settings, load_settings
from .db import PostgresJobRepository
from .language import output_script_for
from .migrations import run_migrations
from .ports import JobRepository, JobStorage, NewTranscriptionJob, UploadTooLarge
from .storage import LocalJobStorage

MigrationRunner = Callable[[], None]


def new_job_id() -> str:
    return f"tr_{secrets.token_urlsafe(18)}"


def ensure_youtube_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(422, "youtube_url must be a valid http(s) URL")


def job_payload(job: dict) -> dict:
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "current_stage": job["current_stage"],
        "source_type": job["source_type"],
        "model": job["model"],
        "language": job["language"],
        "output_script": job["output_script"],
        "duration": job["duration"],
        "processed_seconds": job["processed_seconds"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "completed_at": job["completed_at"],
        "error": (
            {"code": job["error_code"], "message": job["error_message"]}
            if job["error_code"]
            else None
        ),
        "result": (
            {"text": job["result_text"], "available_formats": ["json", "txt", "srt"]}
            if job["status"] == "completed"
            else None
        ),
    }


def create_app(
    *,
    settings: Settings | None = None,
    jobs: JobRepository | None = None,
    storage: JobStorage | None = None,
    migrate: MigrationRunner | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    job_repository = jobs or PostgresJobRepository(resolved_settings)
    job_storage = storage or LocalJobStorage(resolved_settings.data_root)
    migration_runner = migrate or (
        lambda: run_migrations(resolved_settings.database_url)
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        migration_runner()
        yield

    application = FastAPI(
        title="Speech ASR Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @application.post("/v1/transcriptions", status_code=202)
    async def create_transcription(
        file: Annotated[UploadFile | None, File()] = None,
        youtube_url: Annotated[str | None, Form()] = None,
        language: Annotated[str | None, Form()] = None,
        model: Annotated[str, Form()] = "large-v3-turbo",
    ):
        if (file is None) == (youtube_url is None):
            raise HTTPException(422, "Provide exactly one of file or youtube_url")
        if youtube_url:
            ensure_youtube_url(youtube_url)

        job_id = new_job_id()
        filename: str | None = None
        source_path: str | None = None
        try:
            if file:
                stored = await job_storage.store_upload(
                    job_id,
                    file,
                    resolved_settings.max_upload_size_bytes,
                )
                filename = stored.filename
                source_path = str(stored.path)
            job_repository.create(
                NewTranscriptionJob(
                    id=job_id,
                    source_type="upload" if file else "youtube",
                    source_url=youtube_url,
                    original_filename=filename,
                    source_path=source_path,
                    model=model,
                    language=language,
                    output_script=output_script_for(language),
                )
            )
        except UploadTooLarge:
            job_storage.remove_job(job_id)
            raise HTTPException(
                413,
                "Uploaded file exceeds MAX_UPLOAD_SIZE_MB",
            ) from None
        except Exception:
            job_storage.remove_job(job_id)
            raise
        finally:
            if file:
                await file.close()

        return JSONResponse(
            status_code=202,
            content={
                "id": job_id,
                "status": "queued",
                "created_at": datetime.now(UTC).isoformat(),
                "links": {"self": f"/v1/transcriptions/{job_id}"},
            },
            headers={"Location": f"/v1/transcriptions/{job_id}"},
        )

    @application.get("/v1/transcriptions/{job_id}")
    def get_transcription(
        job_id: str,
        format: Literal["json", "txt", "srt"] | None = None,
    ):
        job = job_repository.get(job_id)
        if job is None:
            raise HTTPException(404, "Transcription job not found")
        if format is None:
            return job_payload(job)
        if job["status"] != "completed":
            raise HTTPException(409, "Result is not ready")

        file_metadata = {
            "json": ("application/json", "result.json"),
            "txt": ("text/plain; charset=utf-8", "transcript.txt"),
            "srt": ("application/x-subrip", "transcript.srt"),
        }
        media_type, filename = file_metadata[format]
        result_path = job_storage.artifact_path(job, format)
        if result_path is None or not result_path.is_file():
            raise HTTPException(404, f"{format} artifact is unavailable")
        return FileResponse(result_path, media_type=media_type, filename=filename)

    return application


app = create_app()
