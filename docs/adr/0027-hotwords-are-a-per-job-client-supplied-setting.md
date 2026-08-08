# Hotwords are a per-job, client-supplied setting

Transcription and Diarization jobs will accept an optional Hotword list as part of Transcription configuration, set by the client at job creation and preserved unchanged across Retry, the same way `model` and `language` are handled today. Hotwords are not a deployment-wide fixed list.

This departs from the deployment-selected-strategy pattern used for `ALIGNMENT_STRATEGY` and `SUPPORTED_MODELS` (ADR 0018): those choices are about *how* recognition is performed and are independent of any one Source, so exposing them as client options would add client-facing complexity without client-facing value. Hotwords are the opposite — their entire value comes from naming words that are expected to appear in a *specific* Source (e.g. `PV-1` in one presentation), so a deployment-wide list cannot serve different jobs' different vocabularies.

**Considered Options**

- Deployment-wide fixed hotword list (env var, like `SUPPORTED_MODELS`): simpler, no schema change, but cannot address per-Source vocabulary and would need a deployment redeploy to update.
- Per-job client-supplied list (chosen): matches the content-dependent nature of hotwords and the existing `model`/`language` configuration pattern; costs a schema/migration change and API surface addition.
