"""Load the pinned diarization model and run it against an authorized fixture.

This is deliberately separate from the fake-adapter integration suite. Set
AUTHORIZED_AUDIO_FIXTURE to a short local recording before running it.
"""

import os
import json
from pathlib import Path

from src.config import load_settings
from src.diarizer import PyannoteCommunityDiarization
from src.model_registry import validate_pinned_model


if __name__ == "__main__":
    fixture = Path(os.environ["AUTHORIZED_AUDIO_FIXTURE"])
    settings = load_settings()
    validate_pinned_model(settings)
    turns = PyannoteCommunityDiarization(
        model=settings.diarization_model,
        revision=settings.diarization_model_revision,
        model_root=settings.model_root,
    ).diarize(fixture, min_speakers=None, max_speakers=None)
    if not turns:
        raise SystemExit("Smoke test failed: no speakers detected")
    artifact_path = os.getenv("AUTHORIZED_JSON_ARTIFACT")
    if artifact_path:
        artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        if artifact.get("schema_version") != "1.0" or artifact.get("artifact_type") != "diarized_transcript":
            raise SystemExit("Smoke test failed: invalid diarized artifact envelope")
    print(f"Smoke test passed: {len(turns)} exclusive speaker turns")
