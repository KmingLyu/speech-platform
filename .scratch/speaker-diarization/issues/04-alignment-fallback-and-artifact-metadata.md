# 04 — Alignment fallback and artifact metadata

**What to build:** Completed transcription and diarization JSON artifacts share a versioned envelope and explain how alignment and speaker attribution were performed, including graceful fallback to Whisper timestamps.

**Blocked by:** 03 — Real alignment and speaker attribution.

**Status:** closed

- [x] JSON artifacts expose the existing root schema version and `artifact_type` values for transcript and diarized transcript.
- [x] Diarized metadata records alignment strategy, alignment language when applicable, fallback status/reason, model revisions, speaker list/count, and attribution statistics.
- [x] Missing or failed forced alignment falls back to Whisper word timestamps when available and completes the job.
- [x] JSON top-level text remains plain text while TXT/SRT include speaker labels.
- [x] Segment and SRT numbering remain sequential and correspond across artifacts.
- [x] Existing transcription artifact tests prove the additive schema remains compatible.

## Resolution

Implemented the versioned artifact metadata envelope, typed alignment results,
Whisper timestamp fallback, speaker attribution statistics, model revision
metadata, and integration coverage for fallback output.
