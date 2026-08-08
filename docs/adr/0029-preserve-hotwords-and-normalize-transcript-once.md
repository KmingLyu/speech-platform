# Preserve Hotwords and normalize Transcript once in the Worker

**Status: accepted**

Hotwords are recognizer hints, not Transcript text, so the API preserves the user-provided strings exactly and sends them unchanged to faster-whisper. The API does not depend on OpenCC or perform text conversion. For `zh-tw` and `zh-cn`, the Worker performs one complete Transcript normalization immediately after ASR, including full text, segment text, and word text; all later alignment, diarization, and export stages consume that normalized Transcript. The persisted and public configuration contains only `language`; `output_script` is not a separate concept or field.

This keeps content transformation at the Worker seam that owns Transcript production, prevents Hotword identifiers from being rewritten, and removes duplicate `language`/`output_script` state.
