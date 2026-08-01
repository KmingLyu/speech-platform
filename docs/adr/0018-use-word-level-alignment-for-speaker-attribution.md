# Use word-level alignment for speaker attribution

**Status: superseded by ADR 0025**

The diarization pipeline will internally use word-level forced alignment before assigning speaker turns, then merge adjacent words into speaker-consistent segment-level output. The public JSON will expose segment-level results only; it will not expose word-level timestamps or word-level speaker labels in the first version.

This does not assume that every Whisper Segment contains only one speaker. Whisper segments are ASR-oriented time regions and may cross a speaker boundary. A future implementation may adopt the simpler strategy of assigning one speaker to each Whisper Segment by maximum time overlap, so the internal attribution strategy must remain replaceable without changing the public result shape.

The alignment adapter must also remain replaceable. The first implementation may use language-specific forced alignment, but multilingual or otherwise unalignable content may fall back to Whisper/faster-whisper word timestamps. A later deployment may choose to use Whisper timestamps exclusively and omit the additional alignment model; this is an internal strategy choice and must be recorded in job metadata rather than exposed as a separate public result schema.

Completed results should record the selected `alignment_strategy`, the `alignment_language` when applicable, and whether `fallback_used` was true, so consumers can distinguish refined alignment from the less precise timestamp fallback.

Transcription and diarization JSON artifacts share the existing root-level `schema_version` field. Diarization must not add a second `metadata.schema_version`; it extends the existing envelope with speaker fields and attribution metadata while preserving compatibility for current transcription consumers.

The processing stages follow WhisperX's proven sequence: `transcribing` → `aligning` → `diarizing` → `attributing_speakers` → `exporting`. Alignment produces word timestamps, diarization produces speaker turns, and attribution reconciles the two timelines before the public segment-level artifact is written. ADR 0023 subsequently adds `segmenting_for_display` between attribution and exporting for diarization subtitles; it does not change this attribution decision.

Speaker attribution may produce `speaker: null` when an aligned word or regrouped segment has no reliable overlap with a diarization turn. The first version will preserve that uncertainty instead of assigning the nearest or previous speaker. If the null rate is too high on real fixtures, the replaceable attribution strategy may later enable nearest-speaker filling or switch to Whisper Segment-level attribution.

**Considered Options**

- Treat every Whisper Segment as one speaker: simpler and often adequate, but hides boundary errors and cannot handle a segment crossing speakers reliably.
- Assign speakers at word level, then regroup segments: more processing and dependency on alignment, but gives a safer boundary for speaker attribution and preserves a segment-level public API.
- Use Whisper/faster-whisper word timestamps: simpler deployment and broader language coverage, but potentially less precise speaker boundaries.
