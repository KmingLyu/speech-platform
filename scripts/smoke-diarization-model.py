"""Load the pinned diarization model and run it against an authorized fixture.

This is deliberately separate from the fake-adapter integration suite. Set
AUTHORIZED_AUDIO_FIXTURE to a short local recording before running it.
"""

import os
import json
from pathlib import Path

from src.config import load_settings
from src.isolated_diarization import IsolatedDiarization
from src.device import log_inference_devices, resolve_inference_devices
from src.model_registry import validate_pinned_model


if __name__ == "__main__":
    fixture = Path(os.environ["AUTHORIZED_AUDIO_FIXTURE"])
    settings = load_settings()
    validate_pinned_model(settings)
    devices = resolve_inference_devices(settings.inference_device)
    log_inference_devices(devices)
    turns = IsolatedDiarization(
        model=settings.diarization_model,
        revision=settings.diarization_model_revision,
        model_root=settings.model_root,
        device=devices.diarization,
        allow_runtime_fallback=devices.allow_runtime_fallback,
    ).diarize(fixture, min_speakers=None, max_speakers=None)
    if not turns:
        raise SystemExit("Smoke test failed: no speakers detected")
    artifact_path = os.getenv("AUTHORIZED_JSON_ARTIFACT")
    if artifact_path:
        artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        if artifact.get("schema_version") != "1.0" or artifact.get("artifact_type") != "diarized_transcript":
            raise SystemExit("Smoke test failed: invalid diarized artifact envelope")
    print(f"Smoke test passed: {len(turns)} exclusive speaker turns")
