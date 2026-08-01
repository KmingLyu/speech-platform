# Speaker diarization extension plan

## Scope

Add a `POST /v1/diarizations` workflow that accepts the same Source and transcription settings as `POST /v1/transcriptions`, then runs:

```text
transcribing
→ aligning
→ diarizing
→ attributing_speakers
→ segmenting_for_display
→ exporting
```

The workflow produces one diarized transcript artifact composed of final Display segments. It does not expose a second plain-transcription resource, raw ASR segments, or word timestamps for the same job. The standalone transcription workflow remains unchanged.

## API resources

```http
POST   /v1/transcriptions
GET    /v1/transcriptions
GET    /v1/transcriptions/{id}
POST   /v1/transcriptions/{id}/retry
POST   /v1/transcriptions/{id}/cancel
DELETE /v1/transcriptions/{id}

POST   /v1/diarizations
GET    /v1/diarizations
GET    /v1/diarizations/{id}
POST   /v1/diarizations/{id}/retry
POST   /v1/diarizations/{id}/cancel
DELETE /v1/diarizations/{id}
```

The two resource families share lifecycle statuses, pagination, artifact download conventions, and error envelopes. Each family only addresses its own `job_type`; a type mismatch returns generic `404 job_not_found`.

## Creation inputs

`POST /v1/diarizations` reuses the existing Source, language, model, and format fields and adds:

```text
min_speakers: optional positive integer
max_speakers: optional positive integer
max_chars_per_line: optional positive integer, default 20
```

Validation requires `min_speakers <= max_speakers`. If both are omitted, pyannote estimates the number of speakers. `max_chars_per_line` applies to the complete visible cue, including its speaker label. Diarization model and alignment strategy are deployment-controlled, not client-selected; `POST /v1/transcriptions` does not accept `max_chars_per_line`.

## Job identity and persistence

Use the existing `transcription_jobs` table with:

```text
job_type = transcription | diarization
```

Existing rows default to `transcription`. New IDs use `tr_` and `di_` namespaces. Add nullable diarization configuration columns for `min_speakers`, `max_speakers`, `diarization_model`, and `diarization_model_revision`; `job_type` is immutable.

For diarization jobs, keep `result_text` NULL. Reuse the current artifact path columns and filenames for now; renaming them to `output_*_path` and `output.*` is deferred until the existing transcription copy in `result_text` is removed.

## Processing and models

Self-host `pyannote/speaker-diarization-community-1` in the GPU Worker. Pin a model revision, download it into a persistent versioned `/models` directory, validate it before accepting jobs, and record the revision in both job configuration and output metadata. Use `exclusive_speaker_diarization` for the first version; do not publish raw diarization turns.

Use language-specific forced alignment where available. If no alignment model exists or forced alignment fails, use faster-whisper word timestamps when available. Record the strategy and fallback reason in JSON metadata. A future implementation may use Whisper timestamps exclusively or segment-level attribution.

Set the deployment-level `ALIGNMENT_STRATEGY` to one of:

- `forced_alignment` (default): forced alignment, then faster-whisper word timestamps if forced alignment is unavailable or fails.
- `whisper_word_timestamps`: skip forced alignment and use faster-whisper word timestamps.

This setting applies to diarization only. It must be recorded in completed-artifact metadata through the selected `alignment_strategy` and any fallback fields; it is not a client request parameter. Proportional estimation is not an alignment strategy: it is only the display-stage fallback after successful speaker attribution.

## Display segmentation

After speaker attribution, derive Display segments from the speaker-consistent text and timing data. Preserve the original ASR segments and intermediate word/alignment data in the job work area until the job is deleted, but do not expose them as downloadable artifacts. Display segmentation only changes cue boundaries and times: concatenating the main text of its Display segments must preserve the attributed transcript text (apart from existing output-script conversion and whitespace normalization).

Each Display segment is exactly one visible line. Its speaker label and main text share that line; the system must never add a text newline, rely on CSS wrapping, or shrink the font to make a cue fit. When a cue must be shorter, create another Display segment with a different time range.

