# 01 — Build diarized Display segment foundation

**What to build:** A Diarization job can accept an optional `max_chars_per_line` setting, default it to 20, retain it through retries, and download JSON, TXT, and SRT artifacts made from final one-line Display segments instead of raw ASR segments. Visible subtitle labels use `[SPEAKER_00]` or `[UNKNOWN]`, and the output respects reliable speaker boundaries, the configured line capacity, spoken-text reading speed, and normal 1.0-to-5.0-second cue durations.

**Blocked by:** None — can start immediately.

**Status:** closed

- [x] A Diarization creation request accepts a positive `max_chars_per_line`, defaults an omitted value to 20, returns the applied configuration through observable job state, and preserves it on retry; invalid values are rejected while standalone Transcription remains unchanged.
- [x] A completed Diarization job exports sequential, one-line Display segments consistently in JSON, TXT, and SRT, with visible speaker labels in human-readable artifacts and separate `speaker` and spoken `text` in JSON.
- [x] The black-box Diarization workflow proves cue splitting respects speaker changes, capacity, spoken-text speed, and normal duration bounds without requiring GPU or external-model access.

## Comments

- 2026-08-01: Implemented Display-segment foundation with persisted line capacity, final diarized artifacts, and deterministic fake-worker workflow coverage.
