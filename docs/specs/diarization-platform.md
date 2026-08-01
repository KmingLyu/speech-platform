# Speaker diarization extension plan

## Scope

Add a `POST /v1/diarizations` workflow that accepts the same Source and transcription settings as `POST /v1/transcriptions`, then runs:

```text
transcribing
→ aligning
→ diarizing
→ attributing_speakers
→ exporting
```

The first version produces one diarized transcript artifact. It does not expose a second plain-transcription resource for the same job.

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
```

Validation requires `min_speakers <= max_speakers`. If both are omitted, pyannote estimates the number of speakers. Diarization model and alignment parameters are deployment-controlled, not client-selected.

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

The public schema is segment-level only. Internal word timestamps are used for attribution but are not exported. `speaker` may be `null`; TXT and SRT render this as `[UNKNOWN]`. TXT and SRT include speaker labels, while JSON top-level `text` remains plain text.

## Failure behavior

- `empty_transcript`: permanent failure for diarization jobs.
- `no_speakers_detected`: permanent failure.
- Partial attribution gaps: complete with `speaker: null` and attribution statistics.
- Alignment failure with usable Whisper timestamps: complete with fallback metadata.
- Missing model/deployment failures: retryable and never silently switch model revision.

## Implementation slices

1. Add migration and typed job creation: `job_type`, prefixes, configuration columns, and legacy default.
2. Isolate existing transcription list/detail/actions by job type.
3. Add diarization create/list/detail/action routes using the shared lifecycle.
4. Add worker dispatch by job type and model/revision startup validation.
5. Add alignment, pyannote exclusive diarization, attribution, and exporters.
6. Add fake-adapter contract tests and separate real-model smoke tests.
7. Add authorized audio fixtures for speaker alternation, boundary crossings, fallback, null attribution, and no-speaker failures.

## Deferred work

- overlap-aware output and raw diarization artifacts
- speaker naming, voiceprints, and cross-job identity
- partial retry or reuse of successful intermediate artifacts
- removal of `result_text` and rename from `result_*` to `output_*`
- multilingual per-segment alignment
- exposing word-level timestamps