Use these hard constraints:

- `max_chars_per_line` defaults to 20 visual units. Chinese and other full-width characters count as 1; ASCII letters and digits count as 0.5; the visible speaker label counts toward this limit.
- Main spoken text, excluding the speaker label, must not exceed 6 full-width-character units per second.
- A cue normally remains visible for at least 1.0 second and at most 5.0 seconds. Move a proposed boundary to satisfy the minimum where possible, but never merge across a reliable speaker change. Cues exceeding the maximum must be split.
- A reliable speaker change is the highest-priority timed-cue boundary. A `null` speaker is not a reliable speaker change.

Subject to those hard constraints, choose the boundary nearest the ideal balanced split, in this priority order: sentence-ending punctuation (`。！？` and equivalents); secondary punctuation (`，、：；` and equivalents); a natural pause between words; a Chinese semantic-clause boundary; then any adjacent word boundary that does not damage a protected span. Prefer a boundary that leaves the preceding and following cues similar in length.

Never split a protected span—person name, proper noun, number and unit, English name, or hyphenated term such as `PV-1`. If one protected span alone exceeds the maximum line length, emit it intact as the sole exception rather than splitting the span or using CSS to hide the overflow.

If display segmentation has no usable word timestamps but receives an already speaker-consistent segment with `start` and `end`, it may estimate child cue times in proportion to the main text's visual-unit length and set `metadata.display_timing_strategy` to `proportional_estimate`. This fallback must never be used to infer or alter speaker attribution. If attribution itself has no reliable word data, the diarization job fails as today.

## Output contract

The JSON artifact keeps the existing root envelope and adds:

```json
{
  "schema_version": "1.0",
  "artifact_type": "diarized_transcript",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 2.0,
      "speaker": "SPEAKER_00",
      "text": "大家好"
    }
  ],
  "metadata": {
    "alignment_strategy": "forced_alignment",
    "alignment_language": "zh",
    "fallback_used": false,
    "speaker_count": 1,
    "speakers": ["SPEAKER_00"]
  }
}
```

The public schema is Display-segment-level only. Internal ASR segments and word timestamps are used for attribution and display timing but are not exported. JSON `segments[].text` is main spoken text and `segments[].speaker` is the separate speaker value; JSON top-level `text` remains plain text. TXT, SRT, and future VTT render each final cue on one line as `[SPEAKER_00] main spoken text`; a null speaker renders as `[UNKNOWN]`. The visible label counts toward `max_chars_per_line` but not toward spoken-text reading speed.

## Failure behavior

- `empty_transcript`: permanent failure for diarization jobs.
- `no_speakers_detected`: permanent failure.
- Partial attribution gaps: complete with `speaker: null` and attribution statistics.
- Alignment failure with usable Whisper timestamps: complete with fallback metadata.
- Display timing without usable word timestamps but with an already attributed segment: complete with `display_timing_strategy: proportional_estimate`.
- Missing model/deployment failures: retryable and never silently switch model revision.

## Implementation slices

1. Add migration and typed job creation: `job_type`, prefixes, configuration columns, and legacy default.
2. Isolate existing transcription list/detail/actions by job type.
3. Add diarization create/list/detail/action routes using the shared lifecycle.
4. Add worker dispatch by job type and model/revision startup validation.
5. Add alignment, pyannote exclusive diarization, attribution, and exporters.
6. Add fake-adapter contract tests and separate real-model smoke tests.
7. Add authorized audio fixtures for speaker alternation, boundary crossings, fallback, null attribution, and no-speaker failures.
8. Add Display-segment contract tests for one-line output, line-length and reading-speed limits, punctuation and pause priorities, protected spans, speaker-change cuts, and proportional timing fallback.

## Deferred work

- overlap-aware output and raw diarization artifacts
- speaker naming, voiceprints, and cross-job identity
- partial retry or reuse of successful intermediate artifacts
- removal of `result_text` and rename from `result_*` to `output_*`
- multilingual per-segment alignment
- exposing word-level timestamps
- applying Display segmentation to standalone transcription
