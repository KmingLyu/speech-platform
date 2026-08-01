# Separate job types and ID namespaces

**Status: accepted**

Transcription and diarization jobs share the `transcription_jobs` table and queue/lifecycle infrastructure, but remain distinct API resources. The immutable `job_type` column is the database authority, while IDs use stable public prefixes: `tr_` for transcription and `di_` for diarization. Each endpoint validates both the expected prefix and the stored job type; a mismatch is reported as the generic `job_not_found` response.

Creation endpoints determine the job type; clients cannot provide or override it. Existing rows default to `transcription`, and retries preserve the original type. This keeps storage and worker coordination shared without making `/v1/jobs` responsible for multiple incompatible resource schemas.

**Considered Options**

- One shared `/v1/jobs` resource: centralizes access, but hides meaningful differences in input, stages, and artifacts behind conditional behavior.
- Separate tables: makes ownership explicit, but duplicates queue, lifecycle, retry, cancellation, and recovery logic before the product needs that separation.
- Shared table with typed resources and ID namespaces: preserves infrastructure reuse while keeping API semantics explicit, therefore adopted.
