"""Run PyTorch diarization outside the CTranslate2 ASR process."""

import json
import logging
import os
import subprocess
import sys
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from .device import BackendDevice
from .failures import PermanentFailure, RetryableFailure, classify_failure


logger = logging.getLogger(__name__)


class IsolatedDiarization:
    def __init__(
        self,
        *,
        model: str,
        revision: str | None,
        model_root: Path,
        device: BackendDevice,
        allow_runtime_fallback: bool,
    ):
        self.device = device
        self.configuration = {
            "model": model,
            "revision": revision,
            "model_root": str(model_root),
            "device": asdict(device),
            "allow_runtime_fallback": allow_runtime_fallback,
        }

    def diarize(
        self, audio_path: Path, *, min_speakers: int | None, max_speakers: int | None,
    ) -> list[dict]:
        request = {
            **self.configuration, "audio_path": str(audio_path),
            "min_speakers": min_speakers, "max_speakers": max_speakers,
        }
        logger.info("starting isolated diarization backend=pyannote device=%s",
                    self.device.device)
        environ = {**os.environ, "PYTHONFAULTHANDLER": "1"}
        environ["PYTHONPATH"] = os.pathsep.join(filter(None, [
            str(Path(__file__).resolve().parents[1]), environ.get("PYTHONPATH"),
        ]))
        # Keep logs live, but use a private response file so native stdout cannot
        # corrupt the result. The parent continues refreshing the job heartbeat.
        with TemporaryDirectory(prefix="diarization-") as temporary:
            response_path = Path(temporary) / "response.json"
            result = subprocess.run(
                [sys.executable, "-m", "src.runtime", "--torch-libraries",
                 sys.executable, "-m", "src.isolated_diarization", str(response_path)],
                input=json.dumps(request), text=True, env=environ,
            )
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
                if result.returncode == 0 and isinstance(response.get("turns"), list):
                    logger.info("isolated diarization completed turns=%s", len(response["turns"]))
                    return response["turns"]
                if result.returncode == 1 and "failure" in response:
                    failure = response["failure"]
                    failure_type = RetryableFailure if failure["retryable"] else PermanentFailure
                    raise failure_type(failure["code"], failure["message"])
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                pass
        raise RetryableFailure(
            "diarization_process_failed", "The diarization process stopped unexpectedly.",
            detail=f"Diarization subprocess exited with status {result.returncode}",
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    response_path = Path(sys.argv[1])
    try:
        request = json.loads(sys.stdin.read())
        # Keep third-party progress in the Worker log stream.
        with redirect_stdout(sys.stderr):
            from .diarizer import PyannoteCommunityDiarization

            turns = PyannoteCommunityDiarization(
                model=request["model"], revision=request["revision"],
                model_root=Path(request["model_root"]),
                device=BackendDevice(**request["device"]),
                allow_runtime_fallback=request["allow_runtime_fallback"],
            ).diarize(
                Path(request["audio_path"]), min_speakers=request["min_speakers"],
                max_speakers=request["max_speakers"],
            )
        response_path.write_text(json.dumps({"turns": turns}), encoding="utf-8")
    except Exception as error:
        logger.exception("Diarization subprocess failed")
        response_path.write_text(json.dumps({"failure": asdict(classify_failure(error))}), encoding="utf-8")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
