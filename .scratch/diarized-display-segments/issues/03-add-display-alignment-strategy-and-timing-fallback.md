# 03 — Add display alignment strategy and timing fallback

**What to build:** Diarization subtitle timing can use deployment-selected forced alignment or fixed faster-whisper word timestamps, exposes the strategy and fallback metadata in the final artifact, and uses proportional timing only for Display segmentation after reliable speaker attribution has already completed.

**Blocked by:** 01 — Build diarized Display segment foundation.

**Status:** closed

- [x] Deployment configuration selects `forced_alignment` by default or `whisper_word_timestamps` to skip forced alignment, without making either strategy a client request option.
- [x] Completed JSON artifacts expose the selected alignment strategy, applicable language, and fallback status/reason; the Diarization workflow verifies forced-alignment fallback to faster-whisper words.
- [x] When a speaker-consistent timed segment reaches Display segmentation without usable words, final cues receive proportional timings and `display_timing_strategy: proportional_estimate`; absent word data before attribution still fails rather than guessing speakers.

## Comments

- 2026-08-01: Added deployment-selected alignment mode and display-only proportional timing fallback, covered through the deterministic Diarization workflow.
