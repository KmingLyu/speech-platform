# 05 — Pinned model deployment and quality smoke tests

**What to build:** Production can run a pinned self-hosted pyannote Community-1 revision with persistent model storage and rollback, while real-model validation remains separate from ordinary CI.

**Blocked by:** 03 — Real alignment and speaker attribution.

**Status:** closed

- [x] Production requires an explicit diarization model revision and refuses readiness when it is unavailable.
- [x] Model revisions are stored in versioned persistent directories and can coexist for rollback.
- [x] Job and artifact metadata record the model revision actually used.
- [x] A deployment smoke test loads the model against a short authorized fixture and can validate a public JSON artifact envelope.
- [x] Quality fixtures cover one speaker, alternating speakers, ASR boundary crossings, fallback, null attribution, and no detected speakers.
- [x] Ordinary integration tests do not require GPU access, model downloads, or Hugging Face credentials.

## Resolution

Implemented pinned revision snapshotting, persistent versioned model directories,
startup validation, deployment download and real-model smoke scripts, and
integration coverage that continues to use deterministic fake adapters.
