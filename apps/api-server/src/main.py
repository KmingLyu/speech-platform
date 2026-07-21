import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .config import Settings, load_settings
from .db import connection, ensure_schema
from .language import output_script_for

app = FastAPI(title="Speech ASR Service", version="0.1.0")
settings: Settings = load_settings()


@app.on_event("startup")
def apply_schema_changes() -> None:
    ensure_schema(settings)


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


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/v1/transcriptions", status_code=202)
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
    output_script = output_script_for(language)
    job_root = settings.data_root / "jobs" / job_id
    source_path: Path | None = None
    filename: str | None = None

    try:
        if file:
            filename = Path(file.filename or "upload.bin").name
            source_dir = job_root / "source"
            source_dir.mkdir(parents=True, exist_ok=False)
            source_path = source_dir / filename
            written = 0
            with source_path.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    written += len(chunk)
                    if written > settings.max_upload_size_bytes:
                        source_path.unlink(missing_ok=True)
                        raise HTTPException(413, "Uploaded file exceeds MAX_UPLOAD_SIZE_MB")
                    output.write(chunk)

        with connection(settings) as conn:
            conn.execute(
                """
                INSERT INTO transcription_jobs
                    (id, status, source_type, source_url, original_filename, source_path, model, language, output_script)
                VALUES (%s, 'queued', %s, %s, %s, %s, %s, %s, %s)
                """,
                (job_id, "upload" if file else "youtube", youtube_url, filename,
                 str(source_path) if source_path else None, model, language, output_script),
            )
            conn.commit()
    except Exception:
        if job_root.exists():
            shutil.rmtree(job_root)
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


@app.get("/v1/transcriptions/{job_id}")
def get_transcription(
    job_id: str,
    format: Literal["json", "txt", "srt"] | None = None,
):
    with connection(settings) as conn:
        job = conn.execute("SELECT * FROM transcription_jobs WHERE id = %s", (job_id,)).fetchone()

    if job is None:
        raise HTTPException(404, "Transcription job not found")
    if format is None:
        return job_payload(job)
    if job["status"] != "completed":
        raise HTTPException(409, "Result is not ready")

    file_columns = {
        "json": ("result_json_path", "application/json", "result.json"),
        "txt": ("result_txt_path", "text/plain; charset=utf-8", "transcript.txt"),
        "srt": ("result_srt_path", "application/x-subrip", "transcript.srt"),
    }
    column, media_type, filename = file_columns[format]
    result_path = Path(job[column]) if job[column] else None
    if result_path is None or not result_path.is_file():
        raise HTTPException(404, f"{format} artifact is unavailable")
    return FileResponse(result_path, media_type=media_type, filename=filename)
