"""Resolve the built-in Breeze option to a reproducible, locally converted model."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .failures import RetryableFailure

BREEZE_MODEL = "breeze-asr-25"
BREEZE_REPOSITORY = "MediaTek-Research/Breeze-ASR-25"
BREEZE_REVISION = "cffe7ccb404d025296a00758d0a33468bec3a9d0"
BREEZE_BUILD = f"{BREEZE_REVISION}-ct2-fp16-v1"
REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
MANIFEST = {
    "model": BREEZE_MODEL,
    "repository": BREEZE_REPOSITORY,
    "revision": BREEZE_REVISION,
    "quantization": "float16",
    "build": BREEZE_BUILD,
}


def breeze_model_path(model_root: Path) -> Path:
    return model_root / "asr" / BREEZE_MODEL / BREEZE_BUILD


def validate_breeze_model(model_root: Path) -> Path:
    path = breeze_model_path(model_root)
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if any(manifest.get(key) != value for key, value in MANIFEST.items()):
            raise ValueError("Breeze model manifest does not match the pinned build")
        for filename in REQUIRED_FILES:
            if not (path / filename).is_file() or (path / filename).stat().st_size == 0:
                raise ValueError(f"Missing or empty model file: {filename}")
    except (OSError, ValueError, AttributeError) as error:
        raise RetryableFailure(
            "asr_model_unavailable",
            "The requested ASR model is not prepared.",
            detail="Breeze-ASR-25 is not prepared. Run the model-tools Compose "
            "profile (see docs/deployment.md).",
        ) from error
    return path


def resolve_asr_model(model_name: str, model_root: Path) -> str:
    if model_name == BREEZE_MODEL:
        return str(validate_breeze_model(model_root))
    return model_name


def prepare_breeze_model(model_root: Path) -> Path:
    """Publish only a complete conversion; failed conversions leave no ready model."""
    destination = breeze_model_path(model_root)
    if destination.exists():
        return validate_breeze_model(model_root)

    # Conversion dependencies belong to the model-tools image, not Worker runtime.
    from ctranslate2.converters import TransformersConverter
    from huggingface_hub import snapshot_download

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".prepare-", dir=destination.parent) as temporary:
        source = snapshot_download(
            repo_id=BREEZE_REPOSITORY,
            revision=BREEZE_REVISION,
            local_dir=str(Path(temporary) / "source"),
            allow_patterns=["*.json", "*.safetensors", "*.txt", "README.md", "LICENSE*"],
            token=None,
        )
        converted = Path(temporary) / "converted"
        TransformersConverter(
            source,
            copy_files=["tokenizer.json", "preprocessor_config.json"],
        ).convert(str(converted), quantization="float16")
        # Keep attribution and upstream generation settings beside the conversion.
        for filename in ("README.md", "LICENSE", "LICENSE.txt", "generation_config.json"):
            original = Path(source) / filename
            if original.is_file():
                shutil.copyfile(original, converted / filename)
        for filename in REQUIRED_FILES:
            if not (converted / filename).is_file() or (converted / filename).stat().st_size == 0:
                raise RuntimeError(f"Incomplete Breeze conversion: {filename}")
        (converted / "manifest.json").write_text(
            json.dumps(MANIFEST, indent=2) + "\n", encoding="utf-8",
        )
        converted.rename(destination)
    return validate_breeze_model(model_root)
