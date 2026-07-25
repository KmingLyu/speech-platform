# Keep one source per transcription job

**Status: accepted**

The API creates exactly one Transcription job for exactly one Source; processing multiple sources means making multiple API calls. The platform may queue those jobs, but it does not expose a batch-submit request. This keeps retry, cancellation, deletion, and artifact ownership unambiguous for each source while still supporting asynchronous batch workloads through repeated submissions.

**Considered Options**

- Accept multiple sources in one request: reduces client calls, but creates nested batch state and ambiguous partial failures or cancellation semantics.
- One source per job: keeps each lifecycle independently observable and controllable, therefore adopted.
