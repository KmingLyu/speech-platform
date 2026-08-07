# Self-host the community diarization model

**Status: accepted**

The diarization Worker will self-host `pyannote/speaker-diarization-community-1`. Deployment will use a Hugging Face token only to download the model into the persistent `/models` volume; Worker startup must load and validate the pipeline before accepting jobs. Runtime processing will use the local model files and will not upload audio to an external diarization service.

This keeps diarization within the existing private GPU Worker boundary, avoids per-job network/model-download latency, and leaves model replacement as a deployment configuration change. The deployment must keep the token out of source control and explicitly configure pyannote telemetry.

The deployment must pin a model revision rather than track a moving latest version. New revisions are downloaded into versioned model directories, compared against fixed audio fixtures, activated through configuration, and kept alongside the previous revision until rollback is no longer needed. Completed job metadata records the model revision used so results remain explainable and reproducible.

The first diarization implementation will use Community-1's `exclusive_speaker_diarization` output for speaker attribution. This produces non-overlapping speaker turns that are easier to reconcile with aligned transcription words and matches the first-version decision not to expose overlap-aware output. The regular diarization output remains a future extension point; supporting overlap later would require a new attribution strategy and result representation.

**Considered Options**

- Use pyannoteAI Precision-2: potentially higher quality and simpler hosted orchestration, but sends processing to an external service and changes the private self-hosted boundary.
- Download the model during image build: gives immutable images, but makes image distribution larger and complicates model updates.
- Download on every job: avoids persistent model storage, but adds latency and creates a runtime network dependency.
