# 01 — Typed jobs and ID namespaces

**What to build:** Existing transcription jobs continue working while the platform distinguishes transcription and diarization jobs with an immutable job type and stable public ID namespaces. Resource lists and actions must not operate on the wrong job family.

**Blocked by:** None — can start immediately.

**Status:** closed

- [x] Existing rows become `transcription` jobs through a backward-compatible migration.
- [x] New transcription and diarization identities use `tr_` and `di_` prefixes respectively.
- [x] Lists, detail, retry, cancellation, deletion, and artifact access enforce the endpoint's job type and return generic `job_not_found` on mismatch.
- [x] Job responses expose top-level `job_type` without changing existing transcription behavior.
- [x] Integration tests cover legacy rows, ID namespaces, type isolation, and existing transcription regressions.

## Comments

- 2026-07-31: Implemented typed jobs and ID namespaces with migration 005, API type isolation, immutable database job types, response metadata, and regression coverage. Docker integration suite: 61 passed.
