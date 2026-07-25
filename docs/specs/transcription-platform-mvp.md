# Speech Platform — Transcription Platform MVP

## Problem Statement

The primary user is the owner of Speech Platform, who needs to turn audio files, video files, and public single-video YouTube sources into usable speech-recognition output. The current codebase can submit one upload or YouTube URL and process it asynchronously, but its domain model and API are still shaped around a minimal prototype: worker stages are exposed as job statuses, jobs cannot be listed, retried, canceled, or deleted through the API, input values are weakly validated, and there are no automated tests.

The user needs a reliable API-first workflow for submitting one Source per Transcription job, observing many jobs while they wait, retrieving complete Transcript artifacts, and recovering from transient failures without losing the original Source.

## Solution

Keep the self-hosted FastAPI plus PostgreSQL plus GPU Worker architecture, but make Transcription job the stable domain boundary. Each job owns exactly one Source and one immutable Transcription configuration. The job runs asynchronously, exposes stable lifecycle statuses plus optional worker-stage detail, and produces one complete Transcript represented by the requested JSON, TXT, and/or SRT artifacts.

The API will support creation, cursor-paginated history, detail polling, artifact download, bounded automatic retry, explicit manual retry, asynchronous cancellation, and deletion of terminal jobs. The MVP remains private-network, single-user, API-first, and serializes GPU work through one Worker while keeping the queue safe for future multiple Workers.

## User Stories

1. As the owner, I want to submit an audio file, so that I can obtain a transcription without keeping an HTTP request open during GPU processing.
2. As the owner, I want to submit a video file, so that the platform extracts its speech without requiring a separate audio-conversion step.
3. As the owner, I want to submit one public YouTube video URL, so that the Worker can acquire and transcribe its audio.
4. As the owner, I want the API to reject requests that provide both a file and a YouTube URL, so that every Transcription job has one unambiguous Source.
5. As the owner, I want the API to reject requests that provide neither a file nor a YouTube URL, so that invalid jobs do not enter the queue.
6. As the owner, I want uploads to stream to storage with a configurable capacity guard, so that large media does not need to fit in API memory or silently exhaust the disk.
7. As the owner, I want to leave the file extension and media duration open, so that any audio or video accepted by the media processor can be used.
8. As the owner, I want to select a Language preference or allow automatic detection, so that recognition uses the language appropriate to the Source.
9. As the owner, I want `zh-tw` and `zh-cn` to express the Chinese recognition and output convention I expect, so that I do not need separate language and script fields for the current workflow.
10. As the owner, I want to select a supported model or use the deployment default, so that ordinary jobs remain predictable while explicit model choice remains available.
11. As the owner, I want to select JSON, TXT, and/or SRT Output formats, so that the job produces only the Transcript artifacts I need.
12. As the owner, I want omitted Output formats to default to JSON, TXT, and SRT, so that a normal transcription is immediately useful in common tools.
13. As the owner, I want job creation to return a stable job ID immediately, so that I can submit another Source without waiting for the first job.
14. As the owner, I want to list recent Transcription jobs, so that I can find and monitor jobs when several are queued or processing.
15. As the owner, I want to filter the job list by lifecycle status, so that I can focus on queued, failed, or completed work.
16. As the owner, I want cursor pagination for job history, so that newly created jobs do not make pages duplicate or skip existing jobs.
17. As the owner, I want job detail to show stable status, current stage, approximate progress, configuration, timestamps, and artifact availability, so that polling responses stay small and useful.
18. As the owner, I want only `completed` jobs to expose downloadable artifacts, so that I never mistake an in-progress or partial result for a complete Transcript.
19. As the owner, I want JSON and SRT artifacts to retain segment start/end times, so that I can use them for subtitles and time-aligned processing.
20. As the owner, I want TXT to contain the Whisper text directly without platform-added segmentation or timestamps, so that the plain-text output remains faithful to the recognizer output.
21. As the owner, I want all requested artifacts to succeed before a job becomes completed, so that completed has one reliable meaning.
22. As the owner, I want transient download, Worker, and infrastructure failures to retry automatically within a bound, so that short-lived failures recover without manual intervention.
23. As the owner, I want retryable failures to be manually retriable under the same job ID, so that I can recover after fixing an environment problem without creating duplicate history entries.
24. As the owner, I want permanent input failures to be clearly marked non-retryable, so that I know when to submit a new Source instead of wasting attempts.
25. As the owner, I want Worker loss to be detected through heartbeat recovery, so that a job cannot remain stuck in processing forever.
26. As the owner, I want to cancel a queued job immediately, so that an unwanted job never consumes a Worker attempt.
27. As the owner, I want to cancel an active job asynchronously, so that the Worker can stop safely without corrupting files or GPU resources.
28. As the owner, I want cancellation requests to be safe to repeat, so that a client network retry does not create duplicate cancellation effects.
29. As the owner, I want to delete completed, failed, or canceled jobs and their files, so that I control storage retention explicitly.
30. As the owner, I want deletion of active jobs to be rejected until cancellation completes, so that a Worker cannot race with destructive file removal.
31. As the owner, I want polling to be the only completion notification in the MVP, so that the private-network deployment does not require an email or webhook subsystem.
32. As the owner, I want repeated API calls to represent explicit new jobs unless I later opt into idempotency, so that job creation semantics remain simple and visible.

