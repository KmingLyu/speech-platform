"""Download one pinned Community-1 revision into the persistent model volume."""

from src.config import load_settings
from src.model_registry import download_pinned_model


if __name__ == "__main__":
    settings = load_settings()
    print(download_pinned_model(settings))
