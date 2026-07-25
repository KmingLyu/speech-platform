# Require all requested artifacts before completion

**Status: accepted**

A Transcription job becomes `completed` only when every requested Output format has been written and is available. If any artifact generation fails, the entire job is `failed` and partial artifacts are not exposed as usable results; a retry regenerates the complete requested set. This keeps `completed` a reliable promise instead of making clients reason about partial success.

**Considered Options**

- Mark the job completed with whatever artifacts succeeded: more tolerant of isolated export failures, but makes result completeness ambiguous.
- Require all requested artifacts: gives `completed` one strong meaning, therefore adopted.