## Implementation Decisions

### Domain model and invariants

- `Transcription` is the speech-recognition activity.
- `Transcription job` is the stable lifecycle resource and aggregate boundary.
- `Source` is scoped to one job. It is either an Uploaded source or a YouTube source and is not a reusable library asset.
- `Transcription configuration` is fixed when the job is created and contains Source, Language preference, model, and Output formats.
- Each job has one Source, multiple possible Attempts, and at most one complete Transcript.
- `Transcript` is the result content; `Transcript artifact` is one serialized representation of that Transcript.
- A Retry creates another Attempt under the same job identity and cannot alter the job configuration.
- Future Derived tasks such as diarization, translation, and summary are not modeled in this MVP.

### Lifecycle

The public lifecycle statuses are `queued`, `processing`, `completed`, `failed`, `cancel_requested`, and `canceled`. Worker-specific stages are secondary detail and must not become the primary API contract.

- `queued` means accepted and waiting for a Worker.
- `processing` means the Worker is acquiring, probing, transcoding, transcribing, or exporting.
- `completed` means every requested Transcript artifact is available.
- `failed` means a Permanent failure occurred or the bounded retry policy was exhausted.
- `cancel_requested` applies only while active processing is being stopped safely.
- `canceled` is terminal and produces no usable partial Transcript.

Queued cancellation may transition directly to `canceled`. Active cancellation first records `cancel_requested`; the Worker confirms `canceled` at a safe checkpoint. Repeating cancellation is idempotent. Terminal jobs cannot be canceled.

### API contract

All endpoints are available only within the private-network MVP boundary and use a common structured error envelope with a stable machine-readable code, human-readable message, and optional details.

| Method and path | Request | Success response | Important errors |
| --- | --- | --- | --- |
| `GET /healthz` | None | `200` liveness response | `503` if the service cannot report healthy |
| `POST /v1/transcriptions` | Multipart: exactly one of `file` or `youtube_url`; optional `language`, `model`, repeated `formats` | `202`, job ID, `queued` status, creation timestamp, `Location` header | `413 upload_too_large`; `422 invalid_source`, `youtube_url_not_supported`, `language_not_supported`, `model_not_supported`, `format_not_supported`; `500` storage/database failure |
| `GET /v1/transcriptions` | Optional `status`, bounded `limit`, opaque `cursor` | `200`, summary `items`, `next_cursor` | `400 invalid_cursor` or invalid filter/limit |
| `GET /v1/transcriptions/{id}` | Optional `format=json|txt|srt` | Without format: `200` metadata and artifact links. With format: direct artifact download | `404 job_not_found` or `artifact_not_found`; `409 result_not_ready`; `422 format_not_supported` |
| `POST /v1/transcriptions/{id}/retry` | None | `202`, same job ID, `queued` status, new Attempt | `404 job_not_found`; `409 job_not_retryable` for non-retryable or non-failed jobs |
| `POST /v1/transcriptions/{id}/cancel` | None | Queued: terminal `canceled`; active: `202` with `cancel_requested`; repeated requests return current state | `404 job_not_found`; `409 job_not_cancelable` for terminal jobs |
| `DELETE /v1/transcriptions/{id}` | None | `204`; removes metadata, Source, work files, and artifacts | `404 job_not_found`; `409 job_not_terminal` |

The list and detail summaries must not embed the complete Transcript. Full content is retrieved through the requested artifact format. Cursor ordering is stable by creation time plus job ID; the default page size is 20 and the maximum is 100.

### Source rules

- Uploaded sources accept audio and video without an extension allowlist or product-level duration limit.
- The upload body has a configurable safety ceiling; the current deployment default is 2 GB.
- YouTube sources accept only public single-video URLs on the supported YouTube hosts. Playlists, channels, search URLs, private or login-required content, and other websites are rejected.
- A single request creates one job. Multiple Sources require multiple API calls.
- Uploads use one streaming multipart request in the MVP; resumable upload and idempotency keys are deferred.

### Language, model, and formats

