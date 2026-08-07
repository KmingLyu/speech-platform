# 02 — Extend Hotword support to Diarization jobs

**What to build:** A Diarization creation request can supply the same Hotword list as Transcription jobs, using the same validation and conversion mechanism built in 01. Diarization's internal transcription step benefits from the same recognizer hint, and the job's observable configuration and Retry behavior match Transcription.

**Blocked by:** 01 — Add Hotword support to Transcription jobs.

**Status:** ready-for-agent

- [ ] A Diarization creation request accepts the `hotwords` field with the same validation rules as Transcription (non-empty after trimming, at most 50 characters each, at most 100 entries).
- [ ] Diarization's internal transcription step receives the same converted hotword list, using the mechanism built in 01, with no divergent behavior between the two job types.
- [ ] The Diarization job's observable configuration exposes the converted hotword list alongside existing diarization-specific fields (`min_speakers`, `max_speakers`, `max_chars_per_line`, etc.).
- [ ] Retry of a Diarization job reuses its original hotwords unchanged.
- [ ] Black-box Diarization workflow tests cover acceptance, script conversion, and retry preservation, mirroring the Transcription coverage from 01.
