# Hotwords

**Status:** completed

## Problem Statement

Recognition accuracy degrades on domain-specific vocabulary that faster-whisper has no reason to prefer — product codes, proper nouns, and technical terms particular to one Source (e.g. `PV-1` in a technical presentation). The owner needs a way to bias recognition toward known vocabulary on a per-job basis, without changing the deployment-wide model or strategy configuration.

## Solution

Add an optional Hotword list to Transcription configuration, accepted by both `POST /v1/transcriptions` and `POST /v1/diarizations` as a repeatable `hotwords` form field, matching the existing `formats` convention. Each hotword is validated (non-empty, max 50 characters, max 100 entries per job), preserved exactly as provided, and joined before being passed to faster-whisper's `hotwords` parameter. The completed job's Transcript is normalized separately by the Worker after ASR; this never changes Hotword values.

Hotwords are stored as part of the job row, so Retry preserves them unchanged like `model` and `language` (ADR 0012). `job_configuration()` echoes the original hotword list back to the client so they can confirm what was actually applied.

This is a per-job, client-supplied setting rather than a deployment-wide fixed list — see ADR 0027 for why.

## User Stories

1. As the owner, I want to supply a list of expected words or phrases when creating a Transcription job, so that faster-whisper is more likely to recognize them correctly.
2. As the owner, I want the same capability on Diarization jobs, so that speaker-attributed transcripts benefit from the same accuracy improvement.
3. As the owner, I want my hotwords passed to recognition exactly as supplied, so that product codes and proper nouns are not rewritten.
4. As the owner, I want to see the original hotwords in the job's configuration response, so that I can confirm exactly what was received and applied.
5. As the owner, I want invalid hotword input (empty entries, oversized entries, too many entries) rejected with a structured validation error, so that I find out immediately rather than after the job silently truncates my list.
6. As the owner, I want a Retry of a failed job to reuse the same hotwords, so that retrying doesn't require resubmitting configuration I already provided.

## Out of scope

- Deployment-wide default hotword lists (rejected — see ADR 0027).
- Per-word confidence/weighting controls beyond what faster-whisper's single `hotwords` string supports.
- Any change to the existing output-text script conversion pipeline.
