# Use explicit deletion for retention in the MVP

**Status: accepted**

The MVP retains source files, work files, job metadata, and transcript artifacts until the user explicitly deletes the Transcription job. Automatic retention cleanup is not part of the current product contract, so the existing retention environment variables remain inactive until a concrete storage policy is agreed. Manual deletion avoids unexpectedly removing a source needed for retry or a result the user still needs.

**Considered Options**

- Automatic source and result expiration: limits disk usage, but can silently remove retry inputs or needed results before the user has reviewed them.
- Explicit deletion only: predictable and reversible at the product-operation level, therefore adopted for the current single-user deployment.
