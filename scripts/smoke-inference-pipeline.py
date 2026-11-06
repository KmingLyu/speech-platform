"""Run real ASR, word attribution and isolated diarization on a 30-second clip."""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from src.alignment import WhisperWordAlignment, associate_words_with_asr_segments
from src.asr_models import BREEZE_MODEL
from src.attribution import attribute_words
from src.config import load_settings
from src.device import log_inference_devices, resolve_inference_devices
from src.display_segments import display_segments
from src.isolated_diarization import IsolatedDiarization
from src.script_converter import convert_transcript
from src.transcriber import Transcriber


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    devices = resolve_inference_devices(settings.inference_device)
    log_inference_devices(devices)
    if devices.transcription.device != "cuda" or devices.diarization.device != "cuda":
        raise SystemExit("GPU smoke failed: both backends must select CUDA")
    with tempfile.TemporaryDirectory() as temporary:
        audio = Path(temporary) / "clip.wav"
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-i", os.environ["AUTHORIZED_AUDIO_FIXTURE"],
            "-t", "30", "-ac", "1", "-ar", "16000", str(audio),
        ], check=True)
        text, segments = Transcriber(
            settings, devices.transcription, allow_runtime_fallback=False,
        ).transcribe(audio, model_name=BREEZE_MODEL, language=None)
        text, segments = convert_transcript(text, segments, "zh-tw")
        if not text.strip():
            raise SystemExit("GPU smoke failed: empty transcript")
        alignment = WhisperWordAlignment().align(audio, text=text, segments=segments, language="zh-tw")
        words = associate_words_with_asr_segments(alignment.words, segments)
        print(f"ASR passed: {len(segments)} segments, {len(words)} timestamped words", flush=True)
        turns = IsolatedDiarization(
            model=settings.diarization_model, revision=settings.diarization_model_revision,
            model_root=settings.model_root, device=devices.diarization,
            allow_runtime_fallback=False,
        ).diarize(audio, min_speakers=None, max_speakers=None)
        if not turns:
            raise SystemExit("GPU smoke failed: no speaker turns")
        display = display_segments(attribute_words(words, turns).words, max_chars_per_line=20)
        if not display:
            raise SystemExit("GPU smoke failed: no display segments")
        print(f"Pipeline smoke passed: {len(turns)} speaker turns, {len(display)} display segments")
