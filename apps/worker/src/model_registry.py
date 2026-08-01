from pathlib import Path

from .config import Settings


def pinned_model_path(settings: Settings) -> Path:
    if not settings.diarization_model_revision:
        raise RuntimeError("DIARIZATION_MODEL_REVISION must be configured")
    return settings.model_root / "diarization" / settings.diarization_model_revision


def validate_pinned_model(settings: Settings) -> Path:
    """Fail worker startup unless the configured immutable model directory exists."""
    path = pinned_model_path(settings)
    if not path.is_dir():
        raise RuntimeError(f"Pinned diarization model is missing: {path}")
    return path


def download_pinned_model(settings: Settings) -> Path:
    """Download one revision into its own persistent directory for deployment."""
    path = pinned_model_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir() and any(path.iterdir()):
        return path
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=settings.diarization_model,
        revision=settings.diarization_model_revision,
        local_dir=str(path),
        token=None,
    )
    return validate_pinned_model(settings)
