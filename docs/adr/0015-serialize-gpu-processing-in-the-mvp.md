# Serialize GPU processing in the MVP

**Status: accepted**

The MVP runs one GPU Worker and processes one Transcription job at a time; additional jobs remain queued. The queue and job-claim protocol must remain safe for future multiple Workers, but horizontal worker scaling is deferred until throughput and GPU-memory requirements justify it. Serial processing keeps resource use predictable while preserving the existing PostgreSQL row-lock approach as a future scaling seam.

**Considered Options**

- Run multiple jobs concurrently now: improves throughput, but risks GPU memory contention and duplicates model memory without a measured need.
- Serialize one job at a time: predictable for the current personal deployment, therefore adopted.
