import logging
from dataclasses import dataclass
from typing import Literal, cast


logger = logging.getLogger(__name__)

DeviceName = Literal["cuda", "cpu"]
DevicePreference = Literal["auto", "cuda", "cpu"]


@dataclass(frozen=True)
class BackendDevice:
    backend: str
    device: DeviceName
    compute_type: str | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True)
class InferenceDevices:
    requested: DevicePreference
    transcription: BackendDevice
    diarization: BackendDevice
    allow_runtime_fallback: bool


def _probe_faster_whisper_cuda() -> tuple[bool, str | None]:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return True, None
        return False, "CTranslate2 found no CUDA device"
    except Exception as error:
        return False, f"CTranslate2 CUDA probe failed: {error}"


def _probe_pyannote_cuda() -> tuple[bool, str | None]:
    try:
        import torch

        if torch.cuda.is_available():
            return True, None
        return False, "torch.cuda.is_available() is false"
    except Exception as error:
        return False, f"PyTorch CUDA probe failed: {error}"


def resolve_inference_devices(preference: str) -> InferenceDevices:
    normalized = preference.strip().lower()
    if normalized not in {"auto", "cuda", "cpu"}:
        raise ValueError("INFERENCE_DEVICE must be one of: auto, cuda, cpu")
    requested = cast(DevicePreference, normalized)

    if requested == "cpu":
        return InferenceDevices(
            requested=requested,
            transcription=BackendDevice(
                backend="faster-whisper",
                device="cpu",
                compute_type="int8",
                fallback_reason="CPU was explicitly configured",
            ),
            diarization=BackendDevice(
                backend="pyannote",
                device="cpu",
                fallback_reason="CPU was explicitly configured",
            ),
            allow_runtime_fallback=False,
        )

    transcription_cuda, transcription_reason = _probe_faster_whisper_cuda()
    diarization_cuda, diarization_reason = _probe_pyannote_cuda()
    unavailable: list[str] = []
    if not transcription_cuda:
        unavailable.append(f"faster-whisper ({transcription_reason})")
    if not diarization_cuda:
        unavailable.append(f"pyannote ({diarization_reason})")
    if requested == "cuda" and unavailable:
        raise RuntimeError(
            "INFERENCE_DEVICE=cuda but CUDA is unavailable for " + ", ".join(unavailable)
        )

    return InferenceDevices(
        requested=requested,
        transcription=BackendDevice(
            backend="faster-whisper",
            device="cuda" if transcription_cuda else "cpu",
            compute_type="float16" if transcription_cuda else "int8",
            fallback_reason=None if transcription_cuda else transcription_reason,
        ),
        diarization=BackendDevice(
            backend="pyannote",
            device="cuda" if diarization_cuda else "cpu",
            fallback_reason=None if diarization_cuda else diarization_reason,
        ),
        allow_runtime_fallback=requested == "auto",
    )


def log_inference_devices(devices: InferenceDevices) -> None:
    for selection in (devices.transcription, devices.diarization):
        values = (
            selection.backend,
            devices.requested,
            selection.device,
            selection.compute_type or "default",
        )
        if selection.device == "cpu":
            logger.warning(
                "inference backend is not using GPU backend=%s requested=%s "
                "device=%s compute_type=%s reason=%s",
                *values,
                selection.fallback_reason,
            )
        else:
            logger.info(
                "inference device selected backend=%s requested=%s "
                "device=%s compute_type=%s",
                *values,
            )
