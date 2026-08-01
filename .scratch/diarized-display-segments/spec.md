# Diarized display segments

Status: completed

## Problem Statement

The owner can download a diarized Transcript whose public segments originate from ASR and speaker attribution rather than video display constraints. A single long segment can therefore produce multi-line subtitles that cover important video content, as in technical presentations with dense Chinese speech and terms such as `PV-1`. The owner needs one-line, time-bounded subtitles without losing the underlying ASR and alignment data or changing the established standalone Transcription workflow.

## Solution

Add a Display-segmentation stage to the Diarization workflow after speaker attribution and before artifact export. The stage derives final single-line Display segments from speaker-consistent text and timing data. Every diarized JSON, TXT, and SRT artifact represents those final Display segments; raw ASR segments, word timestamps, and other intermediate data remain internal work data until the Diarization job is deleted.

The Diarization creation request accepts an optional `max_chars_per_line`, defaulting to 20 visual units. The standalone Transcription endpoint and its artifacts remain unchanged. Display timing uses the deployment-selected alignment strategy, preserves reliable speaker boundaries, and uses proportional timing only as a display fallback after successful speaker attribution.

## User Stories

1. As the owner, I want a diarized Transcript to use Display segments, so that downloaded subtitles fit a video without covering excessive content.
2. As the owner, I want standalone Transcription artifacts to remain unchanged, so that this subtitle improvement does not alter an existing workflow I did not ask to change.
3. As the owner, I want each diarized subtitle cue to contain one visible line, so that it is quickly readable on a video.
4. As the owner, I want a speaker label and spoken text on the same line, so that I can identify the speaker without spending an extra display line.
5. As the owner, I want JSON Display segments to keep `speaker` separate from spoken `text`, so that an application can render or process each part independently.
6. As the owner, I want TXT and SRT cues to visibly prefix speech with `[SPEAKER_00]`, so that ordinary subtitle players show the anonymous speaker label.
7. As the owner, I want an unattributed cue to render as `[UNKNOWN]`, so that the platform does not invent a speaker identity.
8. As the owner, I want to set `max_chars_per_line` when I create a Diarization job, so that I can adapt subtitle density to a target video layout.
9. As the owner, I want omitted `max_chars_per_line` to use 20 visual units, so that ordinary jobs have a stable, useful default.
10. As the owner, I want the visible speaker label to count toward the line limit, so that labels cannot make an otherwise valid cue overflow the screen.
11. As the owner, I want spoken Chinese to remain at or below 6 visual units per second, so that a cue is readable at its assigned time.
12. As the owner, I want a cue to normally remain visible for at least 1.0 second, so that short fragments are not flashed too quickly to read.
13. As the owner, I want a cue to remain visible for no more than 5.0 seconds, so that a subtitle does not look stuck when speech continues.
14. As the owner, I want every reliable speaker change to create a new timed cue, so that a subtitle never combines speech from two speakers.
15. As the owner, I want sentence endings preferred as subtitle boundaries, so that a cue ends at a natural linguistic unit whenever possible.
16. As the owner, I want commas, enumeration marks, colons, semicolons, natural pauses, and Chinese clause boundaries considered in decreasing priority, so that long speech is divided naturally when a sentence boundary is unavailable.
17. As the owner, I want adjacent cues to be balanced in length when there are several valid cut positions, so that subtitle rhythm is visually even.
18. As the owner, I want person names, proper nouns, numbers with units, English names, and hyphenated terms such as `PV-1` kept whole, so that the subtitle does not damage meaning.
19. As the owner, I want an overlong protected span to remain intact as an explicit line-length exception, so that the system never splits a term merely to satisfy a layout limit.
20. As the owner, I want overlong speech to become multiple timed cues rather than line breaks, CSS wrapping, or smaller text, so that timing and readability are explicit in every subtitle format.
21. As the owner, I want the chosen alignment strategy and its fallback reason recorded in JSON metadata, so that I can judge the source of subtitle timing.
22. As the owner, I want the deployment to be able to force Whisper word timestamps while retaining fallback behavior, so that I can avoid a forced-alignment dependency when appropriate.
23. As the owner, I want proportional timing to be used only after speaker attribution has already succeeded, so that a display fallback never fabricates speaker assignments.
24. As the owner, I want the JSON metadata to identify proportional display timing when it was used, so that I can distinguish estimated timing from word-based timing.
25. As the owner, I want raw ASR segments and alignment data retained internally until job Deletion, so that the final display presentation does not destroy traceability.
26. As the owner, I want the public artifacts to contain only final Display segments, so that all downloads are consistent and no caller must choose between raw and display subtitle shapes.
27. As the owner, I want Diarization retry to preserve the selected line-length configuration, so that retry does not silently change the requested subtitle layout.
28. As the owner, I want an unsupported or invalid line-length value rejected at job creation, so that unusable subtitle jobs do not enter the queue.

