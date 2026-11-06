"""Check the PyTorch-only CUDA path; launch with src.runtime --torch-libraries.

This does not test CTranslate2. Use smoke-inference-pipeline.py for both backends.
"""

import ctypes
from pathlib import Path

# Exercise a component lookup before importing PyTorch, as ASR does in the Worker.
ctypes.CDLL("libcudnn_graph.so.9")
import faster_whisper
import torch


if __name__ == "__main__":
    print(f"faster-whisper: {faster_whisper.__version__}", flush=True)
    print(f"PyTorch: {torch.__version__}; CUDA: {torch.version.cuda}", flush=True)
    print(f"cuDNN: {torch.backends.cudnn.version()}", flush=True)
    if not torch.cuda.is_available():
        raise SystemExit("Smoke test failed: CUDA is unavailable")
    with torch.inference_mode():
        recurrent = torch.nn.LSTM(8, 8).to("cuda")
        output, _ = recurrent(torch.zeros(4, 1, 8, device="cuda"))
        if not torch.isfinite(output).all():
            raise SystemExit("Smoke test failed: CUDA RNN returned non-finite values")
        torch.cuda.synchronize()
    print("Loaded cuDNN libraries:", flush=True)
    print("\n".join(sorted({
        line.split()[-1]
        for line in Path("/proc/self/maps").read_text().splitlines()
        if "libcudnn" in line
    })), flush=True)
    print("Smoke test passed: cuDNN component lookup and CUDA RNN")
