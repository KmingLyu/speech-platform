# Speaker diarization pipeline

**Status:** completed

## Problem Statement

The platform currently produces standalone speech-recognition output but cannot identify which anonymous speaker spoke each part of a transcript. The owner needs a single asynchronous workflow that accepts the same audio/video sources as transcription, performs transcription followed by alignment and speaker diarization, and returns a readable speaker-attributed transcript without making the client manage intermediate jobs.

## Solution

Add a first-class Diarization job resource. `POST /v1/diarizations` accepts the existing Source and transcription settings plus optional speaker-count bounds. The Worker runs transcription, language-specific alignment when available, pyannote speaker diarization, word-level speaker attribution, segment regrouping, and export. The public result is segment-level JSON/TXT/SRT with anonymous speaker labels.

Transcription and diarization share queue and lifecycle infrastructure but remain separate API resources. A diarization job is not a second resource view of an existing transcription job.

## User Stories

1. As the owner, I want to submit an uploaded audio or video Source for diarization, so that I can receive a transcript with anonymous speaker labels.
2. As the owner, I want to submit a supported public YouTube Source for diarization, so that remote recordings use the same workflow as transcription.
3. As the owner, I want the diarization endpoint to accept the existing language, model, and output format settings, so that I do not learn a second source-submission contract.
4. As the owner, I want to optionally provide a minimum and maximum speaker count, so that known meeting sizes can improve clustering.
5. As the owner, I want omitted speaker bounds to use pyannote's automatic speaker-count estimation, so that ordinary jobs need no extra configuration.
6. As the owner, I want diarization submission to return immediately with a job ID, so that long GPU work does not block HTTP.
7. As the owner, I want diarization jobs to expose queued, processing, completed, failed, cancel-requested, and canceled lifecycle states, so that polling behaves like existing transcription jobs.
8. As the owner, I want the current diarization stage visible during processing, so that I can distinguish transcription, alignment, diarization, attribution, and export progress.
9. As the owner, I want to list only diarization jobs through the diarization list endpoint, so that transcription history remains focused.
10. As the owner, I want transcription endpoints to reject diarization IDs as not found, so that resource semantics cannot be confused.
11. As the owner, I want diarization IDs to use a distinct `di_` namespace, so that logs and clients can recognize their job family.
12. As the owner, I want existing transcription IDs to remain valid and use the `tr_` namespace, so that this feature does not require rewriting existing history.
13. As the owner, I want retry, cancellation, and deletion to be isolated by resource type, so that an operation cannot target the wrong kind of job.
14. As the owner, I want retry to rerun the complete diarization pipeline, so that all timestamps and speaker attribution are regenerated consistently.
15. As the owner, I want a diarization job to fail when no transcript is produced, so that an empty result is not mistaken for successful speaker attribution.
16. As the owner, I want a diarization job to fail when pyannote detects no speakers, so that a result containing only unknown speakers is not reported as successful.
17. As the owner, I want partial attribution gaps to remain usable, so that one uncertain region does not discard an otherwise valid diarized transcript.
18. As the owner, I want uncertain regions represented as `speaker: null` in JSON and `[UNKNOWN]` in TXT/SRT, so that the platform does not invent speaker assignments.
19. As the owner, I want the JSON artifact to include speaker labels on segments, so that applications can process speaker-attributed text structurally.
20. As the owner, I want JSON top-level text to remain plain text, so that it remains useful to downstream text processing.
21. As the owner, I want TXT and SRT to show anonymous speaker labels, so that human-readable downloads retain the value of diarization.
22. As the owner, I want no word-level timestamps exposed in the first version, so that the public schema remains simple while the Worker can use word timings internally.
23. As the owner, I want no overlap-aware output in the first version, so that every public segment has at most one speaker.
24. As the owner, I want anonymous labels to remain scoped to one completed artifact, so that labels are not mistaken for real identities across jobs or retries.
25. As the owner, I want model and alignment strategy metadata included in JSON, so that I can understand how a result was produced.
26. As the owner, I want alignment failure to degrade to Whisper word timestamps when possible, so that a usable result can complete despite missing language-specific alignment.
27. As the owner, I want fallback reasons and attribution statistics recorded, so that later quality decisions can use real data.
28. As the owner, I want the diarization model revision recorded, so that completed output can be reproduced and audited.
29. As the owner, I want model upgrades to be pinned and rollbackable, so that a deployment does not silently change diarization behavior.
30. As the owner, I want diarization results stored as artifacts rather than duplicated in the database text column, so that database metadata remains small and authoritative.
31. As the owner, I want existing artifact names and database path columns reused initially, so that this feature does not expand into an unrelated naming migration.

## Implementation Decisions

### Resource and identity model

- Use the existing jobs table and queue for both job families.
- Add immutable `job_type` values `transcription` and `diarization`; existing rows default to `transcription`.
- Generate public IDs with `tr_` for transcription and `di_` for diarization.
- The endpoint determines job type; clients cannot submit or override it.
- Validate both ID prefix and stored `job_type`; a mismatch returns generic `job_not_found`.
- Keep separate resource families for list, detail, retry, cancel, delete, and artifact download.
- Shared lifecycle behavior, pagination, and error envelopes remain common.

