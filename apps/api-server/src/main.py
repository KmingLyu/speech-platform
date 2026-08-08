import base64
import binascii
import json
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
from .language import OutputScript, convert_text, output_script_for
from .migrations import run_migrations
from .ports import JobRepository, JobStorage, NewTranscriptionJob, UploadTooLarge
from .storage import LocalJobStorage

MigrationRunner = Callable[[], None]
PUBLIC_STATUSES = frozenset(
    {"queued", "processing", "completed", "failed", "cancel_requested", "canceled"}
)
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
MAX_HOTWORDS = 100
MAX_HOTWORD_LENGTH = 50


JOB_TYPE_PREFIXES = {"transcription": "tr_", "diarization": "di_"}


def new_job_id(job_type: str = "transcription") -> str:
    return f"{JOB_TYPE_PREFIXES[job_type]}{secrets.token_urlsafe(18)}"


def require_job(job_repository: JobRepository, job_id: str, job_type: str) -> dict:
    job = job_repository.get(job_id)
    if (
        job is None
        or not job_id.startswith(JOB_TYPE_PREFIXES[job_type])
        or job.get("job_type", "transcription") != job_type
    ):
        raise HTTPException(
            404,
            detail={
                "code": "job_not_found",
                "message": f"{job_type.capitalize()} job not found",
            },
        )
    return job


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


def normalize_hotwords(
    hotwords: list[str] | None, output_script: OutputScript
) -> tuple[str, ...]:
    """Validate the requested Hotwords and convert them to the job's output script.

    Converting here, rather than in the Worker, keeps the stored list identical to
    what the recognizer is biased toward, so the job's configuration can echo it.
    """
    requested = hotwords or []
    if len(requested) > MAX_HOTWORDS:
        raise HTTPException(
            422,
            detail={
                "code": "invalid_hotwords",
                "message": f"hotwords must contain at most {MAX_HOTWORDS} entries",
            },
        )
    trimmed = [value.strip() for value in requested]
    if any(not value for value in trimmed):
        raise HTTPException(
            422,
            detail={"code": "invalid_hotwords", "message": "hotwords must not be empty"},
        )
    if any(len(value) > MAX_HOTWORD_LENGTH for value in trimmed):
        raise HTTPException(
            422,
            detail={
                "code": "invalid_hotwords",
                "message": f"each hotword must be at most {MAX_HOTWORD_LENGTH} characters",
            },
        )
    return tuple(convert_text(value, output_script) for value in trimmed)


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _error(code: str, message: str, details: object | None = None) -> dict:
    payload: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return {"error": payload}


