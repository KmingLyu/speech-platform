# Prefer GPU with observable CPU fallback

**Status: accepted**

The Worker defaults to `INFERENCE_DEVICE=auto`. It probes CUDA independently
for faster-whisper's CTranslate2 runtime and pyannote's PyTorch runtime, uses
GPU for each backend that can access it, and falls back to CPU for an
unavailable backend. Every CPU selection is recorded in the Worker log with
the backend and reason. CUDA uses `float16` for faster-whisper; CPU uses `int8`.

An explicit `INFERENCE_DEVICE=cuda` is strict and prevents the Worker from
starting if either inference backend cannot access CUDA. An explicit
`INFERENCE_DEVICE=cpu` keeps both backends on CPU and is also logged. If CUDA
passes the startup probe but model initialization later fails, `auto` retries
that backend once on CPU and logs the runtime fallback; strict `cuda` does not.

This preserves the GPU-backed production architecture while allowing degraded
operation to remain visible instead of either silently running pyannote on CPU
or failing an `auto` deployment when CUDA is absent.

**Considered Options**

- Always require CUDA: predictable performance, but prevents intentional or
  temporary CPU operation and does not satisfy graceful degradation.
- Use one PyTorch CUDA probe for every model: simpler, but CTranslate2 and
  PyTorch are separate runtimes and can disagree about device availability.
- Silently fall back to CPU: keeps jobs running, but can hide a major throughput
  regression from the operator.
