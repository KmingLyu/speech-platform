# Make cancellation asynchronous and idempotent

**Status: accepted**

Canceling a queued Transcription job can transition directly to `canceled` because no Worker is using its resources. Canceling an active job is asynchronous: the API records `cancel_requested` and returns `202`, then the Worker stops at a safe checkpoint and records `canceled`. Repeating the same cancel request does not create another operation and returns the current cancellation state. This reflects that the API cannot safely terminate FFmpeg or GPU work synchronously while preventing duplicate effects from client retries.

**Considered Options**

- Synchronously force-stop the process: faster feedback, but unsafe around shared files, subprocesses, and GPU cleanup.
- Return `202` and complete cancellation cooperatively: safer for resource cleanup and therefore adopted.
