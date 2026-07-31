# 02 — Diarization API with a fake end-to-end pipeline

**What to build:** A user can submit a Source to `POST /v1/diarizations`, poll the new diarization resource, and download deterministic diarized JSON/TXT/SRT artifacts through the real queue and lifecycle path without requiring external models.

**Blocked by:** 01 — Typed jobs and ID namespaces.

**Status:** closed

- [x] The create endpoint reuses existing Source, language, model, and format validation and accepts optional speaker-count bounds.
- [x] Invalid speaker bounds return structured validation errors.
- [x] Diarization list/detail/retry/cancel/delete and format downloads are type-isolated and use shared lifecycle semantics.
- [x] A fake pipeline produces segment-level speaker labels, plain JSON text, and speaker-labelled TXT/SRT artifacts.
- [x] Diarization jobs leave the database text copy NULL and expose artifact availability through the API.
- [x] API integration tests verify the complete fake workflow and cleanup behavior.

## Resolution

Implemented in the local branch with migration `006_add_diarization_bounds.sql`, the `/v1/diarizations` resource family, deterministic Worker diarization/export adapters, and `test_diarization_workflow.py`.
