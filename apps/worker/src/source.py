from pathlib import Path

from yt_dlp import YoutubeDL


class SourceError(RuntimeError):
    pass


def acquire_source(job: dict, job_root: Path) -> Path:
    if job["source_type"] == "upload":
        path = Path(job["source_path"])
        if not path.is_file():
            raise SourceError("Uploaded source file is missing")
        return path

    if job["source_type"] != "youtube" or not job["source_url"]:
        raise SourceError("Unsupported or incomplete source configuration")

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
        raise SourceError(f"YouTube download failed: {error}") from error

    files = [path for path in source_dir.iterdir() if path.is_file()]
    if len(files) != 1:
        raise SourceError("YouTube download did not produce exactly one source file")
    return files[0]