### API contract

Add:

- `POST /v1/diarizations`
- `GET /v1/diarizations`
- `GET /v1/diarizations/{id}`
- `GET /v1/diarizations/{id}?format=json|txt|srt`
- `POST /v1/diarizations/{id}/retry`
- `POST /v1/diarizations/{id}/cancel`
- `DELETE /v1/diarizations/{id}`

Creation reuses the existing file/YouTube Source validation, language, model, and formats. It adds optional positive `min_speakers` and `max_speakers`; if both exist, minimum must not exceed maximum. No diarization model, VAD, overlap, threshold, naming, or voiceprint parameters are client-configurable.

Job summaries include top-level `job_type`, lifecycle data, current stage, configuration, artifact availability, and links. The detail endpoint remains compact; full metadata is in the JSON artifact.

### Pipeline

The Worker sequence is:

```text
transcribing → aligning → diarizing → attributing_speakers → exporting
```

- Use faster-whisper for transcription.
- Use language-specific forced alignment where a tested model exists.
- If alignment is unavailable or fails, use faster-whisper word timestamps when available.
- Use self-hosted `pyannote/speaker-diarization-community-1`.
- Use `exclusive_speaker_diarization` for first-version non-overlapping attribution.
- Assign speakers internally at word level, then regroup into public segment-level output.
- Use pyannote labels as returned; do not rename them by first appearance.
- Discard raw diarization turns and intermediate alignment artifacts after export.
- Share the existing serialized GPU Worker and load/evict large models safely to avoid GPU OOM.

### Persistence and model configuration

Add nullable diarization configuration fields for speaker bounds, diarization model, and pinned model revision. Store the revision captured at job creation so retry does not silently switch models. Keep `result_text` NULL for diarization jobs; initially reuse the existing result artifact filenames and path columns.

Production must provide a pinned model revision. The model is downloaded into a persistent versioned model directory, validated before accepting jobs, and kept alongside the previous revision for rollback. Missing model revisions are deployment failures and must not trigger an automatic switch to latest.

### JSON artifact

Transcription and diarization JSON share the existing root envelope and root-level `schema_version`. Add `artifact_type` with values `transcript` or `diarized_transcript`.

Diarization segments contain `id`, `start`, `end`, `speaker`, and `text`. Output segment IDs are regenerated sequentially after attribution; original Whisper segment IDs are not public. Top-level text is the concatenation of segment text without speaker labels.

Metadata records provider/model information, diarization model and revision, speaker count/list, alignment strategy, alignment language when applicable, fallback status/reason, and attribution counts/ratio. Alignment strategies are `forced_alignment`, `whisper_word_timestamps`, and a reserved future `whisper_segment_timestamps`.

### Failure behavior

- `empty_transcript`: permanent failure for diarization jobs.
- `no_speakers_detected`: permanent failure.
- `diarization_model_unavailable`, `alignment_model_unavailable`, `diarization_failed`, and `speaker_attribution_failed`: stable sanitized errors with retryability determined by whether the failure is environmental or input-specific.
- Forced alignment failure with usable Whisper timestamps completes with `fallback_used: true`.
- Complete inability to obtain timestamps or attribution fails the job.

## Testing Decisions

Tests use the highest existing seam: black-box HTTP API with a test database, temporary storage, and fake Worker adapters. They assert observable responses, lifecycle, artifacts, and cleanup rather than SQL statements or private helper calls.

Cover:

- creation, validation, ID prefixes, immutable job type, and legacy default
- list/detail/action type isolation and generic not-found behavior
- diarization stages and shared lifecycle semantics
- retry, cancellation, deletion, and full-pipeline rerun behavior
- JSON schema, artifact type, speaker labels, unknown speakers, TXT/SRT formatting, and metadata
- empty transcript, no speakers, fallback, partial attribution, and stable error classification
- model revision snapshot and deployment configuration validation
- migration compatibility with existing transcription rows

Use short, authorized fixtures for one speaker, alternating speakers, boundaries inside an ASR segment, fallback, unknown attribution, and no detected speakers. Keep real model smoke tests separate from ordinary integration tests; CI should use fake adapters and must not require GPU access, model downloads, or Hugging Face credentials.

## Out of Scope

- overlap-aware output and raw diarization artifacts
- word-level timestamps or word-level speaker labels in public output
- speaker naming, voiceprints, real identity, or cross-job label stability
- partial retry or reuse of successful intermediate stages
- a unified `/v1/jobs` endpoint
- separate diarization database table
- client-selected diarization model or internal VAD/threshold parameters
- multilingual per-segment alignment beyond fallback behavior
- immediate removal of `result_text` or renaming existing result paths/files

## Further Notes

The implementation should preserve the existing transcription behavior while extending the shared queue and artifact seams. The deferred artifact naming cleanup should be tracked separately: stop using the database `result_text` copy, then migrate existing result path/file conventions to the generic output naming agreed during design.
