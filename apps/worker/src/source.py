from pathlib import Path

from yt_dlp import YoutubeDL

from .failures import (
    PermanentFailure,
    download_failure,
    source_download_failed,
    source_unavailable,
)


def acquire_source(job: dict, job_root: Path) -> Path:
    if job["source_type"] == "upload":
        path = Path(job["source_path"])
        if not path.is_file():
            raise source_unavailable(f"Uploaded source file is missing: {path}")
        return path

    if job["source_type"] != "youtube" or not job["source_url"]:
        raise PermanentFailure(
            "invalid_source_configuration",
            "The job source configuration is incomplete.",
            detail=f"Unsupported source configuration: {job['source_type']}",
        )

    source_dir = job_root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(source_dir / "youtube.%(ext)s")
    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with YoutubeDL(options) as downloader:
            downloader.download([job["source_url"]])
    except Exception as error:
        raise download_failure(f"YouTube download failed: {error}") from error

    files = [path for path in source_dir.iterdir() if path.is_file()]
    if len(files) != 1:
        raise source_download_failed(
            f"YouTube download produced {len(files)} files in {source_dir}"
        )
    return files[0]