def encode_cursor(created_at: datetime, job_id: str) -> str:
    payload = json.dumps(
        {"created_at": created_at.astimezone(UTC).isoformat(), "id": job_id},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if (
            not isinstance(payload, dict)
            or set(payload) != {"created_at", "id"}
            or not isinstance(payload["id"], str)
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None or not payload["id"]:
            raise ValueError
        return created_at.astimezone(UTC), payload["id"]
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeDecodeError,
    ):
        raise HTTPException(
            400,
            detail={"code": "invalid_cursor", "message": "Invalid pagination cursor"},
        ) from None


def parse_list_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise HTTPException(
            400,
            detail={"code": "invalid_limit", "message": "limit must be between 1 and 100"},
        ) from None
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise HTTPException(
            400,
            detail={"code": "invalid_limit", "message": "limit must be between 1 and 100"},
        )
    return limit


def failure_payload(job: dict) -> dict | None:
    if not job.get("error_code"):
        return None
    return {
        "code": job["error_code"],
        "message": job["error_message"],
        "retryable": bool(job.get("error_retryable")),
    }


def attempts_payload(job: dict) -> dict:
    return {
        "count": job.get("attempt_count") or 0,
        "automatic_count": job.get("automatic_attempt_count") or 0,
    }


def job_configuration(job: dict) -> dict:
    output_formats = set(job.get("output_formats") or ("json", "txt", "srt"))
    configuration = {
        "model": job["model"],
        "language": job["language"],
        "output_script": job["output_script"],
        "formats": sorted(output_formats),
    }
    if job.get("job_type") == "diarization":
        configuration.update({
            "min_speakers": job.get("min_speakers"),
            "max_speakers": job.get("max_speakers"),
            "diarization_model": job.get("diarization_model"),
            "diarization_model_revision": job.get("diarization_model_revision"),
            "max_chars_per_line": job.get("max_chars_per_line"),
        })
    else:
        configuration["hotwords"] = list(job.get("hotwords") or ())
    return configuration


def job_summary(job: dict) -> dict:
    resource = "diarizations" if job.get("job_type", "transcription") == "diarization" else "transcriptions"
    output_formats = set(job.get("output_formats") or ("json", "txt", "srt"))
    completed = job["status"] == "completed"
    artifact_columns = {
        "json": "result_json_path",
        "txt": "result_txt_path",
        "srt": "result_srt_path",
    }
    available_formats = {
        format for format in output_formats
        if job.get(artifact_columns[format])
    }
    source = {"type": job["source_type"]}
    if job.get("original_filename"):
        source["filename"] = job["original_filename"]
    if job.get("source_url"):
        source["url"] = job["source_url"]
    return {
        "id": job["id"],
        "job_type": job.get("job_type", "transcription"),
        "status": job["status"],
        "current_stage": job["current_stage"],
        "progress": job["progress"],
        "source": source,
        "configuration": job_configuration(job),
        "timing": {
            "duration": job["duration"],
            "processed_seconds": job["processed_seconds"],
            "created_at": _timestamp(job["created_at"]),
            "started_at": _timestamp(job["started_at"]),
            "completed_at": _timestamp(job["completed_at"]),
        },
        "attempts": attempts_payload(job),
        "error": failure_payload(job),
        "artifacts": {
            "json": completed and "json" in output_formats and bool(job.get("result_json_path")),
            "txt": completed and "txt" in output_formats and bool(job.get("result_txt_path")),
            "srt": completed and "srt" in output_formats and bool(job.get("result_srt_path")),
        },
        "links": {
            "self": f"/v1/{resource}/{job['id']}",
            "artifacts": {
                format: f"/v1/{resource}/{job['id']}?format={format}"
                for format in sorted(available_formats)
            } if completed else {},
        },
    }


def job_payload(job: dict) -> dict:
    resource = "diarizations" if job.get("job_type", "transcription") == "diarization" else "transcriptions"
    completed = job["status"] == "completed"
    output_formats = set(job.get("output_formats") or ("json", "txt", "srt"))
    artifact_links = {
        format: f"/v1/{resource}/{job['id']}?format={format}"
        for format in sorted(output_formats)
    } if completed else {}
    return {
        "id": job["id"],
        "job_type": job.get("job_type", "transcription"),
        "status": job["status"],
        "current_stage": job["current_stage"],
        "progress": job["progress"],
        "source": {"type": job["source_type"]},
        "configuration": job_configuration(job),
        "timing": {
            "duration": job["duration"],
            "processed_seconds": job["processed_seconds"],
            "created_at": _timestamp(job["created_at"]),
            "started_at": _timestamp(job["started_at"]),
            "completed_at": _timestamp(job["completed_at"]),
        },
        "attempts": attempts_payload(job),
        "error": failure_payload(job),
        "artifacts": {
            "json": completed and "json" in output_formats and bool(job["result_json_path"]),
            "txt": completed and "txt" in output_formats and bool(job["result_txt_path"]),
            "srt": completed and "srt" in output_formats and bool(job["result_srt_path"]),
        },
        "links": {
            "self": f"/v1/{resource}/{job['id']}",
            "artifacts": artifact_links,
        },
    }


def normalize_speaker_bounds(min_speakers: int | None, max_speakers: int | None) -> tuple[int | None, int | None]:
    if min_speakers is not None and min_speakers < 1:
        raise HTTPException(422, detail={"code": "invalid_speaker_bounds", "message": "min_speakers must be positive"})
    if max_speakers is not None and max_speakers < 1:
        raise HTTPException(422, detail={"code": "invalid_speaker_bounds", "message": "max_speakers must be positive"})
    if min_speakers is not None and max_speakers is not None and min_speakers > max_speakers:
        raise HTTPException(422, detail={"code": "invalid_speaker_bounds", "message": "min_speakers must not exceed max_speakers"})
    return min_speakers, max_speakers


def normalize_max_chars_per_line(value: int | None) -> int:
    resolved = 20 if value is None else value
    if resolved < 1:
        raise HTTPException(422, detail={"code": "invalid_max_chars_per_line", "message": "max_chars_per_line must be positive"})
    return resolved


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
        title="Speech Platform API",
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
        hotwords: Annotated[list[str] | None, Form()] = None,
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
        output_script = output_script_for(normalized_language)
        normalized_hotwords = normalize_hotwords(hotwords, output_script)

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
                    job_type="transcription",
                    source_type="upload" if file else "youtube",
                    source_url=youtube_url,
                    original_filename=filename,
                    source_path=source_path,
                    model=model,
                    language=normalized_language,
                    output_script=output_script,
                    output_formats=normalized_formats,
                    hotwords=normalized_hotwords,
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

    @application.post("/v1/diarizations", status_code=202)
    async def create_diarization(
        file: Annotated[UploadFile | None, File()] = None,
        youtube_url: Annotated[str | None, Form()] = None,
        language: Annotated[str | None, Form()] = None,
        model: Annotated[str, Form()] = DEFAULT_MODEL,
        formats: Annotated[list[str] | None, Form()] = None,
        min_speakers: Annotated[int | None, Form()] = None,
        max_speakers: Annotated[int | None, Form()] = None,
        max_chars_per_line: Annotated[int | None, Form()] = None,
    ):
        if (file is None) == (youtube_url is None):
            raise HTTPException(422, detail={"code": "invalid_source", "message": "Provide exactly one of file or youtube_url"})
        if youtube_url:
            ensure_youtube_url(youtube_url)
        normalized_language = normalize_language(language)
        if model not in resolved_settings.supported_models:
            raise HTTPException(422, detail={"code": "model_not_supported", "message": "Unsupported model"})
        normalized_formats = normalize_formats(formats)
        min_speakers, max_speakers = normalize_speaker_bounds(min_speakers, max_speakers)
        max_chars_per_line = normalize_max_chars_per_line(max_chars_per_line)
        if not resolved_settings.diarization_model_revision:
            raise HTTPException(
                503,
                detail={
                    "code": "diarization_model_unavailable",
                    "message": "Diarization is not configured with a pinned model revision",
                },
            )
        job_id = new_job_id("diarization")
        filename: str | None = None
        source_path: str | None = None
        try:
            if file:
                stored = await job_storage.store_upload(job_id, file, resolved_settings.max_upload_size_bytes)
                filename, source_path = stored.filename, str(stored.path)
            job_repository.create(NewTranscriptionJob(
                id=job_id, job_type="diarization",
                source_type="upload" if file else "youtube", source_url=youtube_url,
                original_filename=filename, source_path=source_path, model=model,
                language=normalized_language, output_script=output_script_for(normalized_language),
                output_formats=normalized_formats, min_speakers=min_speakers,
                max_speakers=max_speakers,
                diarization_model=resolved_settings.diarization_model,
                diarization_model_revision=resolved_settings.diarization_model_revision,
                max_chars_per_line=max_chars_per_line,
            ))
        except UploadTooLarge:
            job_storage.remove_job(job_id)
            raise HTTPException(413, detail={"code": "upload_too_large", "message": "Uploaded file exceeds the configured upload limit"}) from None
        except Exception:
            job_storage.remove_job(job_id)
            raise
        finally:
            if file:
                await file.close()
        return JSONResponse(
            status_code=202,
            content={"id": job_id, "status": "queued", "created_at": datetime.now(UTC).isoformat(), "links": {"self": f"/v1/diarizations/{job_id}"}},
            headers={"Location": f"/v1/diarizations/{job_id}"},
        )

    @application.get("/v1/transcriptions")
    def list_transcriptions(
        status: str | None = None,
        limit: str = str(DEFAULT_LIST_LIMIT),
        cursor: str | None = None,
    ):
        if status is not None and status not in PUBLIC_STATUSES:
            raise HTTPException(
                400,
                detail={"code": "invalid_status", "message": "Unsupported job status"},
            )
        page_limit = parse_list_limit(limit)
        before = decode_cursor(cursor) if cursor is not None else None
        page = job_repository.list(
            job_type="transcription", status=status, before=before, limit=page_limit
        )
        has_next = len(page) > page_limit
        items = page[:page_limit]
        next_cursor = (
            encode_cursor(items[-1]["created_at"], items[-1]["id"])
            if has_next and items
            else None
        )
        return {"items": [job_summary(job) for job in items], "next_cursor": next_cursor}

    @application.get("/v1/diarizations")
    def list_diarizations(status: str | None = None, limit: str = str(DEFAULT_LIST_LIMIT), cursor: str | None = None):
        if status is not None and status not in PUBLIC_STATUSES:
            raise HTTPException(400, detail={"code": "invalid_status", "message": "Unsupported job status"})
        page_limit = parse_list_limit(limit)
        before = decode_cursor(cursor) if cursor is not None else None
        page = job_repository.list(job_type="diarization", status=status, before=before, limit=page_limit)
        items = page[:page_limit]
        return {
            "items": [job_summary(job) for job in items],
            "next_cursor": encode_cursor(items[-1]["created_at"], items[-1]["id"]) if len(page) > page_limit and items else None,
        }

    @application.get("/v1/transcriptions/{job_id}")
    def get_transcription(
        job_id: str,
        format: Literal["json", "txt", "srt"] | None = None,
    ):
        job = require_job(job_repository, job_id, "transcription")
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

    @application.post("/v1/transcriptions/{job_id}/retry", status_code=202)
    def retry_transcription(job_id: str):
        require_job(job_repository, job_id, "transcription")
        requeued = job_repository.retry(job_id)
        if requeued is None:
            raise HTTPException(
                409,
                detail={
                    "code": "job_not_retryable",
                    "message": "Transcription job cannot be retried",
                },
            )
        return JSONResponse(
            status_code=202,
            content=job_payload(requeued),
            headers={"Location": f"/v1/transcriptions/{job_id}"},
        )

    @application.post("/v1/transcriptions/{job_id}/cancel")
    def cancel_transcription(job_id: str):
        require_job(job_repository, job_id, "transcription")
        canceled = job_repository.cancel(job_id)
        if canceled is None:
            raise HTTPException(
                409,
                detail={
                    "code": "job_not_cancelable",
                    "message": "Transcription job cannot be canceled",
                },
            )
        if canceled["status"] == "canceled":
            return JSONResponse(status_code=200, content=job_payload(canceled))
        return JSONResponse(
            status_code=202,
            content=job_payload(canceled),
            headers={"Location": f"/v1/transcriptions/{job_id}"},
        )

    @application.delete("/v1/transcriptions/{job_id}", status_code=204)
    def delete_transcription(job_id: str):
        job = require_job(job_repository, job_id, "transcription")
        if job["status"] not in {"completed", "failed", "canceled"}:
            raise HTTPException(
                409,
                detail={
                    "code": "job_not_terminal",
                    "message": "Transcription job must be terminal before deletion",
                },
            )
        # Keep metadata if filesystem cleanup fails; the job can then be retried.
        job_storage.remove_job(job_id)
        deleted = job_repository.delete(job_id)
        if deleted is None:
            raise HTTPException(
                404,
                detail={
                    "code": "job_not_found",
                    "message": "Transcription job not found",
                },
            )
        return None

    @application.get("/v1/diarizations/{job_id}")
    def get_diarization(job_id: str, format: Literal["json", "txt", "srt"] | None = None):
        job = require_job(job_repository, job_id, "diarization")
        if format is None:
            return job_payload(job)
        if job["status"] != "completed":
            raise HTTPException(409, detail={"code": "result_not_ready", "message": "Result is not ready"})
        file_metadata = {
            "json": ("application/json", "result.json"),
            "txt": ("text/plain; charset=utf-8", "diarized-transcript.txt"),
            "srt": ("application/x-subrip", "diarized-transcript.srt"),
        }
        media_type, filename = file_metadata[format]
        result_path = job_storage.artifact_path(job, format)
        if result_path is None or not result_path.is_file():
            raise HTTPException(404, detail={"code": "artifact_not_found", "message": "Artifact is unavailable"})
        return FileResponse(result_path, media_type=media_type, filename=filename)

    @application.post("/v1/diarizations/{job_id}/retry", status_code=202)
    def retry_diarization(job_id: str):
        require_job(job_repository, job_id, "diarization")
        requeued = job_repository.retry(job_id)
        if requeued is None:
            raise HTTPException(409, detail={"code": "job_not_retryable", "message": "Diarization job cannot be retried"})
        return JSONResponse(status_code=202, content=job_payload(requeued), headers={"Location": f"/v1/diarizations/{job_id}"})

    @application.post("/v1/diarizations/{job_id}/cancel")
    def cancel_diarization(job_id: str):
        require_job(job_repository, job_id, "diarization")
        canceled = job_repository.cancel(job_id)
        if canceled is None:
            raise HTTPException(409, detail={"code": "job_not_cancelable", "message": "Diarization job cannot be canceled"})
        if canceled["status"] == "canceled":
            return JSONResponse(status_code=200, content=job_payload(canceled))
        return JSONResponse(status_code=202, content=job_payload(canceled), headers={"Location": f"/v1/diarizations/{job_id}"})

    @application.delete("/v1/diarizations/{job_id}", status_code=204)
    def delete_diarization(job_id: str):
        job = require_job(job_repository, job_id, "diarization")
        if job["status"] not in {"completed", "failed", "canceled"}:
            raise HTTPException(409, detail={"code": "job_not_terminal", "message": "Diarization job must be terminal before deletion"})
        job_storage.remove_job(job_id)
        if job_repository.delete(job_id) is None:
            raise HTTPException(404, detail={"code": "job_not_found", "message": "Diarization job not found"})
        return None

    return application


app = create_app()
