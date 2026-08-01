# 02 — Add semantic Display-segmentation boundaries

**What to build:** A completed Diarization job chooses readable, balanced Display-segment boundaries rather than merely splitting at the nearest available word. It prefers sentence endings, then secondary punctuation, natural pauses, Chinese clause boundaries, and safe word boundaries, while keeping protected terminology whole.

**Blocked by:** 01 — Build diarized Display segment foundation.

**Status:** closed

- [x] When multiple cuts meet the hard display constraints, exported artifacts select the highest-priority natural boundary and favour balanced neighbouring cues.
- [x] Person names, proper nouns, number-and-unit expressions, English names, and hyphenated technical terms remain unbroken; an individually overlong protected span is emitted intact as the documented exception.
- [x] The black-box Diarization workflow covers Chinese punctuation and clause cases, natural pauses, protected terminology, and the overlong-span exception through deterministic fake-worker fixtures.

## Comments

- 2026-08-01: Added priority-aware display boundaries and protected-span handling, with deterministic black-box Diarization coverage.
