# Keep sources scoped to one transcription job

**Status: accepted**

In the current scope, a Source belongs to one Transcription job and is not exposed as a reusable library. Re-running the same recording with another model or language requires a new submission. This keeps source retention, deletion, and permissions aligned with the single job lifecycle while the product has no need for reusable assets or persistent Transcription records.

**Considered Options**

- Introduce a reusable Source library: avoids repeated uploads or downloads for model comparisons, but adds identity, storage, deduplication, and deletion rules before they are needed.
- Keep each Source scoped to its job: simpler and consistent with the current standalone-job boundary, therefore adopted.