## Implementation Decisions

### Scope and domain boundary

- `Display segment` is the final subtitle unit of a `Diarized transcript`; it is distinct from an internal `ASR segment` and from a `Speaker turn`.
- Add `segmenting_for_display` after `attributing_speakers` and before export in the Diarization Worker sequence.
- Do not add display segmentation, a line-length request parameter, new timing logic, or altered artifacts to standalone Transcription.
- Retain the raw ASR segments, aligned words, and attribution intermediate data as job work data until explicit Deletion. Do not provide them as a separate public artifact or database text copy.
- The main spoken text across Display segments must preserve the attributed transcript text, except for existing output-script conversion and whitespace normalization; segmentation must not rewrite content.

### Diarization API and persistence

- Extend only `POST /v1/diarizations` with optional positive-integer `max_chars_per_line`; omitted means 20.
- Reject zero, negative, and malformed values with a stable validation error. `POST /v1/transcriptions` must not accept the parameter.
- Persist the accepted value as immutable Diarization job configuration so that detail responses, retries, and exported metadata can report the applied setting.
- Keep the existing selectable Diarization output formats—JSON, TXT, and SRT. Completion remains all-or-nothing for the formats the user requested.

### Alignment and timing

- Add deployment-level `ALIGNMENT_STRATEGY` with `forced_alignment` as the default and `whisper_word_timestamps` as the mode that deliberately skips forced alignment.
- In `forced_alignment` mode, use forced alignment when available and fall back to faster-whisper word timestamps if it is unavailable or fails. In `whisper_word_timestamps` mode, use faster-whisper words directly.
- Record the selected `alignment_strategy`, alignment language when applicable, and fallback status/reason in the completed JSON artifact.
- If word timestamps are unavailable only at the Display-segmentation stage but the input already has a speaker-consistent time range, estimate child-cue times by each child main text's visual-unit proportion of that range. Set `display_timing_strategy` to `proportional_estimate`.
- Proportional estimation must never be used for speaker attribution. If reliable word data is absent before attribution, preserve the existing Diarization failure behavior rather than guessing speakers.

### Display-segmentation rules

- A Display segment is one visible line. Its speaker label and spoken text share that line; the system must not output embedded text line breaks or rely on wrapping, CSS, or font reduction.
- A smaller cue is always another timed Display segment with its own start and end, not a formatted continuation of the same cue.
- The complete visible cue is limited by `max_chars_per_line`. Chinese and other full-width characters count as one visual unit; ASCII letters and digits count as one-half visual unit; the visible speaker label counts toward the limit.
- Spoken text alone, excluding its speaker label, must not exceed 6 full-width-character visual units per second.
- A cue normally has a 1.0-second minimum and a 5.0-second maximum display duration. Move a proposed boundary to meet the minimum where possible, but never merge across a reliable speaker change; split a cue that would exceed the maximum.
- A reliable speaker change is the highest-priority timed boundary. A `null` speaker is not a reliable speaker change.
- Subject to the hard constraints, choose the cut nearest an ideal balanced split in this order: sentence-ending punctuation; secondary punctuation; natural word pause; Chinese semantic-clause boundary; then an adjacent safe word boundary.
- Protected spans include person names, proper nouns, number-and-unit expressions, English names, and hyphenated terms such as `PV-1`. Never cut within one. If one protected span alone exceeds the line limit, emit it intact as the sole exception.

