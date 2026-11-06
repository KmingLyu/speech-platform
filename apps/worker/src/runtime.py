"""Set NVIDIA wheel library precedence before launching the inference process.

cuDNN dynamically loads same-named component libraries. Without this startup
boundary, CTranslate2 can load the base image's older components before PyTorch
uses the newer cuDNN installed by pip. Do not import either backend here.
"""

import os
import sys
from pathlib import Path


def inference_environment(environ: dict[str, str], search_paths: list[str]) -> dict[str, str]:
    libraries: list[str] = []
    for root in search_paths:
        for package in ("cudnn", "cublas"):
            directory = Path(root) / "nvidia" / package / "lib"
            if directory.is_dir() and any(directory.glob("lib*.so*")):
                path = str(directory.resolve())
                if path not in libraries:
                    libraries.append(path)
    if not libraries:
        return dict(environ)
    existing = environ.get("LD_LIBRARY_PATH", "").split(":")
    paths = list(dict.fromkeys([*libraries, *(path for path in existing if path)]))
    return {**environ, "LD_LIBRARY_PATH": ":".join(paths)}


def main() -> None:
    command = sys.argv[1:]
    if not command:
        raise SystemExit("Usage: python -m src.runtime COMMAND [ARG ...]")
    environ = inference_environment(dict(os.environ), sys.path)
    os.execvpe(command[0], command, environ)


if __name__ == "__main__":
    main()
