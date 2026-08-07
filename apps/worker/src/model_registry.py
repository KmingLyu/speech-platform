from pathlib import Path

from .config import Settings


MODEL_CONFIG_FILENAME = "config.yaml"


def pinned_model_path(settings: Settings) -> Path:
    if not settings.diarization_model_revision:
        raise RuntimeError("DIARIZATION_MODEL_REVISION must be configured")
    return settings.model_root / "diarization" / settings.diarization_model_revision


def validate_pinned_model(settings: Settings) -> Path:
    """Fail worker startup unless the configured immutable model is complete."""
    path = pinned_model_path(settings)
    if not path.is_dir():
        raise RuntimeError(f"Pinned diarization model is missing: {path}")
    config_path = path / MODEL_CONFIG_FILENAME
    if not config_path.is_file():
        raise RuntimeError(f"Pinned diarization model is incomplete: missing {config_path}")
    return path


def download_pinned_model(settings: Settings) -> Path:
    """Download one revision into its own persistent directory for deployment."""
    path = pinned_model_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return validate_pinned_model(settings)
    except RuntimeError:
        # snapshot_download can resume an interrupted download into local_dir.
        # Do not mistake a partial directory for an installed model.
        pass
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=settings.diarization_model,
        revision=settings.diarization_model_revision,
        local_dir=str(path),
        token=None,
    )
    return validate_pinned_model(settings)
