# 02 — Extend Hotword support to Diarization jobs

**What to build:** A Diarization creation request can supply the same Hotword list as Transcription jobs, using the same validation and conversion mechanism built in 01. Diarization's internal transcription step benefits from the same recognizer hint, and the job's observable configuration and Retry behavior match Transcription.

**Blocked by:** 01 — Add Hotword support to Transcription jobs.

**Status:** closed

- [x] A Diarization creation request accepts the `hotwords` field with the same validation rules as Transcription (non-empty after trimming, at most 50 characters each, at most 100 entries).
- [x] Diarization's internal transcription step receives the same converted hotword list, using the mechanism built in 01, with no divergent behavior between the two job types.
- [x] The Diarization job's observable configuration exposes the converted hotword list alongside existing diarization-specific fields (`min_speakers`, `max_speakers`, `max_chars_per_line`, etc.).
- [x] Retry of a Diarization job reuses its original hotwords unchanged.
- [x] Black-box Diarization workflow tests cover acceptance, script conversion, and retry preservation, mirroring the Transcription coverage from 01.

## Comments

- 2026-08-08: The Worker needed no change. `process_job` runs one shared transcription step before branching on `job_type`, so it already read `job.get("hotwords")` for Diarization jobs — the only thing missing was an endpoint that could store them. That is why "no divergent behavior between the two job types" came for free rather than needing to be engineered.
- 2026-08-08: `configuration.hotwords` moved out of the Transcription-only branch of `job_configuration()` into the shared block, and `test_diarization_configuration_does_not_advertise_hotwords_yet` was deleted, as 01's closing comment directed.
- 2026-08-08: The hotword tests are now parametrized over both resources rather than duplicated, since the two endpoints are meant to be indistinguishable here — a divergence in either one fails the shared case. The recognizer-hint assertions read the JSON artifact's `text` instead of the TXT artifact, because Diarization's TXT output carries speaker labels and display-segment line breaks; TXT rendering itself stays covered by `test_smoke_workflow` and `test_transcription_lifecycle`.
- 2026-08-08: Two review notes not actioned, deliberately:
  - The two create endpoints now share a seven-line validation prologue verbatim. Extracting it into one FastAPI dependency is worth doing, but it is a refactor of code 01 did not touch, so it stays out of this ticket.
  - `docs/specs/diarization-platform.md` still lists creation inputs without `hotwords`. It is the historical plan for the diarization feature, not the living contract — 01 likewise left `docs/specs/transcription-platform-mvp.md` alone. `docs/architecture.md` and `README.md` are the documents kept current.