- Omitted `language` uses automatic detection.
- Supported faster-whisper language codes are accepted, plus the product-specific `zh-tw` and `zh-cn` preferences.
- `zh-tw` and `zh-cn` use Chinese recognition and apply the agreed Traditional Taiwan or Simplified Mainland output convention. This is script conversion, not translation.
- `model` is optional, comes from a deployment-defined allowlist, and defaults to `large-v3-turbo`.
- `formats` is optional and defaults to JSON, TXT, and SRT. Only requested artifacts are produced.
- JSON and SRT contain segment-level `start`, `end`, and `text`; word-level timestamps and confidence metadata are out of scope.
- TXT is the Whisper text directly, with only the agreed Chinese script conversion applied when requested; the platform does not add segment line breaks.

### Retry and recovery

- Errors are classified as Retryable failure or Permanent failure.
- Temporary download, Worker, database, and infrastructure failures may be automatically retried within a bounded attempt count.
- Permanent input or media failures do not automatically retry and are not manually retryable; the user must create a new job.
- After automatic retry exhaustion, an explicit manual retry may start another Attempt for a retryable failure, but it never creates an infinite automatic loop.
- The Worker maintains a heartbeat. Stale active jobs are requeued while retry policy allows; otherwise they become failed with a Worker-loss error.
- Cancellation requests must not be requeued by stale-job recovery.

### Storage and deployment

- PostgreSQL remains the source of truth for job metadata and queue coordination.
- Shared filesystem storage remains the Source, work, and artifact store for the current single-host deployment.
- One GPU Worker processes one job at a time in the MVP. The claim protocol remains safe for future multiple Workers.
- Jobs and files are retained until explicit deletion; automatic retention is disabled.
- Raw tool errors remain in server logs. API responses expose stable codes and sanitized messages.

### Testing seam

The primary seam is a black-box HTTP API plus job-lifecycle integration harness. It should exercise the API against a test database and temporary storage while substituting fake Source acquisition, media processing, and Transcription adapters. Tests verify observable state, artifacts, response codes, and cleanup; they do not assert SQL construction, private helper calls, or Worker implementation structure.

## Testing Decisions

- No automated tests currently exist in the repository, so there is no prior test pattern to preserve.
- Add API contract tests for source validation, job creation, structured errors, list pagination, detail polling, artifact download, and private-network assumptions.
- Add lifecycle integration tests covering queued, processing, completed, failed, cancel-requested, canceled, retryable failure, permanent failure, and stale-job recovery.
- Add artifact tests proving JSON and SRT retain segment timestamps, TXT remains direct text, and completion is all-or-nothing across requested formats.
- Add retry tests proving automatic retries are bounded, manual retry preserves job identity and configuration, and permanent failures cannot retry.
- Add cancellation and deletion tests proving queued cancellation is immediate, active cancellation is asynchronous, repeated cancellation is idempotent, and active deletion is rejected.
- Add source tests for uploaded files, supported public single-video YouTube URLs, rejected URL shapes, missing sources, and configurable upload limits.
- Add migration/compatibility tests for existing PostgreSQL volumes, especially the output-script schema and the requested-format fields.
- Add a small manual-quality fixture set for functional checks: complete text, reasonable segment times, language/script behavior, long media completion, and no partial artifacts. Do not introduce WER/CER as an MVP gate.

## Out of Scope

- Browser UI.
- Public internet exposure, accounts, API keys, tenant isolation, TLS termination, rate limiting, and quotas.
- Batch-submit requests containing multiple Sources.
- Reusable Source library or reusable Transcript API.
- Diarization, translation, summary, speaker alignment, word-level timestamps, confidence scores, and downstream Derived tasks.
- Email, webhook, WebSocket, or push notifications.
- Resumable uploads and create-job idempotency keys.
- Automatic source/result retention cleanup.
- Model discovery endpoint and model comparison workflow.
- Partial Transcript publication or checkpoint/resume processing.

## Further Notes

- The current implementation already has the core Source acquisition, media normalization, faster-whisper processing, OpenCC conversion, PostgreSQL queue, and artifact export seams. These should be preserved while the public domain boundary is refactored.
- The current code exposes Worker stages as statuses, lacks list/retry/cancel/delete/recovery behavior, accepts arbitrary HTTP URLs as YouTube sources, does not validate language/model, does not persist requested formats, and embeds full result text in detail responses. These are known implementation gaps against this spec.
- The existing migration flow is inconsistent: the Compose database initialization mounts the first migration while the API startup applies the output-script compatibility change. Schema evolution should be made explicit while adding requested formats and lifecycle support.
- Exact operational defaults for automatic retry count, heartbeat interval, stale timeout, model allowlist, and language allowlist are implementation parameters that must be chosen before tickets are executed. The current deployment default remains `large-v3-turbo` and the current upload guard remains 2 GB.
- This spec intentionally describes the current standalone Transcription boundary. If Derived tasks become real product requirements, revisit the aggregate relationship between Source, Transcript, and Derived task before extending the API.
