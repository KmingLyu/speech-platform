# Use display segments for diarized subtitle outputs

**Status: accepted**

Diarization will retain ASR segments and alignment data as internal work data, but derive separate single-line Display segments before exporting every diarized JSON, TXT, SRT, and future VTT artifact. This preserves the recognizer's source data while making the user-facing subtitles fit video presentation; the same transformation deliberately does not apply to the standalone transcription workflow, whose existing timeline and artifacts remain unchanged until a separate decision is made.

`POST /v1/diarizations` will accept an optional `max_chars_per_line` setting (default 20), while the equivalent transcription endpoint will not. Display timing uses the deployment-selected word-alignment strategy—forced alignment by default or fixed Whisper word timestamps when configured—with proportional text-length estimation only as a last fallback after reliable speaker attribution. This keeps a stable diarization output contract without using decoder-token limits or CSS/font-size changes to solve subtitle layout.

**Considered Options**

- Reuse ASR segments as captions: preserves the raw shape but permits long, multi-line captions that obscure video.
- Apply display segmentation to transcription and diarization alike: offers uniform artifacts but changes standalone transcription's established timeline without a demonstrated need.
- Derive Display segments only for diarization: preserves raw data internally and addresses the video-subtitle use case without changing the transcription contract; adopted.