### Artifact contract

- The Diarization JSON envelope remains a `diarized_transcript` and exposes final Display segments only. Each segment has sequential ID, start, end, speaker, and spoken text; top-level text remains plain text.
- TXT and SRT render each final cue as `[SPEAKER_00] main spoken text`; a null speaker renders as `[UNKNOWN] main spoken text`.
- The visible label counts against the line-length limit but not against the spoken-text reading-speed limit.
- Existing output metadata remains available. Add the applied display configuration and `display_timing_strategy` without adding a competing metadata schema version.

## Testing Decisions

Use the existing black-box Diarization workflow as the primary and highest seam: create a Diarization job through HTTP, run it against a controlled fake Worker with known words and Speaker turns, then download the requested artifacts. Assert user-visible job configuration, artifact content, cue timing, and metadata; do not test SQL statements, private splitter helpers, exporter internals, or attribution loops directly.

The existing Diarization workflow, artifact, API-dependency, and alignment-fallback integration tests are prior art. Extend the same test harness and fake-adapter style so ordinary tests do not require a GPU, model download, or external credentials. Keep a small set of authorized real-model smoke fixtures separate from the deterministic integration suite.

Cover at the workflow seam:

- accepted, defaulted, persisted, retried, and rejected `max_chars_per_line` values, including confirmation that transcription creation does not accept it;
- JSON, TXT, and SRT exports containing the same final Display-segment timing and expected speaker-label representation;
- single-line output, line capacity with speaker labels, 6-unit-per-second spoken-text rate, and 1.0-to-5.0-second durations;
- required splits at reliable speaker changes, including preservation of a short cue rather than merging speakers;
- ordered choices among sentence punctuation, secondary punctuation, pauses, Chinese clauses, and safe word boundaries, with balanced neighbouring cues where choices are equivalent;
- protected names, English identifiers, number-and-unit phrases, `PV-1`, and an overlong protected-span exception;
- word-based timing under both alignment modes, forced-alignment fallback to Whisper words, and display-only proportional estimation with its metadata;
- failure when attribution lacks reliable word data, proving that proportional estimation does not fabricate speaker assignment;
- retention of the existing standalone Transcription artifact behavior.

## Out of Scope

- Applying Display segmentation or `max_chars_per_line` to standalone Transcription.
- Altering ASR decoder settings, such as passing subtitle line length into faster-whisper token generation.
- Replacing, modifying, or expanding the speaker-attribution algorithm, diarization model, or forced-alignment implementation beyond strategy selection and recorded fallback behavior.
- Publishing raw ASR segments, word timestamps, raw diarization turns, or an additional raw-transcript artifact.
- Speaker naming, voiceprints, identity resolution, or speaker labels that remain stable across jobs.
- Overlap-aware subtitle representation.
- CSS, font-size, browser-player, or video-rendering changes used to compensate for overlong cues.
- A user-selectable forced-alignment model, diarization model, or other internal model parameters.
- Reworking the standalone Transcription API or its existing output formats.
- Adding VTT to either Diarization or standalone Transcription; a future VTT feature must reuse the established Display-segment contract for Diarization.

## Further Notes

This feature extends the completed speaker-diarization pipeline rather than reopening it. It follows the accepted architecture decision to keep public Diarization artifacts at segment level while retaining word-level information only internally. It also supersedes the earlier diarization-spec statement that raw intermediates should be discarded immediately after export: raw ASR and alignment work data now remain until the Diarization job is explicitly deleted.

The current product supports JSON, TXT, and SRT artifacts. VTT remains a separate future feature; when it is added to Diarization, it must use the same final Display segments and visible speaker labels. The source screenshot is a usability illustration, not a request to preserve its styling or font treatment.
