"""Convert the pinned official Breeze weights without requiring a GPU or database."""

import os
from pathlib import Path

from src.asr_models import prepare_breeze_model


if __name__ == "__main__":
    print(prepare_breeze_model(Path(os.getenv("MODEL_ROOT", "/models"))))
