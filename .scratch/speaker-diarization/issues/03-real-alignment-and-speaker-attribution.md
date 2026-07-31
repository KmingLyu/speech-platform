# 03 — Real alignment and speaker attribution

**What to build:** A diarization job runs the real transcription, alignment, pyannote exclusive diarization, word-level speaker attribution, segment regrouping, and export pipeline, while exposing only segment-level public results.

**Blocked by:** 02 — Diarization API with a fake end-to-end pipeline.

**Status:** closed

- [x] The Worker executes the agreed stage sequence from transcription through export.
- [x] Internal word timestamps are used to assign speakers, then output segments are regenerated sequentially.
- [x] The first version uses pyannote `exclusive_speaker_diarization` and does not publish raw diarization turns or word-level data.
- [x] Uncertain attribution is represented as `speaker: null` in JSON and `[UNKNOWN]` in TXT/SRT.
- [x] Empty transcription and no detected speakers produce their agreed permanent failures.
- [x] Partial attribution gaps can complete with attribution statistics.
- [x] Worker/integration tests use model adapters or controlled fixtures at the agreed public seams.

## Comments

- 2026-08-01: Implemented in commit `c39189c`. Docker integration harness: mypy passed and 66 pytest tests passed.
