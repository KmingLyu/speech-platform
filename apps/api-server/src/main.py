import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from .config import (
    DEFAULT_MODEL,
    SUPPORTED_OUTPUT_FORMATS,
    Settings,
    load_settings,
)
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
    host = (parsed.hostname or "").lower().rstrip(".")
    hosts = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
    query = parse_qs(parsed.query, keep_blank_values=True)
    is_watch = parsed.path == "/watch" and len(query.get("v", [])) == 1
    is_short_link = host == "youtu.be" and len(parsed.path.strip("/").split("/")) == 1
    path_parts = [part for part in parsed.path.split("/") if part]
    is_video_path = (
        host != "youtu.be"
        and len(path_parts) == 2
        and path_parts[0] in {"shorts", "live", "embed"}
        and bool(path_parts[1])
    )
    if (
        parsed.scheme not in {"http", "https"}
        or host not in hosts
        or not (is_watch or is_short_link or is_video_path)
        or any(key in query for key in {"list", "index", "channel", "search_query"})
    ):
        raise HTTPException(
            422,
            detail={
                "code": "youtube_url_not_supported",
                "message": "youtube_url must be a public single-video YouTube URL",
            },
        )


SUPPORTED_LANGUAGES = frozenset(
    "af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw he hi hr ht hu hy id is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl nn no oc pa pl ps pt ro ru sa sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz vi yi yo zh".split()
) | frozenset({"zh-tw", "zh-cn"})


def normalize_language(language: str | None) -> str | None:
    if language is None or not language.strip():
        return None
    normalized = language.strip().lower().replace("_", "-")
    if normalized not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            422,
            detail={"code": "language_not_supported", "message": "Unsupported language"},
        )
    return normalized


def normalize_formats(formats: list[str] | None) -> tuple[str, ...]:
    requested = formats or ["json", "txt", "srt"]
    normalized = tuple(dict.fromkeys(value.strip().lower() for value in requested))
    if not normalized or any(value not in SUPPORTED_OUTPUT_FORMATS for value in normalized):
        raise HTTPException(
            422,
            detail={"code": "format_not_supported", "message": "Unsupported output format"},
        )
    return normalized


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _error(code: str, message: str, details: object | None = None) -> dict:
    payload: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return {"error": payload}


def job_payload(job: dict) -> dict:
    completed = job["status"] == "completed"
    output_formats = set(job.get("output_formats") or ("json", "txt", "srt"))
    return {
        "id": job["id"],
        "status": job["status"],
        "current_stage": job["current_stage"],
        "progress": job["progress"],
        "source": {"type": job["source_type"]},
        "configuration": {
            "model": job["model"],
            "language": job["language"],
            "output_script": job["output_script"],
            "formats": sorted(output_formats),
        },
        "timing": {
            "duration": job["duration"],
            "processed_seconds": job["processed_seconds"],
            "created_at": _timestamp(job["created_at"]),
            "started_at": _timestamp(job["started_at"]),
            "completed_at": _timestamp(job["completed_at"]),
        },
        "error": (
            {"code": job["error_code"], "message": job["error_message"]}
            if job["error_code"]
            else None
        ),
        "artifacts": {
            "json": completed and "json" in output_formats and bool(job["result_json_path"]),
            "txt": completed and "txt" in output_formats and bool(job["result_txt_path"]),
            "srt": completed and "srt" in output_formats and bool(job["result_srt_path"]),
        },
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

    @application.exception_handler(HTTPException)
    async def structured_http_error(_request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
        return JSONResponse(
            status_code=exc.status_code,
            content=_error("http_error", "The request could not be completed."),
        )

    @application.exception_handler(RequestValidationError)
    async def structured_validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse(status_code=422, content=_error("invalid_request", "Invalid request"))

    @application.exception_handler(Exception)
    async def structured_internal_error(_request: Request, _exc: Exception):
        return JSONResponse(
            status_code=500,
            content=_error("internal_error", "The server could not complete the request."),
        )

    @application.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @application.post("/v1/transcriptions", status_code=202)
    async def create_transcription(
        file: Annotated[UploadFile | None, File()] = None,
        youtube_url: Annotated[str | None, Form()] = None,
        language: Annotated[str | None, Form()] = None,
        model: Annotated[str, Form()] = DEFAULT_MODEL,
        formats: Annotated[list[str] | None, Form()] = None,
    ):
        if (file is None) == (youtube_url is None):
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_source",
                    "message": "Provide exactly one of file or youtube_url",
                },
            )
        if youtube_url:
            ensure_youtube_url(youtube_url)
        normalized_language = normalize_language(language)
        if model not in resolved_settings.supported_models:
            raise HTTPException(
                422,
                detail={"code": "model_not_supported", "message": "Unsupported model"},
            )
        normalized_formats = normalize_formats(formats)

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
                    language=normalized_language,
                    output_script=output_script_for(normalized_language),
                    output_formats=normalized_formats,
                )
            )
        except UploadTooLarge:
            job_storage.remove_job(job_id)
            raise HTTPException(
                413,
                detail={
                    "code": "upload_too_large",
                    "message": "Uploaded file exceeds the configured upload limit",
                },
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
            raise HTTPException(
                404,
                detail={"code": "job_not_found", "message": "Transcription job not found"},
            )
        if format is None:
            return job_payload(job)
        if job["status"] != "completed":
            raise HTTPException(
                409,
                detail={"code": "result_not_ready", "message": "Result is not ready"},
            )

        file_metadata = {
            "json": ("application/json", "result.json"),
            "txt": ("text/plain; charset=utf-8", "transcript.txt"),
            "srt": ("application/x-subrip", "transcript.srt"),
        }
        media_type, filename = file_metadata[format]
        result_path = job_storage.artifact_path(job, format)
        if result_path is None or not result_path.is_file():
            raise HTTPException(
                404,
                detail={"code": "artifact_not_found", "message": "Artifact is unavailable"},
            )
        return FileResponse(result_path, media_type=media_type, filename=filename)

    return application


app = create_app()
