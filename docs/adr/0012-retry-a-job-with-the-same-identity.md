# Retry a failed job with the same identity

**Status: accepted**

Manual retry requeues the existing failed Transcription job under the same job ID instead of creating a new job. Only `failed` jobs are retryable; `canceled` is an intentional terminal state and must be resubmitted as a new job if the user wants to process the source again. A retry keeps the job's original Source and Transcription configuration; changing the source, language, model, or formats requires a new job. The resource remains the same source-processing request, while `attempt_count` and the latest error describe its execution history. This keeps the user's job list free of duplicate entries and leaves room to add detailed attempt history later.

**Considered Options**

- Create a new job ID for every retry: preserves immutable attempt records, but duplicates one logical job in history and requires clients to follow a new identity.
- Requeue the existing job: simpler for the current workflow and therefore adopted.
