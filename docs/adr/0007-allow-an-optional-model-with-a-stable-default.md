# Allow an optional model with a stable default

**Status: accepted**

The transcription request may optionally select a model from a deployment-defined allowlist; when omitted, the service uses the deployment's default `large-v3-turbo`. This supports an explicit model choice without making model comparison the primary workflow. Unsupported model names are rejected by the API; the current private deployment does not need a model-discovery endpoint.

**Considered Options**

- Fix one server-side model and hide model selection: simpler resource management, but removes an explicit choice the current workflow may need.
- Accept any model string: flexible, but can trigger incompatible downloads or GPU failures.
- Allow a controlled optional model with a stable default: balances experimentation and predictable operation, therefore adopted.
