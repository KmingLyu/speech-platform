# Require cancellation before deleting an active job

**Status: accepted**

Deletion is only allowed for a terminal Transcription job (`completed`, `failed`, or `canceled`). An active job must first receive an explicit cancellation request and reach `canceled`; only then may the API delete its database record and all associated source, work, and result files. This two-step boundary prevents a Worker from racing with file deletion and makes the irreversible action explicit.

**Considered Options**

- Automatically cancel and delete an active job in one request: convenient, but creates a destructive race with Worker file access and hides two distinct user intentions.
- Require explicit cancellation before deletion: safer and easier to reason about, therefore adopted.
