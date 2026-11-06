"""Select NVIDIA wheel libraries only for isolated PyTorch processes.

cuDNN dynamically loads same-named component libraries. Without this startup
boundary, the backends can load incompatible components into one process.
ASR retains its original environment. Do not import either backend here.
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
    torch_libraries = bool(command and command[0] == "--torch-libraries")
    if torch_libraries:
        command = command[1:]
    if not command:
        raise SystemExit("Usage: python -m src.runtime [--torch-libraries] COMMAND [ARG ...]")
    environ = dict(os.environ)
    if torch_libraries:
        environ = inference_environment(environ, sys.path)
    os.execvpe(command[0], command, environ)


if __name__ == "__main__":
    main()
