# Expose coarse job statuses and separate processing stages

**Status: accepted**

The API exposes stable lifecycle statuses—`queued`, `processing`, `completed`, `failed`, `cancel_requested`, and `canceled`. Worker-specific details such as source acquisition, probing, transcoding, transcribing, and exporting are reported separately as `current_stage`. This keeps clients independent from internal pipeline stages while preserving useful progress information.

**Considered Options**

- Expose every Worker stage as the primary status: detailed, but couples API clients to an implementation pipeline that will change when new processing tasks are introduced.
- Expose only a single `processing` state: stable, but loses operational visibility needed for a long-running job.
- Use coarse lifecycle status plus an optional current stage: preserves both stability and visibility, therefore adopted.
