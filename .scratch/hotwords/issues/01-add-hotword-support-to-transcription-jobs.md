# 01 — Add Hotword support to Transcription jobs

**What to build:** A Transcription creation request can supply a list of Hotwords. Accepted Hotwords are preserved exactly as supplied, persisted as part of the job's Transcription configuration, sent to the recognizer as a hint on every attempt, echoed back through the job's observable configuration, and preserved unchanged on Retry.

**Blocked by:** None — can start immediately.

**Status:** closed

- [x] A Transcription creation request accepts zero or more `hotwords` values; each must be non-empty after trimming and at most 50 characters, and the list may contain at most 100 entries. Violating any of these rules returns a structured validation error and creates no job.
- [x] Accepted hotwords remain exactly as supplied before being sent to the recognizer.
- [x] The recognizer receives the joined, original hotword list as its hotword hint on every attempt. Omitting hotwords behaves exactly as it does today — no regression for existing Transcription jobs.
- [x] The job's observable configuration exposes the original hotword list so the owner can confirm what was applied.
- [x] Retry reuses the job's original hotwords unchanged, consistent with how `model` and `language` are preserved.
- [x] Black-box Transcription workflow tests cover: an accepted list within limits, each validation-rejection case, script conversion of hotwords, and retry preservation — using the existing deterministic fake recognizer adapter, without requiring GPU or external model access.

## Comments

- 2026-08-08: Implemented per-job Hotwords for Transcription. Conversion runs in the API server at creation time (migration `009_add_hotwords.sql`, `hotwords TEXT[]`), so the stored list is exactly what the recognizer is biased toward and what `configuration.hotwords` echoes. The Worker joins the list with spaces into faster-whisper's `hotwords` parameter on every Attempt; Retry is preserved for free because it never rewrites configuration columns.
- 2026-08-08: Two review notes carried forward, deliberately:
  - Transcript script conversion is owned by the Worker; the API has no OpenCC dependency.
  - `configuration.hotwords` is exposed for Transcription jobs only, so Diarization does not advertise a field its endpoint cannot yet accept. Issue 02 should move the key into the shared configuration block and delete `test_diarization_configuration_does_not_advertise_hotwords_yet`.
