# Keep language as a single user-facing option for the current scope

**Status: accepted**

The current API keeps one validated `language` option: omitted means automatic detection with the model's original script; `zh` means Chinese recognition with the original script; `zh-tw` and `zh-cn` select Chinese recognition plus Traditional Taiwan or Simplified Mainland output conventions; other supported faster-whisper language codes select recognition language without script conversion. Unsupported values are rejected at job creation. This is more intuitive for the current single-user workflow, while deliberately postponing independent recognition-language and output-script controls until a real use case requires them.

**Considered Options**

- Split `language` and `output_script` immediately: more orthogonal, but adds a distinction current users do not need.
- Keep one locale-like `language` option: simpler for current submissions, therefore adopted.
