# 01 — Add Hotword support to Transcription jobs

**What to build:** A Transcription creation request can supply a list of Hotwords. Accepted Hotwords are converted to match the job's output script the same way output text is, persisted as part of the job's Transcription configuration, sent to the recognizer as a hint on every attempt, echoed back through the job's observable configuration, and preserved unchanged on Retry.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A Transcription creation request accepts zero or more `hotwords` values; each must be non-empty after trimming and at most 50 characters, and the list may contain at most 100 entries. Violating any of these rules returns a structured validation error and creates no job.
- [ ] Accepted hotwords are converted to match the job's output script (original/Traditional/Simplified) using the same conversion applied to output text, before being sent to the recognizer.
- [ ] The recognizer receives the joined, converted hotword list as its hotword hint on every attempt. Omitting hotwords behaves exactly as it does today — no regression for existing Transcription jobs.
- [ ] The job's observable configuration exposes the converted hotword list so the owner can confirm what was actually applied.
- [ ] Retry reuses the job's original hotwords unchanged, consistent with how `model` and `language` are preserved.
- [ ] Black-box Transcription workflow tests cover: an accepted list within limits, each validation-rejection case, script conversion of hotwords, and retry preservation — using the existing deterministic fake recognizer adapter, without requiring GPU or external model access.
