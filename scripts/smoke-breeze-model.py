"""Exercise real Breeze inference and word timestamps on a local speech fixture."""

import math
import os
from pathlib import Path

from src.asr_models import BREEZE_MODEL, validate_breeze_model
from src.config import load_settings
from src.device import log_inference_devices, resolve_inference_devices
from src.transcriber import Transcriber


if __name__ == "__main__":
    settings = load_settings()
    validate_breeze_model(settings.model_root)
    devices = resolve_inference_devices(settings.inference_device)
    log_inference_devices(devices)
    text, segments = Transcriber(
        settings, devices.transcription,
        allow_runtime_fallback=devices.allow_runtime_fallback,
    ).transcribe(
        Path(os.environ["AUTHORIZED_AUDIO_FIXTURE"]),
        model_name=BREEZE_MODEL, language="zh-tw",
    )
    words = [word for segment in segments for word in segment["words"]]
    if not text.strip() or not words:
        raise SystemExit("Smoke test failed: missing transcript or word timestamps")
    previous_start = 0.0
    for word in words:
        start, end = word["start"], word["end"]
        if not (math.isfinite(start) and math.isfinite(end) and previous_start <= start <= end):
            raise SystemExit("Smoke test failed: invalid word timestamps")
        previous_start = start
    print(f"Smoke test passed: {len(segments)} segments, {len(words)} timestamped words")
